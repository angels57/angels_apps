from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

NODE_TYPES = [
    ("start", "Start"),
    ("condition", "Condition"),
    ("approve", "Approval"),
    ("task", "Task"),
    ("notify", "Notification"),
    ("back", "Back to Requester"),
    ("end", "End"),
]
# Output ports of each node type, and the field that stores where each one goes.
# The flow designer reads them from ``_flow_ports``.
PORTS = {
    "start": ("next",),
    "condition": ("yes", "no"),
    "approve": ("next", "reject"),
    "task": ("next",),
    "notify": ("next",),
    "back": (),
    "end": (),
}
PORT_FIELDS = {"next": "next_id", "yes": "yes_id", "no": "no_id", "reject": "reject_id"}
# Node types that reach people.
PEOPLE_TYPES = ("approve", "task", "notify")
# Context key to save a whole flow before checking its steps.
DEFER = "angels_flow_defer"


class AngelsFlowNodeMixin(models.AbstractModel):
    """One box of a flow. Documents walk the boxes from Start.

    The model that inherits it names the field of the record holding the flow
    (``_flow_container``) and declares the links, Many2one to itself:
    ``next_id``, ``yes_id``, ``no_id`` and ``reject_id``. Its constraint on
    them calls ``_check_flow_links``.
    """

    _name = "angels.flow.node.mixin"
    _description = "Flow Step"
    _flow_container = None

    name = fields.Char(required=True, translate=True)
    node_type = fields.Selection(NODE_TYPES, string="Type", required=True, default="approve")
    pos_x = fields.Integer()
    pos_y = fields.Integer()
    color = fields.Integer(help="Color of the step.")
    end_state = fields.Selection(
        [("approved", "Approved"), ("rejected", "Rejected")], string="Result", default="approved",
    )
    assign_type = fields.Selection(
        [("users", "Specific users"), ("group", "Members of a group")],
        string="Send To",
        default="users",
    )
    user_ids = fields.Many2many("res.users", string="Users", domain=[("share", "=", False)])
    group_id = fields.Many2one("res.groups", string="Group")
    approval_rule = fields.Selection(
        [("any", "One person is enough"), ("all", "Everyone must approve")],
        string="Rule",
        default="any",
    )
    condition_match = fields.Selection(
        [("all", "All conditions"), ("any", "Any condition")],
        string="Match", required=True, default="all",
    )

    @api.model
    def _flow_ports(self):
        """Output ports of each node type."""
        return PORTS

    def _flow_siblings(self):
        """Every step of the same flow."""
        self.ensure_one()
        container = self._flow_container
        return self.search([(container, "=", self[container].id)])

    @api.constrains("node_type")
    def _check_single_start(self):
        for node in self.filtered(lambda n: n.node_type == "start"):
            if len(node._flow_siblings().filtered(lambda n: n.node_type == "start")) > 1:
                raise ValidationError(_("A flow has only one Start."))

    def _check_flow_links(self):
        container = self._flow_container
        for node in self:
            targets = node.browse().union(*(node[name] for name in PORT_FIELDS.values()))
            if any(target[container] != node[container] for target in targets):
                raise ValidationError(_("A step can only lead to a step of the same flow."))
            if any(target.node_type == "start" for target in targets):
                raise ValidationError(_("No step can lead back to Start."))

    @api.constrains("node_type", "assign_type", "user_ids", "group_id")
    def _check_recipients(self):
        if self.env.context.get(DEFER):
            return
        for node in self.filtered(lambda n: n.node_type in PEOPLE_TYPES):
            if node.assign_type == "users" and not node.user_ids:
                raise ValidationError(_("The step %(step)s needs at least one user.", step=node.name))
            if node.assign_type == "group" and not node.group_id:
                raise ValidationError(_("The step %(step)s needs a group.", step=node.name))

    def _flow_condition_met(self, values):
        """Whether a Condition step goes to "Yes". ``values`` come from the document."""
        self.ensure_one()
        return True

    def _get_recipients(self, values):
        """Active internal users the step reaches."""
        self.ensure_one()
        if self.assign_type == "users":
            users = self.user_ids
        elif self.assign_type == "group":
            users = self.group_id.all_user_ids
        else:
            users = self.env["res.users"]
        return users.sudo().exists().filtered(lambda u: u.active and not u.share)

    def _to_client(self):
        """The step as the flow designer reads it."""
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type,
            "x": self.pos_x,
            "y": self.pos_y,
            "color": self.color,
            "links": {port: self[PORT_FIELDS[port]].id for port in self._flow_ports()[self.node_type]},
            "end_state": self.end_state or "approved",
            "assign_type": self.assign_type or "users",
            "user_ids": self.user_ids.ids,
            "group_id": self.group_id.id,
            "approval_rule": self.approval_rule or "any",
            "match": self.condition_match,
        }
