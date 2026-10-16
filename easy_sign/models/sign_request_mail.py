from odoo import _, models


class SignRequest(models.Model):
    _inherit = "sign.request"

    def _mail_from(self):
        self.ensure_one()
        return self.user_id.email_formatted or self.company_id.email_formatted or self.env.company.email_formatted

    def _render_mail(self, template, values, partner=None):
        lang = (partner and partner.lang) or self.user_id.lang or self.env.lang
        values = dict(values, sign_request=self, company=self.company_id)
        return self.env["ir.qweb"].with_context(lang=lang)._render(f"easy_sign.{template}", values)

    def _send_mail(self, email_to, subject, body, attachments=None):
        if not email_to:
            return
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "email_from": self._mail_from(),
            "email_to": email_to,
            "body_html": body,
            "attachment_ids": [(6, 0, (attachments or self.env["ir.attachment"]).ids)],
            "auto_delete": True,
        })
        mail.send(raise_exception=False)

    def _send_invitation_mail(self, signer, reminder=False):
        self.ensure_one()
        subject = self.subject or _("Please sign: %s", self.document_name or self.name)
        if reminder:
            subject = _("Reminder: %s", subject)
        body = self._render_mail("mail_invitation", {
            "signer": signer,
            "sign_url": signer.sudo().sign_url,
            "reminder": reminder,
        }, signer.partner_id)
        self._send_mail(signer.signer_email, subject, body, self.attachment_ids)

    def _send_otp_mail(self, signer, code):
        self.ensure_one()
        body = self._render_mail("mail_otp", {"signer": signer, "code": code}, signer.partner_id)
        self._send_mail(signer.signer_email, _("Your signing code: %s", code), body)

    def _completion_attachments(self):
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()
        attachments = Attachment.browse()
        for field, name in (("signed_document", self.signed_document_name),
                            ("certificate_pdf", self.certificate_name)):
            if self[field]:
                attachments |= Attachment.create({
                    "name": name,
                    "datas": self[field],
                    "res_model": "sign.request",
                    "res_id": self.id,
                    "mimetype": "application/pdf",
                })
        return attachments

    def _send_completed_mail(self):
        self.ensure_one()
        attachments = self._completion_attachments()
        subject = _("Signed: %s", self.document_name or self.name)
        recipients = [(self.user_id.partner_id, self.user_id.email)]
        recipients += [(s.partner_id, s.signer_email) for s in self.request_item_ids if s.state == "signed"]
        recipients += [(p, p.email) for p in self.cc_partner_ids]
        seen = set()
        for partner, email in recipients:
            if not email or email.lower() in seen:
                continue
            seen.add(email.lower())
            body = self._render_mail("mail_completed", {}, partner)
            self._send_mail(email, subject, body, attachments)

    def _send_declined_mail(self, signer):
        self.ensure_one()
        body = self._render_mail("mail_declined", {"signer": signer}, self.user_id.partner_id)
        self._send_mail(
            self.user_id.email,
            _("%(name)s declined to sign: %(doc)s", name=signer.signer_name, doc=self.document_name or self.name),
            body,
        )

    def _send_cancelled_mail(self, signer):
        self.ensure_one()
        body = self._render_mail("mail_cancelled", {"signer": signer}, signer.partner_id)
        self._send_mail(signer.signer_email, _("Cancelled: %s", self.document_name or self.name), body)
