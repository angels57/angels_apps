from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    auth_method = fields.Selection(
        selection_add=[("sms_otp", "Email link + SMS code")], ondelete={"sms_otp": "set default"},
    )
    signer_phone = fields.Char(string="Mobile")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        super()._onchange_partner_id()
        if self.partner_id:
            self.signer_phone = self.partner_id.phone

    def _send_otp_code(self, code):
        self.ensure_one()
        if self.auth_method != "sms_otp":
            return super()._send_otp_code(code)
        if not self.signer_phone:
            raise UserError(_("No mobile number is set for this signer."))
        self.env["sms.sms"].sudo().create({
            "number": self.signer_phone,
            "body": _("%(code)s is your Easy Sign code for %(doc)s. Valid 10 minutes.",
                      code=code, doc=self.request_id.document_name or self.request_id.name),
        }).send()
