import { Component } from "@odoo/owl";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { useProps, useState } from "../common/owl_compat";

const DATE_TYPES = ["date", "datetime"];

/**
 * The fields an Update Record step sets, one row per field: where its value
 * comes from (a fixed value, today + days, who started the run, empty) and
 * the value. Mutates ``props.node`` in place.
 */
export class UpdateEditor extends Component {
    static template = "angels_flow.UpdateEditor";
    static components = { RecordSelector };

    setup() {
        this.props = useProps(); // node, fields, sources, onChange
        this.node = useState(this.props.node);
        this.state = useState({ adding: false });
    }

    changed() {
        this.props.onChange();
    }
    fieldOf(update) {
        return this.props.fields.find((f) => f.id === update.field_id);
    }
    get freeFields() {
        const used = new Set(this.node.updates.map((u) => u.field_id));
        return this.props.fields.filter((f) => !used.has(f.id));
    }
    sourcesFor(field) {
        const keys = ["value"];
        if (DATE_TYPES.includes(field.type)) {
            keys.push("today");
        }
        if (field.type === "many2one" && field.relation === "res.users") {
            keys.push("starter");
        }
        if (!field.required) {
            keys.push("empty");
        }
        return keys.map((key) => ({ key, label: this.props.sources[key] }));
    }
    valueKind(field) {
        if (["integer", "float", "monetary"].includes(field.type)) {
            return "number";
        }
        if (["boolean", "selection", "date", "datetime", "many2one"].includes(field.type)) {
            return field.type;
        }
        return "text";
    }
    startAdding() {
        this.state.adding = true;
    }
    add(fieldId) {
        const field = this.props.fields.find((f) => String(f.id) === fieldId);
        if (field) {
            this.node.updates.push({ field_id: field.id, source: "value", value: "", days: 0 });
            this.changed();
        }
        this.state.adding = false;
    }
    remove(update) {
        this.node.updates.splice(this.node.updates.indexOf(update), 1);
        this.changed();
    }
    setSource(update, source) {
        Object.assign(update, { source, value: "", days: 0 });
        this.changed();
    }
    setValue(update, value) {
        update.value = value === false || value === undefined || value === null ? "" : String(value);
        this.changed();
    }
    setDays(update, value) {
        update.days = parseInt(value, 10) || 0;
        this.changed();
    }
    /** Date and time are stored as the server writes them ("2026-11-02 09:30:00"). */
    inputValue(update, kind) {
        return kind === "datetime" ? update.value.replace(" ", "T").slice(0, 16) : update.value;
    }
    setInput(update, kind, value) {
        this.setValue(update, kind === "datetime" && value ? `${value.replace("T", " ")}:00` : value);
    }
    recordId(update) {
        return parseInt(update.value, 10) || false;
    }
}
