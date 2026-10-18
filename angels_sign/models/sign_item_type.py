from odoo import api, fields, models

from .sign_item import FIELD_TYPES, LINKED_SELECTION

# Field Size: default width of a new field, as a fraction of the page.
FIELD_SIZES = {"short": 0.15, "regular": 0.25, "long": 0.4}

# Palette icons, drawn by static/src/icons/icons.css (class o_es_i_<key>).
ICONS = [
    ("signature", "Signature"), ("initials", "Pen"), ("user", "Person"), ("email", "Envelope"),
    ("phone", "Phone"), ("company", "Building"), ("text", "Text"), ("multiline", "Lines"),
    ("checkbox", "Checkbox"), ("radio", "Radio"), ("selection", "Drop-down"), ("date", "Calendar"),
    ("strike", "Strikethrough"), ("stamp", "Stamp"), ("id_card", "ID Card"), ("number", "Number"),
    ("location", "Location"), ("star", "Star"),
]


class SignItemType(models.Model):
    """Entries of the editor palette (Signature, Name, Email... and custom ones)."""
    _name = "sign.item.type"
    _description = "Signature Field Type"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    base_type = fields.Selection(FIELD_TYPES, string="Type", required=True, default="text")
    icon = fields.Selection(ICONS, default="text", help="Icon of the field in the editor palette.")
    linked_field = fields.Selection(
        selection=LINKED_SELECTION, string="Field",
        help="Value of the signer's contact that fills this field.",
    )
    update_field = fields.Boolean(
        string="Update Field",
        help="Write the value entered by the signer back to their contact.",
    )
    tip = fields.Char(
        translate=True,
        help="Text of the guide ribbon on the signing page, for example 'Fill in'. Empty: automatic.",
    )
    alignment = fields.Selection(
        [("left", "Left"), ("center", "Center"), ("right", "Right")], default="left", required=True,
    )
    field_size = fields.Selection(
        [("short", "Short Text"), ("regular", "Regular Text"), ("long", "Long Text")],
        compute="_compute_field_size", inverse="_inverse_field_size",
        help="Default width of a new field of this type.",
    )
    default_width = fields.Float(default=0.25, digits=(6, 5))
    default_height = fields.Float(default=0.03, digits=(6, 5))
    required = fields.Boolean(string="Mandatory", default=True)
    readonly = fields.Boolean(string="Read Only")
    placeholder = fields.Char(translate=True)
    linked_model = fields.Char(string="Linked to", compute="_compute_linked")
    linked_field_name = fields.Char(string="Linked Field", compute="_compute_linked")

    _size_check = models.Constraint(
        "CHECK (default_width > 0 AND default_width <= 1 AND default_height > 0 AND default_height <= 1)",
        "The default size is a fraction of the page (0-1).",
    )

    @api.depends("default_width")
    def _compute_field_size(self):
        for item_type in self:
            item_type.field_size = min(FIELD_SIZES, key=lambda size: abs(FIELD_SIZES[size] - item_type.default_width))

    def _inverse_field_size(self):
        for item_type in self.filtered("field_size"):
            item_type.default_width = FIELD_SIZES[item_type.field_size]

    @api.depends("linked_field")
    def _compute_linked(self):
        # Every auto-complete value comes from the signer's contact.
        for item_type in self:
            item_type.linked_model = self.env._("Contact") if item_type.linked_field else False
            item_type.linked_field_name = (item_type.linked_field or "").removeprefix("partner_id.") or False

    @api.model
    def _editor_palette(self):
        return [{
            "id": t.id,
            "label": t.name,
            "icon": t.icon or "text",
            "type": t.base_type,
            "linked": t.linked_field or False,
            "size": [t.default_width, t.default_height],
            "required": t.required,
            "readonly": t.readonly,
            "placeholder": t.placeholder or "",
            "alignment": t.alignment,
        } for t in self.search([])]
