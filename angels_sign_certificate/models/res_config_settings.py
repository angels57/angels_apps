from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    signing_certificate_id = fields.Many2one(related="company_id.signing_certificate_id", readonly=False)
