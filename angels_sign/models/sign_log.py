import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SignLog(models.Model):
    _name = "sign.log"
    _description = "Signature Audit Log"
    _order = "id desc"
    _rec_name = "action"

    request_id = fields.Many2one(
        "sign.request", string="Signature Request", ondelete="cascade", required=True, index=True,
    )
    request_item_id = fields.Many2one("sign.request.item", string="Signer", ondelete="cascade")
    action = fields.Selection(
        [
            ("sent", "Invitation Sent"),
            ("reminded", "Reminder Sent"),
            ("viewed", "Document Viewed"),
            ("otp_sent", "Verification Code Sent"),
            ("signed", "Document Signed"),
            ("declined", "Document Declined"),
            ("delegated", "Signer Replaced"),
            ("cancelled", "Request Cancelled"),
            ("expired", "Request Expired"),
            ("completed", "Request Completed"),
        ],
        string="Action", required=True,
    )
    ip_address = fields.Char(string="IP Address")
    user_agent = fields.Char(string="Browser")
    signer_name = fields.Char(related="request_item_id.signer_name", store=True)
    signer_email = fields.Char(related="request_item_id.signer_email", store=True)
    date = fields.Datetime(string="Date & Time", default=fields.Datetime.now, readonly=True)
    notes = fields.Text(string="Notes")
    previous_log_hash = fields.Char(readonly=True)
    log_hash = fields.Char(string="Event Hash", readonly=True)

    def _payload(self):
        self.ensure_one()
        return "|".join([
            self.previous_log_hash or "",
            str(self.request_id.id),
            str(self.request_item_id.id or ""),
            self.action,
            self.ip_address or "",
            self.user_agent or "",
            fields.Datetime.to_string(self.date),
            self.notes or "",
        ])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("user_agent"):
                vals["user_agent"] = vals["user_agent"][:250]
        logs = self.browse()
        # One by one: every event chains to the previous event of its request.
        for vals in vals_list:
            previous = self.sudo().search(
                [("request_id", "=", vals["request_id"])], order="id desc", limit=1,
            )
            vals["previous_log_hash"] = previous.log_hash or ""
            log = super().create([vals])
            log.sudo().with_context(angels_sign_log_hash=True).write({
                "log_hash": hashlib.sha256(log._payload().encode()).hexdigest(),
            })
            logs |= log
        return logs

    def write(self, vals):
        if not (self.env.context.get("angels_sign_log_hash") and set(vals) == {"log_hash"}):
            raise UserError(_("Audit log entries cannot be modified."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Audit log entries cannot be deleted."))

    def _check_chain(self):
        """Return True when every event of the request chains to the previous one."""
        previous = ""
        for log in self.sorted("id"):
            expected = hashlib.sha256(log._payload().encode()).hexdigest()
            if log.previous_log_hash != previous or log.log_hash != expected:
                return False
            previous = log.log_hash
        return True
