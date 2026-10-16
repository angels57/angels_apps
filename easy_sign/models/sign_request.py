import logging
import secrets
import string
from datetime import timedelta
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

CODE_ALPHABET = string.ascii_uppercase + string.digits


class SignRequest(models.Model):
    _name = "sign.request"
    _description = "Electronic Signature Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    active = fields.Boolean(default=True)
    template_id = fields.Many2one("sign.template", string="Template", readonly=True, index=True)
    document_ids = fields.One2many("sign.document", "request_id", string="Documents", copy=True)
    document_name = fields.Char(string="Document", compute="_compute_document_name")
    item_ids = fields.One2many("sign.item", "request_id", string="Fields")
    request_item_ids = fields.One2many("sign.request.item", "request_id", string="Signers")
    log_ids = fields.One2many("sign.log", "request_id", string="Audit Log")
    subject = fields.Char(string="Email Subject")
    message = fields.Html(string="Invitation Message")
    attachment_ids = fields.Many2many(
        "ir.attachment", "easy_sign_request_attachment_rel", "request_id", "attachment_id",
        string="Email Attachments",
        help="Extra files sent with the invitation email.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("signed", "Fully Signed"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status", default="draft", tracking=True, readonly=True, index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Requested By", default=lambda self: self.env.user,
        tracking=True, index=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", default=lambda self: self.env.company, required=True,
    )
    expiry_date = fields.Date(
        string="Valid Until", tracking=True,
        help="The signing links stop working after this date.",
    )
    signing_order = fields.Boolean(
        string="Signing Order",
        help="Signers receive the invitation one after the other, following the sequence.",
    )
    reminder_days = fields.Integer(
        string="Reminder Every (days)", default=0,
        help="Remind pending signers every N days. 0 disables reminders.",
    )
    cc_partner_ids = fields.Many2many(
        "res.partner", "easy_sign_request_cc_rel", "request_id", "partner_id",
        string="Copy To",
        help="Contacts that receive the signed document and the certificate.",
    )
    redirect_url = fields.Char(
        string="Redirect URL", help="Link shown to the signers after they sign.",
    )
    tag_ids = fields.Many2many("sign.tag", string="Tags")
    res_model = fields.Char(string="Related Model", readonly=True, index=True)
    res_id = fields.Many2oneReference(string="Related Record", model_field="res_model", readonly=True)
    origin_ref = fields.Reference(
        selection="_selection_origin_ref", string="Origin", compute="_compute_origin_ref",
    )
    document_hash = fields.Char(string="Document Hash (SHA-256)", readonly=True, copy=False)
    verification_code = fields.Char(string="Verification Code", readonly=True, copy=False, index=True)
    signed_document = fields.Binary(string="Signed Document", attachment=True, copy=False, readonly=True)
    signed_document_name = fields.Char(copy=False, readonly=True)
    signed_document_hash = fields.Char(
        string="Signed Document Hash (SHA-256)", readonly=True, copy=False, index=True,
    )
    certificate_pdf = fields.Binary(string="Certificate", attachment=True, copy=False, readonly=True)
    certificate_name = fields.Char(copy=False, readonly=True)
    completed_date = fields.Datetime(string="Completed On", readonly=True, copy=False)
    signers_count = fields.Integer(compute="_compute_signing_progress", store=True)
    signed_count = fields.Integer(compute="_compute_signing_progress", store=True)
    has_pending_signers = fields.Boolean(compute="_compute_has_pending_signers")

    _verification_code_unique = models.Constraint(
        "UNIQUE (verification_code)", "The verification code must be unique.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("document_ids.name")
    def _compute_document_name(self):
        for rec in self:
            rec.document_name = ", ".join(rec.document_ids.mapped("name"))


    @api.depends("request_item_ids.state")
    def _compute_signing_progress(self):
        for rec in self:
            items = rec.request_item_ids.filtered(lambda i: i.state != "cancelled")
            rec.signers_count = len(items)
            rec.signed_count = len(items.filtered(lambda i: i.state == "signed"))

    @api.depends("request_item_ids.state")
    def _compute_has_pending_signers(self):
        for rec in self:
            rec.has_pending_signers = any(s.state == "pending" for s in rec.request_item_ids)

    @api.model
    def _selection_origin_ref(self):
        return [(m.model, m.name) for m in self.env["ir.model"].sudo().search([])]

    @api.depends("res_model", "res_id")
    def _compute_origin_ref(self):
        for rec in self:
            if rec.res_model and rec.res_id and rec.res_model in self.env:
                rec.origin_ref = f"{rec.res_model},{rec.res_id}"
            else:
                rec.origin_ref = False

    @api.constrains("redirect_url")
    def _check_redirect_url(self):
        for rec in self:
            if rec.redirect_url and not rec.redirect_url.startswith(("http://", "https://")):
                raise ValidationError(_("The redirect URL must start with http:// or https://."))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("easy_sign.request") or "New"
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state not in ("draft", "cancelled") for rec in self):
            raise UserError(_("Only draft or cancelled requests can be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_ready_to_send(self, signers=None):
        """``signers``: the signers about to be invited (all by default)."""
        self.ensure_one()
        if not self.document_ids:
            raise UserError(_("Add at least one PDF document."))
        if not self.request_item_ids:
            raise UserError(_("Add at least one signer."))
        signers = self.request_item_ids if signers is None else signers
        if any(not s.signer_email for s in signers):
            raise UserError(_("Every signer needs an email address."))
        signers = self.request_item_ids
        orphans = self.item_ids.filtered(lambda f: f.request_item_id not in signers)
        if orphans:
            raise UserError(_("Some fields are not assigned to a signer of this request."))

    def _activate(self):
        """Freeze the documents: from now on the request can be signed."""
        self.ensure_one()
        self._lock_documents()
        self.write({"state": "sent", "verification_code": self._new_verification_code()})

    def action_send(self):
        """Invite the signers not invited yet (all of them for a draft)."""
        for rec in self:
            pending = rec.request_item_ids.filtered(lambda s: s.state == "pending")
            if rec.state not in ("draft", "sent") or not pending:
                raise UserError(_("There is nobody left to invite."))
            rec._check_ready_to_send(pending)
            if rec.state == "draft":
                rec._activate()
            pending.write({"state": "waiting"})
            rec._invite_next_signers()
            rec.message_post(body=_("Signature request sent."), message_type="notification")
        return True

    def _new_verification_code(self):
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _i in range(10))
            if not self.sudo().search_count([("verification_code", "=", code)]):
                return code

    def _invite_next_signers(self):
        """Invite the signers whose turn it is (all of them without signing order)."""
        self.ensure_one()
        waiting = self.request_item_ids.filtered(lambda s: s.state == "waiting")
        if not waiting:
            return
        if self.signing_order:
            if self.request_item_ids.filtered(lambda s: s.state in ("sent", "viewed")):
                return
            first = min(waiting.mapped("sequence"))
            waiting = waiting.filtered(lambda s: s.sequence == first)
        waiting._invite()

    def _on_signer_signed(self):
        self.ensure_one()
        active = self.request_item_ids.filtered(lambda s: s.state != "cancelled")
        if active and all(s.state == "signed" for s in active):
            self._complete()
        else:
            self._invite_next_signers()

    def _complete(self):
        self.ensure_one()
        self.write({"state": "signed", "completed_date": fields.Datetime.now()})
        self._finalize_documents()
        self.env["sign.log"].sudo().create({
            "request_id": self.id,
            "action": "completed",
        })
        self.message_post(
            body=_("All signers have signed. The signed document and its certificate are available."),
            message_type="notification",
        )
        self._post_to_origin()
        self._send_completed_mail()

    def _post_to_origin(self):
        """Attach the signed document and the certificate to the originating record."""
        self.ensure_one()
        if not (self.res_model and self.res_id and self.res_model in self.env):
            return
        record = self.env[self.res_model].sudo().browse(self.res_id).exists()
        if not record or not hasattr(record, "message_post"):
            return
        record.message_post(
            body=_("Document signed with Easy Sign: %s", self.name),
            attachment_ids=self._completion_attachments().ids,
            message_type="notification",
        )

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft", "sent"):
                raise UserError(_("Only draft or sent requests can be cancelled."))
            pending = rec.request_item_ids.filtered(lambda s: s.state in ("sent", "viewed"))
            rec.request_item_ids.filtered(lambda s: s.state != "signed").write({"state": "cancelled"})
            rec.state = "cancelled"
            for signer in pending:
                rec._send_cancelled_mail(signer)
            self.env["sign.log"].sudo().create({"request_id": rec.id, "action": "cancelled"})
            rec.message_post(body=_("Signature request cancelled."), message_type="notification")
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ("cancelled", "expired"):
                raise UserError(_("Only cancelled or expired requests can be reset to draft."))
            rec.request_item_ids._reset_for_draft()
            rec.item_ids.with_context(easy_sign_force=True).write({"value": False})
            rec.document_ids.with_context(easy_sign_force=True).write({"file_hash": False})
            rec.write({
                "state": "draft",
                "document_hash": False,
                "verification_code": False,
            })
        return True

    def action_download_signed(self):
        self.ensure_one()
        if not self.signed_document:
            raise UserError(_("The signed document is not available yet."))
        name = quote(self.signed_document_name or "signed.pdf")
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/sign.request/{self.id}/signed_document/{name}?download=true",
            "target": "self",
        }

    def action_download_certificate(self):
        self.ensure_one()
        if not self.certificate_pdf:
            raise UserError(_("The certificate is not available yet."))
        name = quote(self.certificate_name or "certificate.pdf")
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/sign.request/{self.id}/certificate_pdf/{name}?download=true",
            "target": "self",
        }

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------
    @api.model
    def _cron_expire_requests(self):
        today = fields.Date.context_today(self)
        expired = self.search([("state", "=", "sent"), ("expiry_date", "<", today)])
        for rec in expired:
            rec.state = "expired"
            rec.request_item_ids.filtered(lambda s: s.state in ("pending", "waiting", "sent", "viewed")).write(
                {"state": "cancelled"}
            )
            self.env["sign.log"].sudo().create({
                "request_id": rec.id, "action": "expired",
            })
        return len(expired)

    @api.model
    def _cron_send_reminders(self, batch_size=200):
        Signer = self.env["sign.request.item"]
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        domain = [
            ("state", "in", ("sent", "viewed")),
            ("request_id.state", "=", "sent"),
            ("request_id.reminder_days", ">", 0),
            "|", ("request_id.expiry_date", "=", False), ("request_id.expiry_date", ">=", today),
        ]
        last_id = 0
        sent = 0
        while True:
            signers = Signer.search(domain + [("id", ">", last_id)], order="id", limit=batch_size)
            if not signers:
                break
            last_id = signers[-1].id
            due = signers.filtered(
                lambda s: not s.last_reminder_date
                or s.last_reminder_date + timedelta(days=s.request_id.reminder_days) <= now
            )
            due._invite(reminder=True)
            sent += len(due)
            if self.env.context.get("ir_cron_progress_id"):
                remaining = Signer.search_count(domain + [("id", ">", last_id)])
                if not self.env["ir.cron"]._commit_progress(len(signers), remaining=remaining):
                    break
        return sent
