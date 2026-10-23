from odoo import _, api, fields, models

VALUE_FIELDS = {
    "char": "value_char",
    "selection": "value_char",
    "text": "value_text",
    "multi": "value_text",
    "number": "value_number",
    "date": "value_date",
    "datetime": "value_datetime",
    "boolean": "value_boolean",
    "user": "value_user_id",
    "partner": "value_partner_id",
    "file": "attachment_ids",
}


class AngelsFormAnswer(models.Model):
    """Only questions that were answered have an answer: empty means no record."""

    _name = "angels.form.answer"
    _description = "Form Answer"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one(
        "angels.form.submission", required=True, ondelete="cascade", index=True, readonly=True,
    )
    field_id = fields.Many2one(
        "angels.form.field", string="Question", required=True, ondelete="cascade", readonly=True,
        context={"active_test": False},
    )
    sequence = fields.Integer(related="field_id.sequence")
    field_type = fields.Selection(related="field_id.field_type")
    value_char = fields.Char(readonly=True)
    value_text = fields.Text(readonly=True)
    value_number = fields.Float(readonly=True)
    value_date = fields.Date(readonly=True)
    value_datetime = fields.Datetime(readonly=True)
    value_boolean = fields.Boolean(readonly=True)
    value_user_id = fields.Many2one("res.users", readonly=True)
    value_partner_id = fields.Many2one("res.partner", readonly=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Files", readonly=True)
    display_value = fields.Char(string="Answer", compute="_compute_display_value")

    _one_answer_per_field = models.Constraint(
        "unique(submission_id, field_id)", "A question is answered only once per request.",
    )

    @api.depends("field_id", *set(VALUE_FIELDS.values()))
    def _compute_display_value(self):
        for answer in self:
            answer.display_value = answer._format()

    def _format(self):
        self.ensure_one()
        kind = self.field_type
        if kind == "boolean":
            return _("Yes") if self.value_boolean else _("No")
        value = self._get_value()
        if value is False:
            return ""
        if kind == "date":
            return fields.Date.to_string(value)
        if kind == "datetime":
            return fields.Datetime.to_string(fields.Datetime.context_timestamp(self, value))[:16]
        if kind == "user":
            return self.value_user_id.sudo().name
        if kind == "partner":
            return self.value_partner_id.sudo().display_name
        if kind == "file":
            return ", ".join(self.attachment_ids.mapped("name"))
        if kind == "multi":
            return ", ".join(value)
        if kind == "number":
            number = ("%.2f" % value).rstrip("0").rstrip(".")
            return " ".join(part for part in (self.field_id.prefix, number, self.field_id.suffix) if part)
        return value

    def _get_value(self):
        """Normalized value, the same shape ``angels.form.field._normalize`` returns."""
        self.ensure_one()
        kind = self.field_type
        if kind in ("user", "partner"):
            return self[VALUE_FIELDS[kind]].id or False
        if kind == "file":
            return self.attachment_ids.ids or False
        if kind == "multi":
            return [line for line in (self.value_text or "").splitlines() if line] or False
        return self[VALUE_FIELDS[kind]] if kind in VALUE_FIELDS else False

    def _value_vals(self, field, value):
        """Write values for ``value`` (normalized) on an answer to ``field``."""
        kind = field.field_type
        vals = {name: False for name in set(VALUE_FIELDS.values()) if name != "attachment_ids"}
        if kind == "file":
            vals["attachment_ids"] = [fields.Command.set(value or [])]
        elif kind == "multi":
            vals["value_text"] = "\n".join(value or [])
        elif kind in VALUE_FIELDS:
            vals[VALUE_FIELDS[kind]] = value
        return vals

    def _to_client(self):
        self.ensure_one()
        kind = self.field_type
        value = self._get_value()
        if kind == "file":
            return [
                {"id": a.id, "name": a.name, "size": a.file_size, "mimetype": a.mimetype}
                for a in self.attachment_ids
            ]
        if kind == "date" and value:
            return fields.Date.to_string(value)
        if kind == "datetime" and value:
            return fields.Datetime.to_string(value)
        return value
