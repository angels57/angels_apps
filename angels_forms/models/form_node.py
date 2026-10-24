from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.angels_flow.models.flow_node import DEFER

# Node types where people fill questions.
STAGE_TYPES = ("approve", "task")


class AngelsFormNode(models.Model):
    """One box of a form's flow. Requests walk the boxes from Start."""

    _name = "angels.form.node"
    _inherit = ["angels.flow.node.mixin"]
    _description = "Form Flow Step"
    _order = "form_id, id"
    _flow_container = "form_id"

    form_id = fields.Many2one("angels.form", required=True, ondelete="cascade", index=True)
    color = fields.Integer(help="Color of the step and of the questions it fills.")
    next_id = fields.Many2one("angels.form.node", string="Then", ondelete="set null")
    yes_id = fields.Many2one("angels.form.node", string="If Yes", ondelete="set null")
    no_id = fields.Many2one("angels.form.node", string="If No", ondelete="set null")
    reject_id = fields.Many2one(
        "angels.form.node", string="If Rejected", ondelete="set null",
        help="Where a rejected request goes. Empty: the request is rejected.",
    )
    expired_id = fields.Many2one(
        "angels.form.node", string="If Expired", ondelete="set null",
        help="Where a late step goes when its deadline says so. Empty: the request is rejected.",
    )
    assign_type = fields.Selection(
        selection_add=[("field", "User chosen in the form")], ondelete={"field": "set default"},
    )
    user_field_id = fields.Many2one(
        "angels.form.field",
        string="User Question",
        ondelete="set null",
        domain="[('form_id', '=', form_id), ('field_type', '=', 'user')]",
    )
    condition_ids = fields.One2many("angels.form.condition", "node_id", string="Conditions", copy=False)
    field_ids = fields.One2many("angels.form.field", "node_id", string="Questions to Fill", copy=False)

    @api.constrains("next_id", "yes_id", "no_id", "reject_id", "expired_id", "form_id")
    def _check_links(self):
        self._check_flow_links()

    @api.constrains("node_type", "assign_type", "user_field_id")
    def _check_user_question(self):
        if self.env.context.get(DEFER):
            return
        for node in self.filtered(lambda n: n.node_type in ("approve", "task", "notify")):
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

    def _flow_condition_met(self, values):
        self.ensure_one()
        if not self.condition_ids:
            return True
        results = (condition._matches(values) for condition in self.condition_ids)
        return all(results) if self.condition_match == "all" else any(results)

    def _get_recipients(self, values):
        self.ensure_one()
        if self.assign_type != "field":
            return super()._get_recipients(values)
        users = self.env["res.users"].browse(values.get(self.user_field_id.id) or [])
        return users.sudo().exists().filtered(lambda u: u.active and not u.share)

    def _to_client(self):
        data = super()._to_client()
        data.update({
            "user_field_id": self.user_field_id.id,
            "conditions": [condition._to_client() for condition in self.condition_ids],
        })
        return data
