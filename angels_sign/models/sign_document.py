import hashlib
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.pdf import PdfReader

from ..utils.compat import binary_bytes


class SignDocument(models.Model):
    _name = "sign.document"
    _description = "Signature Document (PDF)"
    _order = "sequence, id"

    request_id = fields.Many2one("sign.request", ondelete="cascade", index=True)
    template_id = fields.Many2one("sign.template", ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="File Name", required=True, default="document.pdf")
    file = fields.Binary(string="PDF", attachment=True, required=True)
    page_count = fields.Integer(compute="_compute_page_count", store=True)
    file_hash = fields.Char(string="SHA-256", readonly=True, copy=False)

    _owner_check = models.Constraint(
        "CHECK (request_id IS NOT NULL OR template_id IS NOT NULL)",
        "A document belongs to a request or a template.",
    )

    def _get_bytes(self):
        self.ensure_one()
        return binary_bytes(self.file)

    @api.depends("file")
    def _compute_page_count(self):
        for doc in self:
            try:
                doc.page_count = len(PdfReader(io.BytesIO(doc._get_bytes())).pages) if doc.file else 0
            except Exception:  # noqa: BLE001 - invalid files are rejected by the constraint
                doc.page_count = 0

    @api.constrains("file")
    def _check_pdf(self):
        for doc in self:
            data = doc._get_bytes()
            if not data.startswith(b"%PDF"):
                raise ValidationError(_("%s is not a PDF file.", doc.name))
            try:
                PdfReader(io.BytesIO(data))
            except Exception as exc:  # noqa: BLE001
                raise ValidationError(_("%s cannot be read as a PDF.", doc.name)) from exc

    def _compute_file_hash(self):
        for doc in self:
            doc.with_context(angels_sign_force=True).file_hash = hashlib.sha256(doc._get_bytes()).hexdigest()

    def _check_editable(self):
        if self.env.context.get("angels_sign_force"):
            return
        for doc in self:
            if doc.request_id and doc.request_id.state != "draft":
                raise UserError(_("Documents cannot be changed once the request has been sent."))
            if doc.template_id and doc.template_id.request_count:
                raise UserError(_("This template has already been used. Edit a copy instead."))

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        docs._check_editable()
        return docs

    def write(self, vals):
        self._check_editable()
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        return super().unlink()
