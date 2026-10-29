from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    use_sign_terms = fields.Boolean(
        string="Sign Default Terms & Conditions", config_parameter="angels_sign.use_sign_terms",
    )
    sign_terms_type = fields.Selection(related="company_id.sign_terms_type", readonly=False)
    sign_terms = fields.Html(related="company_id.sign_terms", readonly=False)
    sign_terms_url = fields.Char(compute="_compute_sign_terms_url")
    group_manage_template_access = fields.Boolean(
        string="Manage template access", implied_group="angels_sign.group_manage_template_access",
    )
    signing_certificate_id = fields.Many2one(related="company_id.signing_certificate_id", readonly=False)

    def _compute_sign_terms_url(self):
        for settings in self:
            settings.sign_terms_url = f"{settings.get_base_url()}/sign/terms/{settings.company_id.id}"
