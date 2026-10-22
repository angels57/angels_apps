from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

WIZARD_MODEL = "angels.approval.request.wizard"
REQUEST_MODEL = "angels.approval.request"


class AngelsApprovalFlow(models.Model):
    _name = "angels.approval.flow"
    _description = "Approval Flow"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        help="Leave empty to use the flow in every company.",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Applies To",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_name = fields.Char(related="model_id.model", store=True, string="Model Name")
    domain = fields.Char(
        string="Records",
        default="[]",
        help="Only records that match this filter can use the flow.",
    )
    step_ids = fields.One2many("angels.approval.step", "flow_id", string="Steps", copy=True)
    requester_group_ids = fields.Many2many(
        "res.groups",
        string="Allowed Requesters",
        help="Groups allowed to request this approval. Empty means every approval user.",
    )
    allow_self_approval = fields.Boolean(
        help="Let the requester approve a step where they are an approver.",
    )
    approve_action_id = fields.Many2one(
        "ir.actions.server",
        string="On Approval",
        domain="[('model_id', '=', model_id)]",
        groups="base.group_system",
        help="Server action run on the record when the request is approved.",
    )
    reject_action_id = fields.Many2one(
        "ir.actions.server",
        string="On Rejection",
        domain="[('model_id', '=', model_id)]",
        groups="base.group_system",
        help="Server action run on the record when the request is rejected.",
    )
    request_ids = fields.One2many(REQUEST_MODEL, "flow_id", string="Requests")
    request_count = fields.Integer(compute="_compute_request_count")

    @api.depends("request_ids")
    def _compute_request_count(self):
        counts = dict(
            self.env[REQUEST_MODEL]._read_group(
                [("flow_id", "in", self.ids)], ["flow_id"], ["__count"]
            )
        )
        for flow in self:
            flow.request_count = counts.get(flow, 0)

    @api.constrains("domain", "model_id")
    def _check_domain(self):
        for flow in self:
            try:
                flow._validate_domain(flow.domain)
            except Exception as error:
                raise ValidationError(
                    _("The record filter of %(flow)s is not valid: %(error)s",
                      flow=flow.name, error=error)
                ) from error

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _eval_domain(self, domain):
        return safe_eval(domain or "[]", {"uid": self.env.uid, "user": self.env.user})

    def _validate_domain(self, domain):
        self.ensure_one()
        self.env[self.model_name].sudo().search_count(self._eval_domain(domain), limit=1)

    def _filter_records(self, records):
        """Records (sudo) that match the flow filter, in the caller's env."""
        self.ensure_one()
        domain = self._eval_domain(self.domain)
        return records.sudo().filtered_domain(domain).with_env(records.env)

    def _flows_for(self, records):
        """Active flows that every record in ``records`` can use."""
        flows = self.search([("model_name", "=", records._name)])
        user_groups = self.env.user.all_group_ids
        return flows.filtered(
            lambda f: (not f.requester_group_ids or f.requester_group_ids & user_groups)
            and len(f._filter_records(records)) == len(records)
        )

    # ------------------------------------------------------------------
    # "Request Approval" and "Approvals" actions on the target model
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        flows = super().create(vals_list)
        flows._sync_bindings(flows.model_id)
        return flows

    def write(self, vals):
        old_models = self.model_id
        res = super().write(vals)
        if {"model_id", "active"} & set(vals):
            self._sync_bindings(old_models | self.model_id)
        return res

    def unlink(self):
        ir_models = self.model_id
        res = super().unlink()
        self._sync_bindings(ir_models)
        return res

    def _sync_bindings(self, ir_models):
        """Keep one pair of bound actions per model that has an active flow."""
        templates = (
            (WIZARD_MODEL, "angels_approvals.action_request_wizard_template"),
            (REQUEST_MODEL, "angels_approvals.action_record_requests_template"),
        )
        Action = self.env["ir.actions.act_window"].sudo()
        Flow = self.sudo().with_context(active_test=True)
        for ir_model in ir_models:
            has_flow = bool(Flow.search_count([("model_id", "=", ir_model.id)], limit=1))
            for res_model, xmlid in templates:
                bound = Action.search([
                    ("res_model", "=", res_model),
                    ("binding_model_id", "=", ir_model.id),
                ])
                if has_flow and not bound:
                    template = self.env.ref(xmlid).sudo()
                    template.copy({"binding_model_id": ir_model.id})
                elif not has_flow and bound:
                    bound.unlink()

    def action_view_requests(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "angels_approvals.action_approval_request_all"
        )
        action["domain"] = [("flow_id", "=", self.id)]
        action["context"] = {}
        return action
