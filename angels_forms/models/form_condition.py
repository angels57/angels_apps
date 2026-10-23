from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.angels_flow.models.flow_condition import (
    OPERATORS,
    OPERATORS_BY_TYPE,
    TRUE_WORDS,
    is_set,
    match_value,
)

# Re-exported for the other models of this module.
__all__ = ["OPERATORS", "OPERATORS_BY_TYPE", "TRUE_WORDS", "is_set"]


class AngelsFormCondition(models.Model):
    """One test on an answer. Owned by a field (show it only if ...) or a flow condition."""

    _name = "angels.form.condition"
    _description = "Form Condition"
    _order = "id"

    field_id = fields.Many2one("angels.form.field", ondelete="cascade", index=True)
    node_id = fields.Many2one("angels.form.node", string="Flow Step", ondelete="cascade", index=True)
    source_field_id = fields.Many2one(
        "angels.form.field", string="Question", required=True, ondelete="cascade",
    )
    operator = fields.Selection(OPERATORS, required=True, default="=")
    value = fields.Char()

    @api.constrains("field_id", "node_id", "source_field_id", "operator")
    def _check_condition(self):
        for condition in self:
            owner_form = condition.field_id.form_id or condition.node_id.form_id
            source = condition.source_field_id
            if bool(condition.field_id) == bool(condition.node_id):
                raise ValidationError(_("A condition belongs to one field or to one flow step."))
            if source.form_id != owner_form:
                raise ValidationError(_("A condition can only test a question of the same form."))
            if source.field_type == "section":
                raise ValidationError(_("A condition cannot test a section."))
            if condition.operator not in OPERATORS_BY_TYPE[source.field_type]:
                raise ValidationError(
                    _("The operator of the condition on %(question)s does not fit its type.",
                      question=source.name)
                )
            target = condition.field_id
            if target and source._position() >= target._position():
                raise ValidationError(
                    _("%(field)s can only depend on questions placed before it, not on %(source)s.",
                      field=target.name, source=source.name)
                )

    def _matches(self, values):
        """``values`` maps field ids to answers normalized by the field."""
        self.ensure_one()
        source = self.source_field_id
        return match_value(source.field_type, values.get(source.id, False), self.operator, self.value, source._normalize)

    def _to_client(self):
        return {"source_id": self.source_field_id.id, "operator": self.operator, "value": self.value or ""}
