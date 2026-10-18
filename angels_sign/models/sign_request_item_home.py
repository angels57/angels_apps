from odoo import api, models


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    # Counter on the Angels Sign tile of the angels_theme home screen. The
    # theme looks these up by name, so this module does not depend on it.
    _angels_home_badge_app = "angels_sign.menu_angels_sign_root"

    @api.model
    def _angels_home_badge_count(self):
        """Documents the current user still has to sign."""
        return self.search_count([
            ("partner_id", "=", self.env.user.partner_id.id),
            ("state", "in", ("sent", "viewed")),
            ("request_id.state", "=", "sent"),
        ])
