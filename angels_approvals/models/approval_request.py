from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

STATES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]


class AngelsApprovalRequest(models.Model):
    _name = "angels.approval.request"
    _description = "Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    # Approvers only read the request; they still discuss it in the chatter.
    _mail_post_access = "read"

    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="/")
    flow_id = fields.Many2one(
        "angels.approval.flow", required=True, readonly=True, ondelete="restrict", index=True
    )
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    res_model = fields.Char(string="Model", required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference(
        string="Record ID", model_field="res_model", required=True, readonly=True, index=True
    )
    res_name = fields.Char(string="Record", readonly=True)
    requested_by_id = fields.Many2one(
        "res.users", string="Requested By", required=True, readonly=True, index=True
    )
    note = fields.Text(string="Reason", readonly=True)
    state = fields.Selection(
        STATES, required=True, default="pending", readonly=True, tracking=True, index=True
    )
    date_done = fields.Datetime(string="Decided On", readonly=True)
    line_ids = fields.One2many("angels.approval.request.line", "request_id", string="Steps")
    decision_ids = fields.One2many("angels.approval.decision", "request_id", string="Decisions")
    current_line_id = fields.Many2one(
        "angels.approval.request.line", string="Current Step",
        compute="_compute_current_line", store=True,
    )
    is_my_turn = fields.Boolean(
        string="Waiting for Me", compute="_compute_is_my_turn", search="_search_is_my_turn"
    )
    can_cancel = fields.Boolean(compute="_compute_can_cancel")

    _one_pending_per_record = models.UniqueIndex(
        "(res_model, res_id) WHERE state = 'pending'",
        "This record already has a pending approval request.",
    )

    @api.depends("line_ids.state")
    def _compute_current_line(self):
        for request in self:
            request.current_line_id = request.line_ids.filtered(lambda l: l.state == "pending")[:1]

    @api.depends_context("uid")
    @api.depends("state", "current_line_id")
    def _compute_is_my_turn(self):
        user = self.env.user
        for request in self:
            line = request.sudo().current_line_id
            request.is_my_turn = bool(
                request.state == "pending" and line and line._principals_for(user)
            )

    def _search_is_my_turn(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        user = self.env.user
        principals = user | self.env["angels.approval.delegation"]._delegators_of(user)
        lines = self.env["angels.approval.request.line"].sudo().search([
            ("state", "=", "pending"),
            ("request_id.state", "=", "pending"),
            ("approver_ids", "in", principals.ids),
        ]).filtered(lambda l: l._principals_for(user))
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", lines.request_id.ids)]

    @api.depends_context("uid")
    @api.depends("state", "requested_by_id")
    def _compute_can_cancel(self):
        is_manager = self.env.user.has_group("angels_approvals.group_approval_manager")
        for request in self:
            request.can_cancel = request.state == "pending" and (
                is_manager or request.requested_by_id == self.env.user
            )

    # ------------------------------------------------------------------
    # Target record
    # ------------------------------------------------------------------

    def _get_record(self):
        self.ensure_one()
        return self.env[self.res_model].browse(self.res_id).exists()

    def _post_on_record(self, body):
        record = self._get_record()
        if record and hasattr(record, "message_post"):
            record.sudo().message_post(body=body, subtype_xmlid="mail.mt_note")

    def action_open_record(self):
        self.ensure_one()
        record = self._get_record()
        if not record:
            raise UserError(_("The record no longer exists."))
        record.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    @api.model
    def _submit(self, flow, record, note=False):
        """Create and start a request. Callers must check access first."""
        if not flow._filter_records(record):
            raise UserError(
                _("%(record)s does not match the flow %(flow)s.",
                  record=record.display_name, flow=flow.name)
            )
        steps = flow.step_ids.sorted("sequence")
        applicable = steps.filtered(lambda s: s._applies_to(record))
        if not applicable:
            raise UserError(_("No step of the flow %(flow)s applies to this record.", flow=flow.name))
        for step in applicable:
            if not step._get_approvers(record):
                raise UserError(_("The step %(step)s has no approvers.", step=step.name))
        company = record.company_id if "company_id" in record._fields else flow.company_id
        request = self.sudo().create({
            "name": self.env["ir.sequence"].sudo().next_by_code("angels.approval.request") or "/",
            "flow_id": flow.id,
            "company_id": company.id or self.env.company.id,
            "res_model": record._name,
            "res_id": record.id,
            "res_name": record.display_name,
            "requested_by_id": self.env.user.id,
            "note": note,
            "line_ids": [
                fields.Command.create({
                    "step_id": step.id,
                    "sequence": index,
                    "name": step.name,
                    "approval_rule": step.approval_rule,
                    "state": "waiting" if step in applicable else "skipped",
                })
                for index, step in enumerate(steps, start=1)
            ],
        })
        request.message_subscribe(partner_ids=self.env.user.partner_id.ids)
        request._post_on_record(
            Markup(_("Approval requested: %(link)s")) % {"link": request._link()}
        )
        request._advance()
        return request.with_env(self.env)

    def _link(self):
        return Markup('<a href="#" data-oe-model="%s" data-oe-id="%s">%s</a>') % (
            self._name, self.id, self.name
        )

    def _advance(self):
        """Activate the next waiting step, or approve when none is left."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.state == "waiting").sorted("sequence")[:1]
        if line:
            line._activate()
        else:
            self._finish("approved")

    def _finish(self, state):
        self.ensure_one()
        self.sudo().write({"state": state, "date_done": fields.Datetime.now()})
        self.line_ids.filtered(lambda l: l.state == "waiting").sudo().state = "skipped"
        self._clear_activities()
        if state == "approved":
            body = _("Approval %(link)s was approved.")
            action = self.flow_id.sudo().approve_action_id
        else:
            body = _("Approval %(link)s was rejected.")
            action = self.flow_id.sudo().reject_action_id
        self._post_on_record(Markup(body) % {"link": self._link()})
        self.sudo().message_post(
            body=Markup(body) % {"link": self.name},
            partner_ids=self.requested_by_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        record = self._get_record()
        if action and record:
            # Same as base.automation: the action was configured by an
            # administrator and runs with superuser rights on the record.
            action.with_context(
                active_model=record._name, active_id=record.id, active_ids=record.ids,
            ).run()

    def _clear_activities(self):
        activity_type = self.env.ref("angels_approvals.mail_activity_approval")
        self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type
        ).unlink()

    def action_cancel(self):
        for request in self:
            if not request.can_cancel:
                raise AccessError(_("Only the requester or an administrator can cancel %(name)s.",
                                    name=request.name))
            request.sudo().write({"state": "cancelled", "date_done": fields.Datetime.now()})
            request.line_ids.filtered(lambda l: l.state in ("waiting", "pending")).sudo().state = "skipped"
            request._clear_activities()
            request._post_on_record(
                Markup(_("Approval %(link)s was cancelled.")) % {"link": request._link()}
            )
        return True

    def _open_decision_wizard(self, decision):
        self.ensure_one()
        if not self.is_my_turn:
            raise UserError(_("This request is not waiting for your decision."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Approve") if decision == "approve" else _("Reject"),
            "res_model": "angels.approval.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id, "default_decision": decision},
        }

    def action_approve(self):
        return self._open_decision_wizard("approve")

    def action_reject(self):
        return self._open_decision_wizard("reject")

    def write(self, vals):
        if not self.env.su and {"state", "res_model", "res_id", "flow_id"} & set(vals):
            self.check_access("write")
            raise UserError(_("Approval requests change only through their workflow."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Approval requests cannot be deleted. Cancel them instead."))
