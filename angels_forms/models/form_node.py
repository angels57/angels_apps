from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

NODE_TYPES = [
    ("start", "Start"),
    ("condition", "Condition"),
    ("approve", "Approval"),
    ("task", "Task"),
    ("notify", "Notification"),
    ("record", "Create Record"),
    ("back", "Back to Requester"),
    ("end", "End"),
]
# Output ports of each node type, and the field that stores where each one goes.
# Kept in sync with static/src/designer/flow_editor.js.
PORTS = {
    "start": ("next",),
    "condition": ("yes", "no"),
    "approve": ("next", "reject"),
    "task": ("next",),
    "notify": ("next",),
    "record": ("next",),
    "back": (),
    "end": (),
}
PORT_FIELDS = {"next": "next_id", "yes": "yes_id", "no": "no_id", "reject": "reject_id"}
# Node types that reach people, and the ones where people fill questions.
PEOPLE_TYPES = ("approve", "task", "notify")
STAGE_TYPES = ("approve", "task")


class AngelsFormNode(models.Model):
    """One box of a form's flow. Requests walk the boxes from Start."""

    _name = "angels.form.node"
    _description = "Form Flow Step"
    _order = "form_id, id"

    form_id = fields.Many2one("angels.form", required=True, ondelete="cascade", index=True)
    name = fields.Char(required=True, translate=True)
    node_type = fields.Selection(NODE_TYPES, string="Type", required=True, default="approve")
    pos_x = fields.Integer()
    pos_y = fields.Integer()
    color = fields.Integer(help="Color of the step and of the questions it fills.")
    next_id = fields.Many2one("angels.form.node", string="Then", ondelete="set null")
    yes_id = fields.Many2one("angels.form.node", string="If Yes", ondelete="set null")
    no_id = fields.Many2one("angels.form.node", string="If No", ondelete="set null")
    reject_id = fields.Many2one(
        "angels.form.node", string="If Rejected", ondelete="set null",
        help="Where a rejected request goes. Empty: the request is rejected.",
    )
    end_state = fields.Selection(
        [("approved", "Approved"), ("rejected", "Rejected")], string="Result", default="approved",
    )
    assign_type = fields.Selection(
        [
            ("users", "Specific users"),
            ("group", "Members of a group"),
            ("field", "User chosen in the form"),
        ],
        string="Send To",
        default="users",
    )
    user_ids = fields.Many2many("res.users", string="Users", domain=[("share", "=", False)])
    group_id = fields.Many2one("res.groups", string="Group")
    user_field_id = fields.Many2one(
        "angels.form.field",
        string="User Question",
        ondelete="set null",
        domain="[('form_id', '=', form_id), ('field_type', '=', 'user')]",
    )
    approval_rule = fields.Selection(
        [("any", "One person is enough"), ("all", "Everyone must approve")],
        string="Rule",
        default="any",
    )
    condition_match = fields.Selection(
        [("all", "All conditions"), ("any", "Any condition")],
        string="Match", required=True, default="all",
    )
    condition_ids = fields.One2many("angels.form.condition", "node_id", string="Conditions", copy=False)
    field_ids = fields.One2many("angels.form.field", "node_id", string="Questions to Fill", copy=False)

    @api.constrains("node_type", "form_id")
    def _check_single_start(self):
        for node in self.filtered(lambda n: n.node_type == "start"):
            starts = node.form_id.node_ids.filtered(lambda n: n.node_type == "start")
            if len(starts) > 1:
                raise ValidationError(_("A flow has only one Start."))

    @api.constrains("next_id", "yes_id", "no_id", "reject_id", "form_id")
    def _check_links(self):
        for node in self:
            targets = node.next_id | node.yes_id | node.no_id | node.reject_id
            if any(target.form_id != node.form_id for target in targets):
                raise ValidationError(_("A step can only lead to a step of the same flow."))
            if any(target.node_type == "start" for target in targets):
                raise ValidationError(_("No step can lead back to Start."))

    @api.constrains("node_type", "assign_type", "user_ids", "group_id", "user_field_id")
    def _check_recipients(self):
        if self.env.context.get("angels_forms_defer"):
            return
        for node in self.filtered(lambda n: n.node_type in PEOPLE_TYPES):
            if node.assign_type == "users" and not node.user_ids:
                raise ValidationError(_("The step %(step)s needs at least one user.", step=node.name))
            if node.assign_type == "group" and not node.group_id:
                raise ValidationError(_("The step %(step)s needs a group.", step=node.name))
            if node.assign_type == "field" and (
                node.user_field_id.field_type != "user" or node.user_field_id.form_id != node.form_id
            ):
                raise ValidationError(
                    _("The step %(step)s needs a user question of the same form.", step=node.name)
                )

    @api.model
    def _translate_default_names(self):
        """Start and End steps created with an English name get it in every installed language."""
        langs = [code for code, _name in self.env["res.lang"].get_installed() if code != "en_US"]
        defaults = ("Request Sent", "Approved", "Rejected")
        for node in self.with_context(lang="en_US").search([("node_type", "in", ("start", "end"))]):
            source = node.name
            if source not in defaults:
                continue
            for lang in langs:
                localized = node.with_context(lang=lang)
                if localized.name == source:
                    localized.name = localized.env._(source)

    def _conditions_met(self, values):
        self.ensure_one()
        if not self.condition_ids:
            return True
        results = (condition._matches(values) for condition in self.condition_ids)
        return all(results) if self.condition_match == "all" else any(results)

    def _get_recipients(self, values):
        """Active internal users the step reaches."""
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
            "type": self.node_type,
            "x": self.pos_x,
            "y": self.pos_y,
            "color": self.color,
            "links": {port: self[PORT_FIELDS[port]].id for port in PORTS[self.node_type]},
            "end_state": self.end_state or "approved",
            "assign_type": self.assign_type or "users",
            "user_ids": self.user_ids.ids,
            "group_id": self.group_id.id,
            "user_field_id": self.user_field_id.id,
            "approval_rule": self.approval_rule or "any",
            "match": self.condition_match,
            "conditions": [condition._to_client() for condition in self.condition_ids],
        }
