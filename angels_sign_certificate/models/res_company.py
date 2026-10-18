from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Field name expected by odoo.tools.pdf.signature.PdfSigner.
    signing_certificate_id = fields.Many2one(
        "certificate.certificate", string="PDF Signing Certificate",
        domain="[('company_id', '=', id)]",
        help="Certificate used to sign the documents completed with Easy Sign.",
    )
