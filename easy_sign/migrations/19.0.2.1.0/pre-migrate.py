"""19.0.2.0.0 -> 19.0.2.1.0: sign.item.type.icon stops being a Font Awesome class.

Odoo 20 no longer loads Font Awesome in the backend, so the palette icons are
drawn by the module (static/src/icons/icons.css) and the field becomes a
selection of those keys. Map the old classes; anything else falls back to text.
"""
import json

FA_TO_ICON = {
    "fa-user": "user", "fa-user-o": "user", "fa-envelope": "email", "fa-envelope-o": "email",
    "fa-phone": "phone", "fa-mobile": "phone", "fa-building": "company", "fa-building-o": "company",
    "fa-font": "text", "fa-bars": "multiline", "fa-align-left": "multiline",
    "fa-check-square": "checkbox", "fa-check-square-o": "checkbox",
    "fa-dot-circle-o": "radio", "fa-circle-o": "radio", "fa-angle-down": "selection", "fa-caret-down": "selection",
    "fa-calendar": "date", "fa-calendar-o": "date", "fa-strikethrough": "strike", "fa-certificate": "stamp",
    "fa-id-card": "id_card", "fa-id-card-o": "id_card", "fa-id-badge": "id_card", "fa-hashtag": "number",
    "fa-map-marker": "location", "fa-star": "star", "fa-star-o": "star",
    "fa-pencil": "initials", "fa-pencil-square-o": "initials",
}


def migrate(cr, version):
    cr.execute("""
        UPDATE sign_item_type
           SET icon = CASE WHEN base_type = 'signature' THEN 'signature'
                           ELSE COALESCE((%s::jsonb) ->> icon, 'text') END
         WHERE icon IS NULL OR icon NOT IN %s
    """, [json.dumps(FA_TO_ICON), tuple(set(FA_TO_ICON.values()) | {"signature"})])
