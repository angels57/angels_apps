from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RULE_TYPES = [
    ("approve", "Ask for approval"),
    ("notify_submit", "Inform when sent"),
    ("notify_done", "Inform when approved"),
]


class AngelsFormRule(models.Model):
    """Who a request goes to, and when. Approval rules run one after another."""

    _name = "angels.form.rule"
    _description = "Form Routing Rule"
    _order = "form_id, sequence, id"

    form_id = fields.Many2one("angels.form", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    rule_type = fields.Selection(RULE_TYPES, string="Action", required=True, default="approve")
    assign_type = fields.Selection(
        [
            ("users", "Specific users"),
            ("group", "Members of a group"),
            ("field", "User chosen in the form"),
        ],
        string="Send To",
        required=True,
        default="users",
    )
    user_ids = fields.Many2many("res.users", string="Users", domain=[("share", "=", False)])
    group_id = fields.Many2one("res.groups", string="Group")
    user_field_id = fields.Many2one(
        "angels.form.field",
        string="User Question",
        ondelete="cascade",
        domain="[('form_id', '=', form_id), ('field_type', '=', 'user')]",
    )
    approval_rule = fields.Selection(
        [("any", "One person is enough"), ("all", "Everyone must approve")],
        string="Rule",
        required=True,
        default="any",
    )
    condition_match = fields.Selection(
        [("all", "All conditions"), ("any", "Any condition")],
        string="Apply When", required=True, default="all",
    )
    condition_ids = fields.One2many(
        "angels.form.condition", "rule_id", string="Only If", copy=False,
    )

    @api.constrains("assign_type", "user_ids", "group_id", "user_field_id")
    def _check_recipients(self):
        for rule in self:
            if rule.assign_type == "users" and not rule.user_ids:
                raise ValidationError(_("The rule %(rule)s needs at least one user.", rule=rule.name))
            if rule.assign_type == "group" and not rule.group_id:
                raise ValidationError(_("The rule %(rule)s needs a group.", rule=rule.name))
            if rule.assign_type == "field" and (
                rule.user_field_id.field_type != "user" or rule.user_field_id.form_id != rule.form_id
            ):
                raise ValidationError(
                    _("The rule %(rule)s needs a user question of the same form.", rule=rule.name)
                )

    def _applies(self, values):
        self.ensure_one()
        if not self.condition_ids:
            return True
        results = (condition._matches(values) for condition in self.condition_ids)
        return all(results) if self.condition_match == "all" else any(results)

    def _get_recipients(self, values):
        """Active internal users the rule sends the request to."""
        self.ensure_one()
        if self.assign_type == "users":
            users = self.user_ids
        elif self.assign_type == "group":
            users = self.group_id.all_user_ids
        else:
            users = self.env["res.users"].browse(values.get(self.user_field_id.id) or [])
        return users.sudo().exists().filtered(lambda u: u.active and not u.share)

    def _to_client(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "rule_type": self.rule_type,
            "assign_type": self.assign_type,
            "user_ids": self.user_ids.ids,
            "group_id": self.group_id.id,
            "user_field_id": self.user_field_id.id,
            "approval_rule": self.approval_rule,
            "match": self.condition_match,
            "conditions": [condition._to_client() for condition in self.condition_ids],
        }
