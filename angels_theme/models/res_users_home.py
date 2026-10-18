import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

XMLID_RE = re.compile(r"^[a-z0-9_]+\.[a-zA-Z0-9_]+$")
MAX_APPS = 200


class ResUsers(models.Model):
    _inherit = "res.users"

    angels_home_prefs = fields.Json(
        string="Home Screen Layout",
        help="Pinned apps and app order of the home screen, by menu XML id.",
    )

    # = Layout (favorites and order)

    @api.model
    def _angels_clean_xmlids(self, values):
        if not isinstance(values, list) or len(values) > MAX_APPS:
            raise ValidationError(self.env._("Invalid home screen layout."))
        clean = []
        for value in values:
            if not isinstance(value, str) or not XMLID_RE.match(value):
                raise ValidationError(self.env._("Invalid home screen layout."))
            if value not in clean:
                clean.append(value)
        return clean

    @api.model
    def angels_home_save_prefs(self, prefs):
        """Save the current user's home layout: {"favorites": [...], "order": [...]}."""
        if not isinstance(prefs, dict):
            raise ValidationError(self.env._("Invalid home screen layout."))
        clean = {
            "favorites": self._angels_clean_xmlids(prefs.get("favorites", [])),
            "order": self._angels_clean_xmlids(prefs.get("order", [])),
        }
        # Only the user's own record, with validated values.
        self.env.user.sudo().angels_home_prefs = clean
        return clean

    # = Badges

    @api.model
    def angels_home_badges(self):
        """Counters shown on the home screen tiles, as {app menu XML id: count}.

        Two sources are added up:
        * the user's activities due today or overdue, on the app that opens
          their model;
        * any model that declares `_angels_home_badge_app` (an app menu XML
          id) and implements `_angels_home_badge_count()`, so other addons can
          add their own counter without depending on this one.
        """
        badges = {}
        for app_xmlid, count in self._angels_activity_badges().items():
            badges[app_xmlid] = badges.get(app_xmlid, 0) + count
        for model_name, Model in self.env.registry.items():
            app_xmlid = getattr(Model, "_angels_home_badge_app", None)
            if not app_xmlid or getattr(Model, "_abstract", False):
                continue
            try:
                count = self.env[model_name]._angels_home_badge_count()
            except AccessError:
                continue
            if count:
                badges[app_xmlid] = badges.get(app_xmlid, 0) + count
        return badges

    @api.model
    def _angels_activity_badges(self):
        if "mail.activity" not in self.env:
            return {}
        groups = self.env["mail.activity"]._read_group(
            [("user_id", "=", self.env.uid), ("date_deadline", "<=", fields.Date.context_today(self))],
            ["res_model"],
            ["__count"],
        )
        if not groups:
            return {}
        app_of_model = self._angels_app_of_model()
        badges = {}
        for res_model, count in groups:
            app_xmlid = app_of_model.get(res_model)
            if app_xmlid:
                badges[app_xmlid] = badges.get(app_xmlid, 0) + count
        return badges

    @api.model
    def _angels_app_of_model(self):
        """Map each model to the visible app that opens it closest to its root.

        A model reachable from several apps (contacts, for instance) belongs to
        the one where its menu is shallowest, then to the first app in order.
        """
        menus = self.env["ir.ui.menu"].search([("action", "!=", False)])
        roots = self.env["ir.ui.menu"].search([("parent_id", "=", False)])
        root_rank = {root.id: rank for rank, root in enumerate(roots)}
        root_xmlids = roots.get_external_id()
        best = {}
        for menu in menus.sudo():
            action = menu.action
            if not action or action._name != "ir.actions.act_window" or not action.res_model:
                continue
            path = [int(part) for part in menu.parent_path.split("/") if part]
            root_id = path[0]
            if root_id not in root_rank or not root_xmlids.get(root_id):
                continue
            key = (len(path), root_rank[root_id])
            current = best.get(action.res_model)
            if current is None or key < current[0]:
                best[action.res_model] = (key, root_xmlids[root_id])
        return {model: xmlid for model, (key, xmlid) in best.items()}
