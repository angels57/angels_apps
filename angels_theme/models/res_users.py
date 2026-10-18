from odoo import fields, models

THEME_FIELDS = ["angels_theme_density", "angels_theme_tab_style"]


class ResUsers(models.Model):
    _inherit = "res.users"

    angels_theme_density = fields.Selection(
        [
            ("compact", "Compact"),
            ("normal", "Normal"),
            ("comfortable", "Comfortable"),
        ],
        string="Density",
        default="normal",
        required=True,
        help="Spacing of lists and forms in the backend.",
    )
    angels_theme_tab_style = fields.Selection(
        [
            ("underline", "Underline"),
            ("pill", "Pill"),
        ],
        string="Tab Style",
        default="underline",
        required=True,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + THEME_FIELDS

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + THEME_FIELDS

    def preference_save(self):
        # The theme is applied when the web client boots, so reload the page.
        return {"type": "ir.actions.client", "tag": "reload"}
