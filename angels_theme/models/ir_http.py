from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        if user and not user._is_public():
            company = self.env.company
            image_url = False
            if company.angels_home_background == "image" and company.angels_home_image:
                image_url = "/web/image/res.company/%s/angels_home_image?unique=%s" % (
                    company.id,
                    int(company.write_date.timestamp()),
                )
            info["angels_theme"] = {
                "density": user.angels_theme_density or "normal",
                "tab_style": user.angels_theme_tab_style or "underline",
                "home_background": company.angels_home_background or "gradient",
                "home_image_url": image_url,
            }
        return info
