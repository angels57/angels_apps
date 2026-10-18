from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    angels_home_background = fields.Selection(
        [
            ("gradient", "Brand Gradient"),
            ("plain", "Plain"),
            ("image", "Image"),
        ],
        string="Home Background",
        default="gradient",
        required=True,
        help="Background of the home screen that lists the apps.",
    )
    angels_home_image = fields.Image(
        string="Home Image",
        max_width=1920,
        max_height=1920,
    )
