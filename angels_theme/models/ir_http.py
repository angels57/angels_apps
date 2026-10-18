from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        if user and not user._is_public():
            info["angels_theme"] = {
                "density": user.angels_theme_density or "normal",
                "tab_style": user.angels_theme_tab_style or "underline",
            }
        return info
