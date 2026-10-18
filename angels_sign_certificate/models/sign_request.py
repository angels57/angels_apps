import io
import logging

from odoo import models
from odoo.tools.pdf.signature import PdfSigner

_logger = logging.getLogger(__name__)


class SignRequest(models.Model):
    _inherit = "sign.request"

    def _angels_sign_post_process_pdf(self, pdf_bytes):
        pdf_bytes = super()._angels_sign_post_process_pdf(pdf_bytes)
        company = self.company_id.sudo()
        if not company.signing_certificate_id:
            return pdf_bytes
        try:
            signed = PdfSigner(io.BytesIO(pdf_bytes), company=company).sign_pdf(field_name="Angels Sign")
        except Exception:  # noqa: BLE001 - keep the unsigned PDF rather than losing the signature
            _logger.exception("Angels Sign: certificate signature failed for %s", self.name)
            return pdf_bytes
        return signed.getvalue() if signed else pdf_bytes
