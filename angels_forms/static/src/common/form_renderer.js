import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { visibleFieldIds } from "./conditions";
import { useProps, useState } from "./owl_compat";

const { DateTime } = luxon;
// Bootstrap columns of each width (angels.form.field.width).
export const WIDTH_COLS = { quarter: 3, third: 4, half: 6, two_thirds: 8, three_quarters: 9, full: 12 };
const RADIO_LIMIT = 4;
const MAX_FILE_SIZE = 25 * 1024 * 1024;

/**
 * The questions of a form, with live conditions. Used by the fill screen and
 * by the designer preview. Writes the answers into ``props.values``.
 */
export class FormRenderer extends Component {
    static template = "angels_forms.FormRenderer";
    static components = { RecordSelector };

    setup() {
        this.props = useProps(); // fields, values, errors, disabled
        // Subscribe to the parent's reactive objects; they are mutated, never replaced.
        this.fields = useState(this.props.fields);
        this.values = useState(this.props.values);
        this.errors = useState(this.props.errors || {});
        this.uid = Math.random().toString(36).slice(2, 8);
    }

    get visibleFields() {
        const visible = visibleFieldIds(this.fields, this.values);
        return this.fields.filter((f) => visible.has(String(f.id)));
    }

    key(field) {
        return String(field.id);
    }
    colClass(field) {
        return `col-12 col-md-${WIDTH_COLS[field.width] || 12} o_af_question`;
    }
    /** Read-only: the whole form, or a question another step fills. */
    isDisabled(field) {
        return Boolean(this.props.disabled) || field.editable === false;
    }
    inputId(field) {
        return `o_af_${this.uid}_${field.id}`;
    }
    value(field) {
        const value = this.values[this.key(field)];
        return value === false || value === undefined || value === null ? "" : value;
    }
    error(field) {
        return this.errors[this.key(field)];
    }
    useRadios(field) {
        return field.options.length <= RADIO_LIMIT;
    }

    set(field, value) {
        this.values[this.key(field)] = value;
        delete this.errors[this.key(field)];
    }
    onText(field, ev) {
        this.set(field, ev.target.value);
    }
    onNumber(field, ev) {
        const raw = ev.target.value;
        this.set(field, raw === "" ? false : Number(raw));
    }
    checked(field) {
        return Boolean(this.values[this.key(field)]);
    }
    onBoolean(field, ev) {
        this.set(field, ev.target.checked);
    }
    datetimeValue(field) {
        const value = this.value(field);
        return value ? deserializeDateTime(value).toFormat("yyyy-MM-dd'T'HH:mm") : "";
    }
    onDatetime(field, ev) {
        const raw = ev.target.value;
        this.set(field, raw ? serializeDateTime(DateTime.fromISO(raw)) : false);
    }
    recordId(field) {
        return this.values[this.key(field)] || false;
    }
    files(field) {
        return this.values[this.key(field)] || [];
    }
    async onFiles(field, ev) {
        const files = [...ev.target.files];
        ev.target.value = "";
        const added = [];
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE) {
                this.errors[this.key(field)] = _t("%s is larger than 25 MB.", file.name);
                continue;
            }
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            added.push({ name: file.name, data });
        }
        if (added.length) {
            this.set(field, [...this.files(field), ...added]);
        }
    }
    removeFile(field, index) {
        const files = [...this.files(field)];
        files.splice(index, 1);
        this.set(field, files);
    }
}
