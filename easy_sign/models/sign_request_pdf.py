import base64
import hashlib
import io
import logging

from PIL import Image

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date
from odoo.tools.pdf import PdfReader, PdfWriter

from ..utils.compat import binary_value
from ..utils.pdf_overlay import PageOverlay

_logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_SIZE = (1200, 600)


class SignRequest(models.Model):
    _inherit = "sign.request"

    # ------------------------------------------------------------------
    # Images sent by signers
    # ------------------------------------------------------------------
    def _validate_image(self, data):
        """Accept a data URL or base64 PNG/JPEG; return clean PNG bytes."""
        if not data:
            return b""
        if "," in data[:100]:
            data = data.split(",", 1)[1]
        try:
            raw = base64.b64decode(data, validate=True)
        except ValueError as exc:
            raise UserError(_("The image is not valid.")) from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise UserError(_("The image is larger than 2 MB."))
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except Exception as exc:  # noqa: BLE001
            raise UserError(_("The file is not an image.")) from exc
        if img.format not in ("PNG", "JPEG"):
            raise UserError(_("Use a PNG or JPEG image."))
        img.thumbnail(MAX_IMAGE_SIZE)
        out = io.BytesIO()
        img.convert("RGBA").save(out, format="PNG")  # re-encoding drops metadata
        return out.getvalue()

    # ------------------------------------------------------------------
    # Hashes
    # ------------------------------------------------------------------
    def _lock_documents(self):
        self.ensure_one()
        self.document_ids._compute_file_hash()
        joined = "".join(self.document_ids.mapped("file_hash"))
        self.document_hash = hashlib.sha256(joined.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Signed PDF
    # ------------------------------------------------------------------
    def _footer_text(self):
        return _("Easy Sign · %(code)s · %(hash)s", code=self.verification_code, hash=(self.document_hash or "")[:16])

    def _draw_field(self, overlay, field):
        signer = field.request_item_id
        box = overlay.box(field.pos_x, field.pos_y, field.width, field.height)
        frame = (signer.signer_hash or "")[:16]
        if field.type == "signature" and field.value:
            overlay.image(signer._binary_bytes(signer.signature), box, frame)
        elif field.type == "initials" and field.value:
            overlay.image(signer._binary_bytes(signer.initials or signer.signature), box, frame)
        elif field.type == "stamp" and field.value:
            overlay.image(base64.b64decode(field.value), box, frame)
        elif field.type == "checkbox":
            overlay.check(box, field.value == "1")
        elif field.type == "strike":
            if field.value == "1":
                overlay.strike(box)
        elif field.type == "radio":
            overlay.radio(field._option_list(), field.value, box)
        elif field.type == "date" and field.value:
            overlay.text(format_date(self.env, field.value), box, field.alignment)
        elif field.type in ("text", "selection", "textarea"):
            overlay.text(field.value or "", box, field.alignment, multiline=field.type == "textarea")

    def _draw_legacy_grid(self, overlay, signers):
        """Signers without placed fields: signatures in a grid at the bottom of the last page."""
        sig_w, sig_h, margin_x, margin_y, gap = 150, 56, 40, 34, 18
        cols = max(1, int((overlay.dw - 2 * margin_x) / (sig_w + gap)))
        for idx, signer in enumerate(signers):
            x = margin_x + (idx % cols) * (sig_w + gap)
            y = margin_y + (idx // cols) * (sig_h + gap + 18)
            overlay.image(signer._binary_bytes(signer.signature), (x, y, sig_w, sig_h), (signer.signer_hash or "")[:16])
            overlay.caption(signer.signer_name or "", x, y - 9)
            if signer.signed_date:
                overlay.caption(fields.Datetime.to_string(signer.signed_date) + " UTC", x, y - 16, 5.5)

    def _build_signed_pdf(self):
        self.ensure_one()
        writer = PdfWriter()
        signed = self.request_item_ids.filtered(lambda s: s.state == "signed")
        legacy = signed.filtered(lambda s: s not in self.item_ids.request_item_id)
        docs = self.document_ids
        for doc in docs:
            reader = PdfReader(io.BytesIO(doc._get_bytes()))
            last_index = len(reader.pages) - 1
            doc_fields = self.item_ids.filtered(lambda f: f.document_id == doc)
            for index, page in enumerate(reader.pages):
                overlay = PageOverlay(page)
                for field in doc_fields.filtered(lambda f: f.page == index + 1):
                    self._draw_field(overlay, field)
                if legacy and doc == docs[-1] and index == last_index:
                    self._draw_legacy_grid(overlay, legacy)
                overlay.footer(self._footer_text())
                page.merge_page(PdfReader(io.BytesIO(overlay.render())).pages[0])
                writer.add_page(page)
        return writer

    def _render_certificate(self):
        self.ensure_one()
        try:
            pdf, _type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
                "easy_sign.action_report_certificate", res_ids=self.ids,
            )
        except Exception:  # noqa: BLE001 - never block the signature because of the report
            _logger.exception("Easy Sign: certificate rendering failed for %s", self.name)
            return b""
        return pdf if pdf and pdf.startswith(b"%PDF") else b""

    def _easy_sign_post_process_pdf(self, pdf_bytes):
        """Hook for bridge modules (cryptographic signature). Returns PDF bytes."""
        return pdf_bytes

    def _finalize_documents(self):
        self.ensure_one()
        writer = self._build_signed_pdf()
        certificate = self._render_certificate()
        if certificate:
            for page in PdfReader(io.BytesIO(certificate)).pages:
                writer.add_page(page)
        writer.add_metadata({
            "/Title": self.document_name or self.name,
            "/Subject": _("Signed with Easy Sign - verification code %s", self.verification_code),
            "/Creator": "Easy Sign - Odoo 19",
        })
        out = io.BytesIO()
        writer.write(out)
        final = self._easy_sign_post_process_pdf(out.getvalue())
        base_name = (self.document_ids[:1].name or "document.pdf").rsplit(".", 1)[0]
        self.with_context(easy_sign_force=True).write({
            "signed_document": binary_value(final),
            "signed_document_name": f"{base_name}_signed.pdf",
            "signed_document_hash": hashlib.sha256(final).hexdigest(),
            "certificate_pdf": binary_value(certificate),
            "certificate_name": f"{base_name}_certificate.pdf" if certificate else False,
        })
