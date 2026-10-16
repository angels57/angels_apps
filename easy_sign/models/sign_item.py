import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

FIELD_TYPES = [
    ("signature", "Signature"),
    ("initials", "Initials"),
    ("text", "Text"),
    ("date", "Date"),
    ("checkbox", "Checkbox"),
    ("textarea", "Multiline Text"),
    ("radio", "Radio"),
    ("selection", "Selection"),
    ("strike", "Strikethrough"),
    ("stamp", "Stamp"),
]
IMAGE_TYPES = ("signature", "initials", "stamp")
MAX_TEXT = 2000

# Fields that templates may copy into a field value (``linked_field``).
LINKABLE_FIELDS = {
    "partner_id.name", "partner_id.email", "partner_id.phone", "partner_id.vat",
    "partner_id.street", "partner_id.city", "partner_id.zip", "partner_id.country_id.name",
    "partner_id.company_name", "name", "email", "phone", "vat", "street", "city", "zip",
}


class SignItem(models.Model):
    _name = "sign.item"
    _description = "Signature Field Placed on a Document"
    _order = "document_id, page, pos_y, pos_x, id"

    request_id = fields.Many2one("sign.request", ondelete="cascade", index=True)
    template_id = fields.Many2one("sign.template", ondelete="cascade", index=True)
    document_id = fields.Many2one("sign.document", required=True, ondelete="cascade", index=True)
    request_item_id = fields.Many2one("sign.request.item", string="Signer", ondelete="cascade")
    role_id = fields.Many2one("sign.role", string="Role", ondelete="cascade")
    type = fields.Selection(FIELD_TYPES, required=True, default="signature")
    page = fields.Integer(required=True, default=1)
    pos_x = fields.Float(required=True, digits=(6, 5))
    pos_y = fields.Float(required=True, digits=(6, 5))
    width = fields.Float(required=True, default=0.25, digits=(6, 5))
    height = fields.Float(required=True, default=0.06, digits=(6, 5))
    required = fields.Boolean(default=True)
    readonly = fields.Boolean()
    placeholder = fields.Char()
    options = fields.Text(help="One option per line (radio and selection).")
    value = fields.Text(copy=False)
    alignment = fields.Selection(
        [("left", "Left"), ("center", "Center"), ("right", "Right")], default="left", required=True,
    )
    linked_field = fields.Selection(
        selection=[(f, f) for f in sorted(LINKABLE_FIELDS)], string="Auto-complete",
        help="Fill the field with this value of the signer's contact.",
    )

    _page_positive = models.Constraint("CHECK (page >= 1)", "The page must be 1 or more.")
    _inside_page = models.Constraint(
        "CHECK (pos_x >= 0 AND pos_y >= 0 AND width > 0 AND height > 0 "
        "AND pos_x + width <= 1.0001 AND pos_y + height <= 1.0001)",
        "The field must stay inside the page.",
    )

    def _option_list(self):
        self.ensure_one()
        return [o.strip() for o in (self.options or "").splitlines() if o.strip()]

    @api.constrains("page", "document_id")
    def _check_page(self):
        for item in self:
            if item.document_id.page_count and item.page > item.document_id.page_count:
                raise ValidationError(_("Page %s does not exist in %s.", item.page, item.document_id.name))

    def _check_editable(self):
        if self.env.context.get("easy_sign_force"):
            return
        for item in self:
            if item.request_id and item.request_id.state != "draft":
                raise UserError(_("Fields cannot be changed once the request has been sent."))
            if item.template_id and item.template_id.request_count:
                raise UserError(_("This template has already been used. Edit a copy instead."))

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._check_editable()
        return items

    def write(self, vals):
        self._check_editable()
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        return super().unlink()

    def _autocomplete_value(self, signer):
        """Value suggested to ``signer`` for this field (linked contact data)."""
        self.ensure_one()
        if not self.linked_field or self.linked_field not in LINKABLE_FIELDS or not signer.partner_id:
            return self.value or ""
        path = self.linked_field.removeprefix("partner_id.")
        value = signer.partner_id.sudo().mapped(path)
        value = value[0] if value else ""
        return value.display_name if isinstance(value, models.BaseModel) else str(value or "")

    def _apply_signer_values(self, values):
        """Validate and store the values sent by the signer for these fields."""
        values = {int(k): v for k, v in (values or {}).items() if str(k).isdigit()}
        unknown = set(values) - set(self.ids)
        if unknown:
            raise UserError(_("Some fields do not belong to this signer."))
        for item in self:
            signer = item.request_item_id
            if item.readonly:
                raw = item._autocomplete_value(signer)
            else:
                raw = values.get(item.id, "")
            raw = raw if isinstance(raw, str) else ("1" if raw else "")
            value = item._clean_value(raw)
            if item.required and not value and item.type not in ("strike",):
                raise UserError(_("Please complete all the required fields."))
            item.with_context(easy_sign_force=True).sudo().value = value or False

    def _clean_value(self, raw):
        self.ensure_one()
        raw = (raw or "").strip()
        if self.type in ("signature", "initials", "checkbox", "strike"):
            return "1" if raw and raw not in ("0", "false") else ""
        if self.type == "date":
            if not raw:
                return ""
            try:
                return fields.Date.to_string(fields.Date.to_date(raw))
            except ValueError as exc:
                raise UserError(_("Invalid date.")) from exc
        if self.type in ("radio", "selection"):
            if raw and raw not in self._option_list():
                raise UserError(_("Invalid option."))
            return raw
        if self.type == "stamp":
            if not raw:
                return ""
            png = self.env["sign.request"]._validate_image(raw)
            return base64.b64encode(png).decode()
        if len(raw) > MAX_TEXT:
            raise UserError(_("The text is too long."))
        return raw

    def _public_data(self, signer):
        """Projection sent to the public signing page (no other signer's data)."""
        return [{
            "id": item.id,
            "doc": item.document_id.id,
            "page": item.page,
            "x": item.pos_x, "y": item.pos_y, "w": item.width, "h": item.height,
            "type": item.type,
            "required": item.required,
            "readonly": item.readonly,
            "placeholder": item.placeholder or "",
            "options": item._option_list(),
            "align": item.alignment,
            "value": item._autocomplete_value(signer) if item.type not in IMAGE_TYPES else "",
        } for item in self]

