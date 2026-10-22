from odoo import fields, models


class AngelsApprovalDecisionWizard(models.TransientModel):
    _name = "angels.approval.decision.wizard"
    _description = "Approval Decision Wizard"

    request_id = fields.Many2one("angels.approval.request", required=True, readonly=True)
    decision = fields.Selection(
        [("approve", "Approve"), ("reject", "Reject")], required=True, readonly=True
    )
    comment = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.request_id.current_line_id._decide(self.decision, self.comment)
        return {"type": "ir.actions.act_window_close"}
