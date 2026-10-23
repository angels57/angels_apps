from datetime import datetime

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

# Operators that make sense for each kind of value. Kept in sync with
# angels_forms/static/src/common/conditions.js.
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
# Kind of value of each type of Odoo field a condition can test.
FIELD_KINDS = {
    "char": "char",
    "text": "text",
    "html": "text",
    "integer": "number",
    "float": "number",
    "monetary": "number",
    "date": "date",
    "datetime": "datetime",
    "boolean": "boolean",
    "selection": "selection",
}
RELATION_KINDS = {"res.users": "user", "res.partner": "partner"}


def is_set(value):
    # Identity checks: 0 is a value, although 0 == False in Python.
    return not (value is None or value is False or value == "" or value == [])


def match_value(kind, actual, operator, raw, normalize):
    """Whether ``actual`` passes "``operator`` ``raw``" for a value of ``kind``.

    ``raw`` is the value typed in the condition; ``normalize`` turns it into
    the same type as ``actual``.
    """
    if operator == "set":
        return is_set(actual)
    if operator == "not_set":
        return not is_set(actual)
    if kind == "boolean":
        expected = (raw or "").strip().lower() in TRUE_WORDS
        return (bool(actual) == expected) == (operator == "=")
    if kind == "multi":
        # "contains": the choice is one of the ticked ones.
        ticked = [choice.lower() for choice in actual or []]
        return operator == "contains" and (raw or "").strip().lower() in ticked
    expected = normalize(raw)
    if not is_set(actual) or not is_set(expected):
        return operator == "!=" and is_set(actual) != is_set(expected)
    if kind in ("char", "text", "selection"):
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


def field_kind(field):
    """Kind of value of an ``ir.model.fields`` record, or None if no condition can test it."""
    if field.ttype == "many2one":
        return RELATION_KINDS.get(field.relation)
    return FIELD_KINDS.get(field.ttype)


def record_value(record, field):
    """The value of ``field`` on ``record``, as conditions compare it."""
    value = record[field.name]
    kind = field_kind(field)
    if kind in ("user", "partner"):
        return value.id or False
    if kind == "number":
        return float(value or 0)
    return value


class AngelsFlowCondition(models.Model):
    """One test on a field of the record a flow runs on."""

    _name = "angels.flow.condition"
    _description = "Flow Condition"
    _order = "id"

    node_id = fields.Many2one("angels.flow.node", string="Flow Step", required=True, ondelete="cascade", index=True)
    field_id = fields.Many2one("ir.model.fields", string="Field", required=True, ondelete="cascade")
    operator = fields.Selection(OPERATORS, required=True, default="=")
    value = fields.Char()

    @api.constrains("node_id", "field_id", "operator")
    def _check_condition(self):
        for condition in self:
            field = condition.field_id
            if field.model != condition.node_id.flow_id.model_name:
                raise ValidationError(_("A condition can only test a field of the flow's model."))
            kind = field_kind(field)
            if not kind:
                raise ValidationError(_("No condition can test the field %(field)s.", field=field.field_description))
            if condition.operator not in OPERATORS_BY_TYPE[kind]:
                raise ValidationError(_("The operator of the condition on %(field)s does not fit its type.",
                                        field=field.field_description))

    def _normalize(self, raw):
        kind = field_kind(self.field_id)
        if not is_set(raw):
            return False
        try:
            if kind == "number":
                return float(raw)
            if kind in ("user", "partner"):
                return int(raw)
            if kind == "date":
                return fields.Date.to_date(raw)
        except (TypeError, ValueError):
            return False
        return raw

    def _matches(self, values):
        """``values`` maps field names to values read by ``record_value``."""
        self.ensure_one()
        actual = values.get(self.field_id.name, False)
        if isinstance(actual, datetime) and field_kind(self.field_id) == "date":
            actual = actual.date()
        return match_value(field_kind(self.field_id), actual, self.operator, self.value, self._normalize)

    def _to_client(self):
        return {"source_id": self.field_id.id, "operator": self.operator, "value": self.value or ""}
