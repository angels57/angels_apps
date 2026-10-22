from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .form_condition import TRUE_WORDS, is_set
from .form_node import STAGE_TYPES

FIELD_TYPES = [
    ("section", "Section"),
    ("char", "Text"),
    ("text", "Long Text"),
    ("number", "Number"),
    ("date", "Date"),
    ("datetime", "Date and Time"),
    ("boolean", "Checkbox"),
    ("selection", "Choice List"),
    ("user", "User"),
    ("partner", "Contact"),
    ("file", "File"),
]

# Share of the row a question takes; static/src/common/form_renderer.js maps them to columns.
WIDTHS = [
    ("quarter", "1/4"),
    ("third", "1/3"),
    ("half", "1/2"),
    ("two_thirds", "2/3"),
    ("three_quarters", "3/4"),
    ("full", "Full width"),
]


class AngelsFormField(models.Model):
    _name = "angels.form.field"
    _description = "Form Field"
    _order = "form_id, sequence, id"

    form_id = fields.Many2one("angels.form", required=True, ondelete="cascade", index=True)
    # Fields that already have answers are archived instead of deleted.
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Label", required=True, translate=True)
    field_type = fields.Selection(FIELD_TYPES, string="Type", required=True, default="char")
    required = fields.Boolean()
    help = fields.Char(string="Help Text", translate=True)
    placeholder = fields.Char(translate=True)
    # Not translated: conditions compare answers with these exact words.
    options = fields.Text(help="Choices of a choice list, one per line.")
    width = fields.Selection(WIDTHS, required=True, default="full")
    node_id = fields.Many2one(
        "angels.form.node",
        string="Filled By",
        ondelete="set null",
        copy=False,
        domain="[('form_id', '=', form_id), ('node_type', 'in', ('approve', 'task'))]",
        help="Flow step whose people fill this question. Empty: the requester fills it.",
    )
    condition_match = fields.Selection(
        [("all", "All conditions"), ("any", "Any condition")],
        string="Show When", required=True, default="all",
    )
    condition_ids = fields.One2many(
        "angels.form.condition", "field_id", string="Show Only If", copy=False,
    )

    @api.constrains("node_id", "form_id")
    def _check_node(self):
        for field in self.filtered("node_id"):
            if field.node_id.form_id != field.form_id or field.node_id.node_type not in STAGE_TYPES:
                raise ValidationError(
                    _("%(field)s can only be filled by an approval or task step of the same form.",
                      field=field.name)
                )

    @api.constrains("field_type", "options")
    def _check_options(self):
        for field in self:
            if field.field_type == "selection" and not field._option_list():
                raise ValidationError(_("The choice list %(field)s needs at least one choice.",
                                        field=field.name))

    def _position(self):
        self.ensure_one()
        return (self.sequence, self.id)

    def _option_list(self):
        self.ensure_one()
        return [line.strip() for line in (self.options or "").splitlines() if line.strip()]

    def _conditions_met(self, values):
        self.ensure_one()
        if not self.condition_ids:
            return True
        results = (condition._matches(values) for condition in self.condition_ids)
        return all(results) if self.condition_match == "all" else any(results)

    def _normalize(self, raw):
        """Answer as sent by the browser or stored in a condition, in a comparable form."""
        self.ensure_one()
        kind = self.field_type
        if not is_set(raw) and kind != "boolean":
            return False
        if kind in ("char", "text", "selection"):
            return str(raw).strip() or False
        if kind == "number":
            try:
                return float(raw)
            except (TypeError, ValueError):
                raise ValidationError(_("%(field)s must be a number.", field=self.name)) from None
        if kind in ("date", "datetime"):
            convert = fields.Date.to_date if kind == "date" else fields.Datetime.to_datetime
            try:
                return convert(raw)
            except (TypeError, ValueError):
                raise ValidationError(_("%(field)s is not a valid date.", field=self.name)) from None
        if kind == "boolean":
            return raw.strip().lower() in TRUE_WORDS if isinstance(raw, str) else bool(raw)
        if kind in ("user", "partner"):
            try:
                return int(raw)
            except (TypeError, ValueError):
                raise ValidationError(_("%(field)s is not valid.", field=self.name)) from None
        if kind == "file":
            return list(raw) if isinstance(raw, (list, tuple)) else False
        return False

    def _to_client(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "type": self.field_type,
            "required": self.required,
            "help": self.help or "",
            "placeholder": self.placeholder or "",
            "options": self._option_list(),
            "width": self.width,
            "node_id": self.node_id.id,
            "match": self.condition_match,
            "conditions": [condition._to_client() for condition in self.condition_ids],
        }
