import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { isSet, visibleFieldIds } from "./conditions";
import { layoutItems, spanOf } from "./layout";
import { useProps, useState } from "./owl_compat";

const { DateTime } = luxon;
// Up to this many choices show as cards; more get a search box.
const CARD_LIMIT = 6;
const MAX_FILE_SIZE = 25 * 1024 * 1024;
// Icon inside the input of each kind of question.
export const CONTROL_ICONS = {
    char: "fa-font",
    number: "fa-hashtag",
    date: "fa-calendar",
    datetime: "fa-clock-o",
    user: "fa-user",
    partner: "fa-address-book-o",
    selection: "fa-search",
};

/**
 * The questions of a form, with live conditions. Used by the fill screen and
 * by the designer's Test mode. Writes the answers into ``props.values``.
 *
 * Every question looks the same: label (required mark or "optional"), help,
 * then a control made for its type. Read-only questions (filled by another
 * step) show their answer as text. With ``progress``, a bar counts the
 * answers, and sections fold and show a check once their questions are done.
 */
export class FormRenderer extends Component {
    static template = "angels_forms.FormRenderer";
    static components = { RecordSelector };

    setup() {
        this.props = useProps(); // fields, values, errors, disabled, progress
        // Subscribe to the parent's reactive objects; they are mutated, never replaced.
        this.fields = useState(this.props.fields);
        this.values = useState(this.props.values);
        this.errors = useState(this.props.errors || {});
        this.ui = useState({ folded: {}, dragOver: false });
        this.uid = Math.random().toString(36).slice(2, 8);
    }

    get visibleFields() {
        const visible = visibleFieldIds(this.fields, this.values);
        return this.fields.filter((f) => visible.has(String(f.id)));
    }
    /** Visible questions placed on the grid; the questions of a folded section are left out. */
    get items() {
        let folded = false;
        return layoutItems(this.visibleFields).filter(({ field }) => {
            if (field.type === "section") {
                folded = Boolean(this.ui.folded[field.id]);
                return true;
            }
            return !folded;
        });
    }
    /** Questions the user answers here, for the progress bar. Checkboxes always have an answer. */
    get countedFields() {
        return this.visibleFields.filter((f) => f.type !== "section" && f.type !== "boolean" && !this.isDisabled(f));
    }
    get progress() {
        const fields = this.countedFields;
        const done = fields.filter((f) => this.isDone(f)).length;
        return { done, total: fields.length, percent: fields.length ? Math.round((done * 100) / fields.length) : 100 };
    }
    get progressText() {
        const { done, total } = this.progress;
        return _t("%(done)s of %(total)s answered", { done, total });
    }

    key(field) {
        return String(field.id);
    }
    colClass(item) {
        const offset = item.offset ? ` offset-md-${item.offset}` : "";
        return `col-12 col-md-${spanOf(item.field)}${offset} o_af_question`;
    }
    questionClass(field) {
        return {
            o_af_q_error: Boolean(this.error(field)),
            o_af_q_done: this.isDone(field),
            o_af_q_readonly: this.isDisabled(field),
        };
    }
    /** Read-only: the whole form, or a question another step fills. */
    isDisabled(field) {
        return Boolean(this.props.disabled) || field.editable === false;
    }
    isDone(field) {
        return field.type !== "boolean" && !this.isDisabled(field) && isSet(this.values[this.key(field)]);
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
    icon(field) {
        return CONTROL_ICONS[field.type] || "fa-pencil";
    }
    useCards(field) {
        return field.options.length <= CARD_LIMIT;
    }
    /** The answer as plain text, for a question the user cannot change. */
    readonlyText(field) {
        const value = this.values[this.key(field)];
        if (field.type === "boolean") {
            return value ? _t("Yes") : _t("No");
        }
        if (!isSet(value)) {
            return "—";
        }
        if (field.type === "number") {
            return [field.prefix, value, field.suffix].filter((part) => part !== "" && part !== undefined).join(" ");
        }
        if (field.type === "date") {
            return DateTime.fromISO(value).toLocaleString(DateTime.DATE_MED);
        }
        if (field.type === "datetime") {
            return deserializeDateTime(value).toLocaleString(DateTime.DATETIME_MED);
        }
        if (field.type === "multi") {
            return value.join(", ");
        }
        return String(value);
    }

    // Sections
    isFolded(field) {
        return Boolean(this.ui.folded[field.id]);
    }
    toggleSection(field) {
        this.ui.folded[field.id] = !this.ui.folded[field.id];
    }
    /** A section is done when its required questions are answered (and at least one question is). */
    sectionDone(section) {
        const fields = this.visibleFields;
        const start = fields.indexOf(section);
        const questions = [];
        for (const field of fields.slice(start + 1)) {
            if (field.type === "section") {
                break;
            }
            if (field.type !== "boolean" && !this.isDisabled(field)) {
                questions.push(field);
            }
        }
        return (
            questions.length > 0 &&
            questions.some((f) => this.isDone(f)) &&
            questions.filter((f) => f.required).every((f) => this.isDone(f))
        );
    }

    // Answers
    set(field, value) {
        this.values[this.key(field)] = value;
        delete this.errors[this.key(field)];
    }
    onText(field, ev) {
        this.set(field, ev.target.value);
    }
    /** Long text grows with what is typed. */
    onLongText(field, ev) {
        ev.target.style.height = "auto";
        ev.target.style.height = `${ev.target.scrollHeight + 2}px`;
        this.set(field, ev.target.value);
    }
    charCount(field) {
        return _t("%s characters", String(this.value(field)).length);
    }
    onNumber(field, ev) {
        const raw = ev.target.value;
        this.set(field, raw === "" ? false : Number(raw));
    }
    step(field, delta) {
        const current = Number(this.values[this.key(field)]) || 0;
        this.set(field, Math.round((current + delta) * 1e6) / 1e6);
    }
    get dateShortcuts() {
        return [
            { label: _t("Today"), days: 0 },
            { label: _t("Tomorrow"), days: 1 },
            { label: _t("In a week"), days: 7 },
        ];
    }
    pickDate(field, days) {
        this.set(field, DateTime.now().plus({ days }).toISODate());
    }
    isBoolean(field, value) {
        return Boolean(this.values[this.key(field)]) === value;
    }
    datetimeValue(field) {
        const value = this.value(field);
        return value ? deserializeDateTime(value).toFormat("yyyy-MM-dd'T'HH:mm") : "";
    }
    onDatetime(field, ev) {
        const raw = ev.target.value;
        this.set(field, raw ? serializeDateTime(DateTime.fromISO(raw)) : false);
    }
    isChosen(field, option) {
        const value = this.values[this.key(field)];
        return field.type === "multi" ? (value || []).includes(option) : value === option;
    }
    choose(field, option) {
        if (field.type === "multi") {
            const ticked = [...(this.values[this.key(field)] || [])];
            const index = ticked.indexOf(option);
            if (index >= 0) {
                ticked.splice(index, 1);
            } else {
                ticked.push(option);
            }
            this.set(field, ticked.length ? ticked : false);
        } else {
            this.set(field, this.isChosen(field, option) && !field.required ? false : option);
        }
    }
    /** Search box of a long choice list: the typed text must match a choice. */
    onSearchChoice(field, ev) {
        const typed = ev.target.value.trim().toLowerCase();
        const option = field.options.find((o) => o.toLowerCase() === typed);
        this.set(field, option || false);
        ev.target.value = option || "";
    }
    recordPlaceholder(field) {
        return field.placeholder || (field.type === "user" ? _t("Choose a user") : _t("Choose a contact"));
    }
    recordId(field) {
        return this.values[this.key(field)] || false;
    }

    // Files
    files(field) {
        return this.values[this.key(field)] || [];
    }
    fileSize(file) {
        const size = file.size || 0;
        if (size >= 1024 * 1024) {
            return `${(size / 1024 / 1024).toFixed(1)} MB`;
        }
        return size ? `${Math.max(1, Math.round(size / 1024))} KB` : "";
    }
    thumbnail(file) {
        if (!(file.mimetype || "").startsWith("image/")) {
            return false;
        }
        return file.id ? `/web/image/${file.id}?width=96&height=96` : `data:${file.mimetype};base64,${file.data}`;
    }
    setDragOver(value) {
        this.ui.dragOver = value;
    }
    onFiles(field, ev) {
        const files = [...ev.target.files];
        ev.target.value = "";
        return this.addFiles(field, files);
    }
    onDropFiles(field, ev) {
        this.ui.dragOver = false;
        if (!this.isDisabled(field)) {
            return this.addFiles(field, [...ev.dataTransfer.files]);
        }
    }
    async addFiles(field, files) {
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
            added.push({ name: file.name, data, size: file.size, mimetype: file.type });
        }
        if (added.length) {
            this.set(field, [...this.files(field), ...added]);
        }
    }
    removeFile(field, index) {
        const files = [...this.files(field)];
        files.splice(index, 1);
        this.set(field, files.length ? files : false);
    }
}
