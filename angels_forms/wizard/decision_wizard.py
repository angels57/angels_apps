from odoo import fields, models


class AngelsFormDecisionWizard(models.TransientModel):
    _name = "angels.form.decision.wizard"
    _description = "Form Request Decision"

    submission_id = fields.Many2one("angels.form.submission", required=True, readonly=True)
    decision = fields.Selection(
        [("approve", "Approve"), ("reject", "Reject")], required=True, readonly=True
    )
    comment = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.submission_id.current_step_id._decide(self.decision, self.comment)
        return {"type": "ir.actions.act_window_close"}
