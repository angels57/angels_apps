from odoo import api, fields, models

from .sign_item import FIELD_TYPES, LINKABLE_FIELDS


class SignItemType(models.Model):
    """Entries of the editor palette (Signature, Name, Email... and custom ones)."""
    _name = "sign.item.type"
    _description = "Signature Field Type"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    base_type = fields.Selection(FIELD_TYPES, string="Type", required=True, default="text")
    icon = fields.Char(default="fa-font", help="Font Awesome class, for example fa-user.")
    linked_field = fields.Selection(
        selection=[(f, f) for f in sorted(LINKABLE_FIELDS)], string="Auto-complete",
    )
    default_width = fields.Float(default=0.25, digits=(6, 5))
    default_height = fields.Float(default=0.03, digits=(6, 5))
    required = fields.Boolean(default=True)
    readonly = fields.Boolean()
    placeholder = fields.Char(translate=True)

    _size_check = models.Constraint(
        "CHECK (default_width > 0 AND default_width <= 1 AND default_height > 0 AND default_height <= 1)",
        "The default size is a fraction of the page (0-1).",
    )

    @api.model
    def _editor_palette(self):
        return [{
            "id": t.id,
            "label": t.name,
            "icon": t.icon or "fa-font",
            "type": t.base_type,
            "linked": t.linked_field or False,
            "size": [t.default_width, t.default_height],
            "required": t.required,
            "readonly": t.readonly,
            "placeholder": t.placeholder or "",
        } for t in self.search([])]
