from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    use_sign_terms = fields.Boolean(
        string="Sign Default Terms & Conditions", config_parameter="easy_sign.use_sign_terms",
    )
    sign_terms_type = fields.Selection(related="company_id.sign_terms_type", readonly=False)
    sign_terms = fields.Html(related="company_id.sign_terms", readonly=False)
    sign_terms_url = fields.Char(compute="_compute_sign_terms_url")
    group_manage_template_access = fields.Boolean(
        string="Manage template access", implied_group="easy_sign.group_manage_template_access",
    )
    module_easy_sign_sms = fields.Boolean(string="Authenticate by SMS")
    module_easy_sign_certificate = fields.Boolean(string="Cryptographic signature")

    def _compute_sign_terms_url(self):
        for settings in self:
            settings.sign_terms_url = f"{settings.get_base_url()}/sign/terms/{settings.company_id.id}"
