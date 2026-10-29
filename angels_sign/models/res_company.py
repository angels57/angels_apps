from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sign_terms_type = fields.Selection(
        [("plain", "Terms in Email"), ("html", "Terms as Web Page")],
        string="Terms Display", default="plain", required=True,
    )
    sign_terms = fields.Html(string="Sign Terms & Conditions", translate=True, sanitize=True)
    # Field name expected by odoo.tools.pdf.signature.PdfSigner.
    signing_certificate_id = fields.Many2one(
        "certificate.certificate", string="PDF Signing Certificate",
        domain="[('company_id', '=', id)]",
        help="Certificate used to sign the documents completed with Angels Sign.",
    )
