import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OTP_VALIDITY = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_DELAY = timedelta(seconds=60)


class SignRequestItem(models.Model):
    _name = "sign.request.item"
    _description = "Signature Request Signer"
    _order = "sequence, id"
    _rec_name = "signer_name"

    request_id = fields.Many2one(
        "sign.request", string="Signature Request", ondelete="cascade", required=True, index=True,
    )
    sequence = fields.Integer(default=10)
    role_id = fields.Many2one("sign.role", string="Role")
    color = fields.Integer(compute="_compute_color")
    partner_id = fields.Many2one("res.partner", string="Contact")
    signer_name = fields.Char(string="Name", required=True)
    signer_email = fields.Char(string="Email")
    state = fields.Selection(
        [
            ("pending", "Draft"),
            ("waiting", "Waiting Turn"),
            ("sent", "Invitation Sent"),
            ("viewed", "Viewed"),
            ("signed", "Signed"),
            ("declined", "Declined"),
            ("cancelled", "Cancelled"),
        ],
        string="Status", default="pending", readonly=True,
    )
    auth_method = fields.Selection(
        [("none", "Email link"), ("email_otp", "Email link + code")],
        string="Verification", default="none", required=True,
    )
    can_delegate = fields.Boolean(
        string="Can Be Replaced",
        help="Allow changing this signer after the request has been sent.",
    )
    access_token = fields.Char(copy=False, readonly=True, index=True)
    sign_url = fields.Char(string="Signing Link", compute="_compute_sign_url")
    signature = fields.Binary(string="Signature", attachment=True, copy=False, readonly=True)
    initials = fields.Binary(string="Initials", attachment=True, copy=False, readonly=True)
    signature_method = fields.Selection(
        [("draw", "Drawn"), ("type", "Typed"), ("upload", "Uploaded")],
        string="Signature Method", readonly=True, copy=False,
    )
    signed_date = fields.Datetime(string="Signed On", readonly=True, copy=False)
    declined_reason = fields.Text(string="Decline Reason", readonly=True, copy=False)
    ip_address = fields.Char(string="IP Address", readonly=True, copy=False)
    user_agent = fields.Char(string="Browser", readonly=True, copy=False)
    signer_hash = fields.Char(string="Signer Hash", readonly=True, copy=False)
    last_reminder_date = fields.Datetime(readonly=True, copy=False)
    otp_hash = fields.Char(copy=False, groups="base.group_system")
    otp_expiry = fields.Datetime(copy=False, groups="base.group_system")
    otp_sent_date = fields.Datetime(copy=False, groups="base.group_system")
    otp_attempts = fields.Integer(copy=False, groups="base.group_system")

    @api.depends("request_id.request_item_ids")
    def _compute_color(self):
        for item in self:
            ids = [i for i in item.request_id.request_item_ids.ids if isinstance(i, int)]
            item.color = (ids.index(item.id) % 10) + 1 if item.id in ids else 1

    @api.depends("access_token")
    def _compute_sign_url(self):
        for item in self:
            item.sign_url = f"{item.get_base_url()}/sign/view/{item.access_token}" if item.access_token else False

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            self.signer_name = self.partner_id.name
            self.signer_email = self.partner_id.email

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("access_token", secrets.token_urlsafe(32))
        return super().create(vals_list)

    def write(self, vals):
        forced = self.env.context.get("easy_sign_force")
        replaced = self.browse()
        if not forced and {"signer_name", "signer_email", "partner_id"} & set(vals):
            for item in self:
                if item.request_id.state == "draft":
                    continue
                if item.state not in ("waiting", "sent", "viewed") or not item.can_delegate:
                    raise UserError(_("Signer %s can no longer be changed.", item.signer_name))
                replaced |= item
        config = {"sequence", "auth_method", "can_delegate", "role_id"}
        if not forced and config & set(vals) and any(i.request_id.state != "draft" for i in self):
            raise UserError(_("Signers can only be reconfigured while the request is a draft."))
        res = super().write(vals)
        for item in replaced:
            item.sudo().with_context(easy_sign_force=True).write({"access_token": secrets.token_urlsafe(32)})
            self.env["sign.log"].sudo().create({
                "request_id": item.request_id.id,
                "request_item_id": item.id,
                "action": "delegated",
                "notes": _("Signer replaced by %s", item.signer_email),
            })
            if item.state in ("sent", "viewed"):
                item._invite()
        return res

    def unlink(self):
        if any(item.request_id.state != "draft" for item in self):
            raise UserError(_("Signers can only be removed while the request is a draft."))
        return super().unlink()

    def _reset_for_draft(self):
        for item in self:
            item.sudo().with_context(easy_sign_force=True).write({
                "state": "pending",
                "signature": False,
                "initials": False,
                "signature_method": False,
                "signed_date": False,
                "declined_reason": False,
                "ip_address": False,
                "user_agent": False,
                "signer_hash": False,
                "last_reminder_date": False,
                "access_token": secrets.token_urlsafe(32),
            })

    # ------------------------------------------------------------------
    # Invitations
    # ------------------------------------------------------------------
    def _invite(self, reminder=False):
        for item in self:
            item.sudo().write({
                "state": "sent" if item.state == "waiting" else item.state,
                "last_reminder_date": fields.Datetime.now(),
            })
            item.request_id._send_invitation_mail(item, reminder=reminder)
            self.env["sign.log"].sudo().create({
                "request_id": item.request_id.id,
                "request_item_id": item.id,
                "action": "reminded" if reminder else "sent",
            })

    def action_resend(self):
        if any(i.state not in ("sent", "viewed") or i.request_id.state != "sent" for i in self):
            raise UserError(_("Only pending signers can receive the invitation again."))
        self._invite(reminder=True)
        return True

    # ------------------------------------------------------------------
    # One-time codes
    # ------------------------------------------------------------------
    def _otp_digest(self, code):
        self.ensure_one()
        return hmac.new(self.sudo().access_token.encode(), code.encode(), hashlib.sha256).hexdigest()

    def _send_otp(self):
        self.ensure_one()
        signer = self.sudo()
        now = fields.Datetime.now()
        if signer.otp_sent_date and signer.otp_sent_date + OTP_RESEND_DELAY > now:
            raise UserError(_("A code was sent less than a minute ago. Please check your inbox."))
        code = f"{secrets.randbelow(10 ** 6):06d}"
        signer.write({
            "otp_hash": self._otp_digest(code),
            "otp_expiry": now + OTP_VALIDITY,
            "otp_sent_date": now,
            "otp_attempts": 0,
        })
        self._send_otp_code(code)
        self.env["sign.log"].sudo().create({
            "request_id": self.request_id.id,
            "request_item_id": self.id,
            "action": "otp_sent",
        })

    def _send_otp_code(self, code):
        """Deliver the code. Bridge modules override this for other channels."""
        self.ensure_one()
        self.request_id._send_otp_mail(self, code)

    def _check_otp(self, code):
        self.ensure_one()
        signer = self.sudo()
        if not signer.otp_hash or not signer.otp_expiry or signer.otp_expiry < fields.Datetime.now():
            raise UserError(_("The code has expired. Request a new one."))
        if signer.otp_attempts >= OTP_MAX_ATTEMPTS:
            raise UserError(_("Too many attempts. Request a new code."))
        if not hmac.compare_digest(signer.otp_hash, self._otp_digest((code or "").strip())):
            signer.otp_attempts += 1
            raise UserError(_("The code is not correct."))
        signer.write({"otp_hash": False, "otp_expiry": False})

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _compute_signer_hash(self):
        self.ensure_one()
        signature_digest = hashlib.sha256(self._binary_bytes(self.signature)).hexdigest()
        payload = "|".join([
            self.request_id.document_hash or "",
            str(self.id),
            (self.signer_email or "").lower(),
            fields.Datetime.to_string(self.signed_date),
            signature_digest,
        ])
        return hashlib.sha256(payload.encode()).hexdigest()

    def _sign(self, signature_png, method, initials_png=None, values=None, ip_address=None, user_agent=None):
        """Record the signature and the field values of this signer.

        ``signature_png`` / ``initials_png`` are raw PNG bytes, already validated.
        ``values`` maps ``sign.item`` ids of this signer to their values.
        """
        self.ensure_one()
        if self.state not in ("sent", "viewed") or self.request_id.state != "sent":
            raise UserError(_("This document can no longer be signed."))
        own_fields = self.request_id.item_ids.filtered(lambda f: f.request_item_id == self)
        own_fields._apply_signer_values(values or {})
        vals = {
            "state": "signed",
            "signed_date": fields.Datetime.now(),
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:250],
            "signature_method": method,
        }
        if signature_png:
            vals["signature"] = self._binary_value(signature_png)
        if initials_png:
            vals["initials"] = self._binary_value(initials_png)
        signer = self.sudo().with_context(easy_sign_force=True)
        signer.write(vals)
        signer.signer_hash = self._compute_signer_hash()
        self.env["sign.log"].sudo().create({
            "request_id": self.request_id.id,
            "request_item_id": self.id,
            "action": "signed",
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        self.request_id.sudo()._on_signer_signed()
        return True

    def action_decline(self, reason=None, ip_address=None, user_agent=None):
        """A refusal cancels the whole request, as in Odoo Sign."""
        self.ensure_one()
        if self.state not in ("sent", "viewed") or self.request_id.state != "sent":
            raise UserError(_("This document can no longer be declined."))
        self.sudo().write({
            "state": "declined",
            "declined_reason": reason,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:250],
        })
        self.env["sign.log"].sudo().create({
            "request_id": self.request_id.id,
            "request_item_id": self.id,
            "action": "declined",
            "ip_address": ip_address,
            "user_agent": user_agent,
            "notes": reason,
        })
        request = self.request_id.sudo()
        request.request_item_ids.filtered(lambda s: s != self and s.state != "signed").write(
            {"state": "cancelled"}
        )
        request.state = "cancelled"
        request._send_declined_mail(self)
        request.message_post(
            body=_("%(name)s declined to sign. The request has been cancelled.", name=self.signer_name),
            message_type="notification",
        )
        return True

    # Binary helpers: the only place that knows how binaries are stored (differs in 20.0).
    @api.model
    def _binary_bytes(self, value):
        return base64.b64decode(value) if value else b""

    @api.model
    def _binary_value(self, raw):
        return base64.b64encode(raw)
