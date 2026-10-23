from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

OPERATORS = [
    ("=", "is"),
    ("!=", "is not"),
    (">", "greater than"),
    (">=", "greater or equal"),
    ("<", "less than"),
    ("<=", "less or equal"),
    ("contains", "contains"),
    ("set", "is filled"),
    ("not_set", "is empty"),
]

# Operators that make sense for each kind of question. Kept in sync with
# static/src/common/conditions.js.
OPERATORS_BY_TYPE = {
    "char": ("=", "!=", "contains", "set", "not_set"),
    "text": ("contains", "set", "not_set"),
    "number": ("=", "!=", ">", ">=", "<", "<=", "set", "not_set"),
    "date": ("=", "!=", ">", ">=", "<", "<=", "set", "not_set"),
    "datetime": ("set", "not_set"),
    "boolean": ("=", "!="),
    "selection": ("=", "!=", "set", "not_set"),
    "multi": ("contains", "set", "not_set"),
    "user": ("=", "!=", "set", "not_set"),
    "partner": ("=", "!=", "set", "not_set"),
    "file": ("set", "not_set"),
}
TRUE_WORDS = ("1", "true", "yes")


def is_set(value):
    # Identity checks: 0 is an answer, although 0 == False in Python.
    return not (value is None or value is False or value == "" or value == [])


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
        actual = values.get(source.id, False)
        operator = self.operator
        if operator == "set":
            return is_set(actual)
        if operator == "not_set":
            return not is_set(actual)
        if source.field_type == "boolean":
            expected = (self.value or "").strip().lower() in TRUE_WORDS
            return (bool(actual) == expected) == (operator == "=")
        if source.field_type == "multi":
            # "contains": the choice is one of the ticked ones.
            ticked = [choice.lower() for choice in actual or []]
            return operator == "contains" and (self.value or "").strip().lower() in ticked
        expected = source._normalize(self.value)
        if not is_set(actual) or not is_set(expected):
            return operator == "!=" and is_set(actual) != is_set(expected)
        if source.field_type in ("char", "text", "selection"):
            actual, expected = actual.lower(), expected.lower()
        if operator == "=":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == "contains":
            return expected in actual
        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        return False

    def _to_client(self):
        return {"source_id": self.source_field_id.id, "operator": self.operator, "value": self.value or ""}
