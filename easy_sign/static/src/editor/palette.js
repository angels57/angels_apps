import { _t } from "@web/core/l10n/translation";

/** Field palette. Name/Email/Phone/Company are text fields pre-filled from the signer's contact. */
export const PALETTE = [
    { key: "signature", label: _t("Signature"), icon: "fa-pencil-square-o", type: "signature", size: [0.25, 0.06] },
    { key: "initials", label: _t("Initials"), icon: "fa-pencil-square-o", type: "initials", size: [0.08, 0.04] },
    { key: "name", label: _t("Name"), icon: "fa-user", type: "text", linked: "partner_id.name", size: [0.25, 0.03] },
    { key: "email", label: _t("Email"), icon: "fa-envelope-o", type: "text", linked: "partner_id.email", size: [0.25, 0.03] },
    { key: "phone", label: _t("Phone"), icon: "fa-phone", type: "text", linked: "partner_id.phone", size: [0.2, 0.03] },
    { key: "company", label: _t("Company"), icon: "fa-building-o", type: "text", linked: "partner_id.parent_id.name", size: [0.25, 0.03] },
    { key: "text", label: _t("Text"), icon: "fa-font", type: "text", size: [0.25, 0.03] },
    { key: "textarea", label: _t("Multiline"), icon: "fa-bars", type: "textarea", size: [0.35, 0.08] },
    { key: "checkbox", label: _t("Checkbox"), icon: "fa-check-square-o", type: "checkbox", size: [0.025, 0.02] },
    { key: "radio", label: _t("Radio"), icon: "fa-dot-circle-o", type: "radio", size: [0.2, 0.08] },
    { key: "selection", label: _t("Selection"), icon: "fa-angle-down", type: "selection", size: [0.2, 0.03] },
    { key: "date", label: _t("Date"), icon: "fa-calendar", type: "date", size: [0.15, 0.03] },
    { key: "strike", label: _t("Strikethrough"), icon: "fa-strikethrough", type: "strike", size: [0.3, 0.015] },
    { key: "stamp", label: _t("Stamp"), icon: "fa-certificate", type: "stamp", size: [0.15, 0.1] },
];

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

export function itemLabel(item) {
    return LINKED_LABEL[item.linked_field] || TYPE_LABEL[item.type] || item.type;
}

export function newItemVals(entry) {
    return {
        type: entry.type,
        width: entry.size[0],
        height: entry.size[1],
        linked_field: entry.linked || false,
        required: !["checkbox", "strike"].includes(entry.type),
        options: ["radio", "selection"].includes(entry.type) ? `${_t("Option 1")}\n${_t("Option 2")}` : false,
    };
}

export const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
