from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .flow_condition import field_kind, record_value

TITLE_LENGTH = 80


class AngelsFlowRun(models.Model):
    """One record going through one flow."""

    _name = "angels.flow.run"
    _inherit = ["angels.flow.document.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Flow Run"
    _order = "id desc"
    # Reviewers only read the run; they still discuss it in the chatter.
    _mail_post_access = "read"

    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="/")
    flow_id = fields.Many2one("angels.flow", required=True, readonly=True, ondelete="cascade", index=True)
    res_model = fields.Char(string="Model", required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference(string="Record ID", model_field="res_model", required=True, readonly=True,
                                      index=True)
    record_name = fields.Char(string="Record", compute="_compute_record_name", store=True)
    user_id = fields.Many2one("res.users", string="Started By", required=True, readonly=True,
                              default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    date_start = fields.Datetime(string="Started On", readonly=True, default=fields.Datetime.now)
    step_ids = fields.One2many("angels.flow.run.step", "run_id", string="Steps")
    current_step_id = fields.Many2one(
        "angels.flow.run.step", string="Current Step", compute="_compute_current_step", store=True,
    )
    current_step_type = fields.Selection(related="current_step_id.step_type", string="Current Step Type")
    wait_node_id = fields.Many2one("angels.flow.node", string="Waiting At", readonly=True, ondelete="set null")
    wait_until = fields.Datetime(string="Waiting Until", readonly=True, index=True)
    is_my_turn = fields.Boolean(string="Waiting for Me", compute="_compute_is_my_turn",
                                search="_search_is_my_turn")

    @api.depends("res_model", "res_id")
    def _compute_record_name(self):
        for run in self:
            record = run._record()
            run.record_name = (record.display_name or "")[:TITLE_LENGTH] if record else False

    @api.depends("name", "record_name")
    def _compute_display_name(self):
        for run in self:
            run.display_name = f"{run.name} - {run.record_name}" if run.record_name else run.name

    @api.depends("step_ids.state")
    def _compute_current_step(self):
        for run in self:
            run.current_step_id = run.step_ids.filtered(lambda s: s.state == "pending")[:1]

    @api.depends_context("uid")
    @api.depends("state", "current_step_id")
    def _compute_is_my_turn(self):
        user = self.env.user
        for run in self:
            step = run.sudo().current_step_id
            run.is_my_turn = bool(run.state == "pending" and step and step._can_decide(user))

    def _search_is_my_turn(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        user = self.env.user
        steps = self.env["angels.flow.run.step"].sudo().search([
            ("state", "=", "pending"), ("run_id.state", "=", "pending"), ("user_ids", "in", user.ids),
        ]).filtered(lambda s: s._can_decide(user))
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", steps.run_id.ids)]

    def _record(self):
        """The record the run is about, or an empty recordset if it is gone."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_id:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists()

    # ------------------------------------------------------------------
    # What the flow reads from a run
    # ------------------------------------------------------------------

    def _flow_values(self):
        record = self._record()
        if not record:
            return {}
        nodes = self.flow_id.node_ids
        used = nodes.condition_ids.field_id | nodes.user_field_id
        return {field.name: record_value(record, field) for field in used if field_kind(field)}

    def _flow_requester(self):
        return self.user_id

    def _flow_allow_self_approval(self):
        return self.flow_id.allow_self_approval

    def _flow_activity_type(self):
        return self.env.ref("angels_flow.mail_activity_flow_step")

    def _flow_run_node(self, node, values):
        if node.node_type == "wait":
            delta = {"hours": node.wait_amount} if node.wait_unit == "hours" else {"days": node.wait_amount}
            until = fields.Datetime.add(fields.Datetime.now(), **delta)
            self.sudo().write({"wait_node_id": node.id, "wait_until": until})
            self.sudo().message_post(
                body=Markup("<p>%s</p>") % _("%(step)s: the flow goes on after %(date)s.", step=node.name,
                                             date=fields.Datetime.to_string(until)),
                subtype_xmlid="mail.mt_note",
            )
            return True
        return super()._flow_run_node(node, values)

    def _flow_start(self, start):
        self.ensure_one()
        self.sudo().write({
            "name": self.env["ir.sequence"].sudo().next_by_code("angels.flow.run") or "/",
            "state": "pending",
        })
        self._post_on_record(_("The flow %(flow)s started: %(run)s.", flow=self.flow_id.name,
                               run=self._get_html_link()))
        return self._flow_run(start.next_id)

    def _flow_fail(self, error):
        """A run started automatically that could not go on: cancelled, with the reason."""
        self.ensure_one()
        self.sudo().write({"state": "cancelled", "date_done": fields.Datetime.now()})
        self.sudo().message_post(
            body=Markup("<p>%s</p><p>%s</p>") % (_("The flow could not go on."), str(error)),
            subtype_xmlid="mail.mt_note",
        )

    def _flow_finish(self, state):
        result = super()._flow_finish(state)
        self.sudo().write({"wait_node_id": False, "wait_until": False})
        if state == "approved":
            message = _("The flow %(flow)s ended: approved (%(run)s).", flow=self.flow_id.name, run=self._get_html_link())
        else:
            message = _("The flow %(flow)s ended: rejected (%(run)s).", flow=self.flow_id.name, run=self._get_html_link())
        self._post_on_record(message)
        return result

    def _post_on_record(self, message):
        record = self._record()
        if record and hasattr(record, "message_post"):
            record.message_post(body=Markup("<p>%s</p>") % message, subtype_xmlid="mail.mt_note")

    @api.model
    def _cron_resume(self):
        """Runs whose Wait step is over go on."""
        for run in self.search([("state", "=", "pending"), ("wait_until", "<=", fields.Datetime.now())]):
            node = run.wait_node_id
            run.sudo().write({"wait_node_id": False, "wait_until": False})
            try:
                with self.env.cr.savepoint():
                    run._flow_run(node.next_id)
            except UserError as error:
                run._flow_fail(error)

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_open_record(self):
        self.ensure_one()
        record = self._record()
        if not record:
            raise UserError(_("The record of %(run)s no longer exists.", run=self.display_name))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
        }

    def _open_decision_wizard(self, decision):
        self.ensure_one()
        if not self.is_my_turn:
            raise UserError(_("This run is not waiting for your decision."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Approve") if decision == "approve" else _("Reject"),
            "res_model": "angels.flow.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_run_id": self.id, "default_decision": decision},
        }

    def action_approve(self):
        return self._open_decision_wizard("approve")

    def action_reject(self):
        return self._open_decision_wizard("reject")

    def action_cancel(self):
        is_manager = self.env.user.has_group("angels_flow.group_flow_manager")
        for run in self:
            if run.state != "pending":
                continue
            if not (is_manager or run.user_id == self.env.user):
                raise AccessError(_("Only who started %(run)s or an administrator can cancel it.",
                                    run=run.display_name))
            run._flow_cancel()
            run.sudo().write({"wait_node_id": False, "wait_until": False})
            run.sudo().message_post(
                body=Markup("<p>%s</p>") % _("Run cancelled by %(user)s.", user=self.env.user.name),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def write(self, vals):
        if not self.env.su and {"state", "flow_id", "res_model", "res_id", "name"} & set(vals):
            self.check_access("write")
            raise UserError(_("Runs change only through their flow."))
        return super().write(vals)


class AngelsFlowRunStep(models.Model):
    """One flow step reached by one run: an approval, a task or a notification."""

    _name = "angels.flow.run.step"
    _inherit = ["angels.flow.step.mixin"]
    _description = "Flow Run Step"
    _order = "run_id, sequence, id"
    _flow_document = "run_id"

    run_id = fields.Many2one("angels.flow.run", required=True, ondelete="cascade", index=True, readonly=True)
    node_id = fields.Many2one("angels.flow.node", string="Flow Step", ondelete="set null", readonly=True)
    user_ids = fields.Many2many(
        "res.users", "angels_flow_run_step_user_rel", "step_id", "user_id", string="People", readonly=True,
    )
    approved_by_ids = fields.Many2many(
        "res.users", "angels_flow_run_step_approved_rel", "step_id", "user_id", string="Approved By", readonly=True,
    )


class AngelsFlowDecisionWizard(models.TransientModel):
    _name = "angels.flow.decision.wizard"
    _description = "Flow Run Decision"

    run_id = fields.Many2one("angels.flow.run", required=True, readonly=True)
    decision = fields.Selection([("approve", "Approve"), ("reject", "Reject")], required=True, readonly=True)
    step_type = fields.Selection(related="run_id.current_step_type")
    comment = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.run_id.current_step_id._decide(self.decision, self.comment)
        return {"type": "ir.actions.act_window_close"}
