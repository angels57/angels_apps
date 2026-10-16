import { _t } from "@web/core/l10n/translation";

export const TYPE_LABEL = {
    signature: _t("Signature"), initials: _t("Initials"), text: _t("Text"), textarea: _t("Multiline"),
    checkbox: _t("Checkbox"), radio: _t("Radio"), selection: _t("Selection"), date: _t("Date"),
    strike: _t("Strikethrough"), stamp: _t("Stamp"),
};

export const LINKED_LABEL = {
    "partner_id.name": _t("Name"), "partner_id.email": _t("Email"), "partner_id.phone": _t("Phone"),
    "partner_id.parent_id.name": _t("Company"), "partner_id.city": _t("City"), "partner_id.vat": _t("Tax ID"),
    "partner_id.street": _t("Street"), "partner_id.zip": _t("ZIP"), "partner_id.country_id.name": _t("Country"),
    "partner_id.company_name": _t("Company Name"),
};

/** Label of a placed field: its palette entry, else its auto-complete or type. */
export function itemLabel(item, palette = []) {
    const entry = item.item_type_id && palette.find((e) => e.id === item.item_type_id);
    return entry ? entry.label : LINKED_LABEL[item.linked_field] || TYPE_LABEL[item.type] || item.type;
}

/** Values of a new field created from a palette entry (sign.item.type). */
export function newItemVals(entry) {
    return {
        type: entry.type,
        item_type_id: entry.id,
        width: entry.size[0],
        height: entry.size[1],
        linked_field: entry.linked || false,
        required: entry.required,
        readonly: entry.readonly,
        placeholder: entry.placeholder || "",
        options: ["radio", "selection"].includes(entry.type) ? `${_t("Option 1")}\n${_t("Option 2")}` : false,
    };
}

export const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
