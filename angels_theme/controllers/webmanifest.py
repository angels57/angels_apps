from odoo.addons.web.controllers.webmanifest import WebManifest

BRAND = "#534ab7"
ICON = "/angels_theme/static/img/app_icon_%s.png"


class AngelsWebManifest(WebManifest):
    """Installed app (PWA): the theme icon and brand color instead of Odoo's."""

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest["background_color"] = BRAND
        manifest["theme_color"] = BRAND
        for icon in manifest["icons"]:
            icon["src"] = ICON % icon["sizes"].split("x")[0]
        return manifest

    def _icon_path(self):
        # Offline page and the fallback icon of the per-app shortcuts.
        return "angels_theme/static/img/app_icon_192.png"
