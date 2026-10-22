from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AngelsApprovalRequestWizard(models.TransientModel):
    _name = "angels.approval.request.wizard"
    _description = "Request Approval Wizard"

    res_model = fields.Char(string="Model", required=True, readonly=True)
    res_ids = fields.Json(string="Record IDs", required=True, readonly=True)
    record_count = fields.Integer(compute="_compute_flows")
    available_flow_ids = fields.Many2many(
        "angels.approval.flow", string="Available Flows", compute="_compute_flows"
    )
    flow_id = fields.Many2one(
        "angels.approval.flow",
        string="Approval Flow",
        domain="[('id', 'in', available_flow_ids)]",
    )
    note = fields.Text(string="Reason")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        res_model = context.get("active_model")
        res_ids = context.get("active_ids") or ([context["active_id"]] if context.get("active_id") else [])
        if res_model and res_model in self.env and res_ids:
            values.update(res_model=res_model, res_ids=res_ids)
            flows = self.env["angels.approval.flow"]._flows_for(self._records(res_model, res_ids))
            if len(flows) == 1:
                values["flow_id"] = flows.id
        return values

    @api.model
    def _records(self, res_model, res_ids):
        return self.env[res_model].browse(res_ids).exists()

    @api.depends("res_model", "res_ids")
    def _compute_flows(self):
        Flow = self.env["angels.approval.flow"]
        for wizard in self:
            records = wizard._get_records()
            wizard.record_count = len(records)
            wizard.available_flow_ids = Flow._flows_for(records) if records else Flow

    def _get_records(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_ids:
            return self.env["res.partner"]
        return self._records(self.res_model, self.res_ids)

    def action_submit(self):
        self.ensure_one()
        records = self._get_records()
        if not records:
            raise UserError(_("Select at least one record."))
        if not self.flow_id or self.flow_id not in self.available_flow_ids:
            raise UserError(_("Choose an approval flow that applies to the selected records."))
        # The requester must be able to read every record before the
        # request is created with elevated rights.
        records.check_access("read")
        Request = self.env["angels.approval.request"]
        requests = Request.browse()
        for record in records:
            requests |= Request._submit(self.flow_id, record, note=self.note)
        if len(requests) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "angels.approval.request",
                "res_id": requests.id,
                "view_mode": "form",
                "target": "current",
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("%(count)s approval requests were created.", count=len(requests)),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
