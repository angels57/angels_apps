from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sign_terms_type = fields.Selection(
        [("plain", "Terms in Email"), ("html", "Terms as Web Page")],
        string="Terms Display", default="plain", required=True,
    )
    sign_terms = fields.Html(string="Sign Terms & Conditions", translate=True, sanitize=True)
