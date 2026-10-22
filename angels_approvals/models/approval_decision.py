from odoo import _, fields, models
from odoo.exceptions import UserError


class AngelsApprovalDecision(models.Model):
    _name = "angels.approval.decision"
    _description = "Approval Decision"
    _order = "date desc, id desc"

    line_id = fields.Many2one(
        "angels.approval.request.line", string="Step", required=True, ondelete="cascade", index=True
    )
    request_id = fields.Many2one(
        related="line_id.request_id", store=True, index=True, string="Request"
    )
    user_id = fields.Many2one("res.users", string="Decided By", required=True, index=True)
    on_behalf_of_id = fields.Many2one(
        "res.users", string="On Behalf Of", required=True,
        help="Approver this decision counts for. Differs from the user when acting as a delegate.",
    )
    decision = fields.Selection(
        [("approve", "Approved"), ("reject", "Rejected")], required=True
    )
    comment = fields.Text()
    date = fields.Datetime(required=True, default=fields.Datetime.now)

    def write(self, vals):
        raise UserError(_("Approval decisions cannot be changed."))

    def unlink(self):
        if not self.env.context.get("module_uninstall"):
            raise UserError(_("Approval decisions cannot be deleted."))
        return super().unlink()
