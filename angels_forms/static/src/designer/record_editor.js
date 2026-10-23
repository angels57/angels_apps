import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { useService } from "@web/core/utils/hooks";
import { useProps, useState } from "@angels_flow/common/owl_compat";

// Kinds of question each kind of Odoo field accepts. Kept in sync with models/form_record.py.
const AS_TEXT = ["char", "text", "number", "date", "datetime", "boolean", "selection", "multi", "user", "partner"];
const QUESTION_TYPES = {
    char: AS_TEXT,
    text: AS_TEXT,
    html: AS_TEXT,
    integer: ["number"],
    float: ["number"],
    monetary: ["number"],
    boolean: ["boolean"],
    date: ["date", "datetime"],
    datetime: ["datetime", "date"],
    selection: ["selection", "char"],
};
const RELATION_QUESTIONS = { "res.users": ["user"], "res.partner": ["user", "partner"] };
const TEXT_TYPES = ["char", "text", "html"];
const PLACEHOLDER = /\{([^{}]+)\}/g;
const REQUEST_TOKENS = ["reference", "requester"];

// Kinds of record and their fields, loaded once for every Create Record step.
const cache = { models: null, fields: {} };

function questionTypes(field) {
    return field.relation ? RELATION_QUESTIONS[field.relation] || [] : QUESTION_TYPES[field.type] || [];
}

/** What blocks saving a Create Record step: the full sentence, and a short one for the step on the diagram. */
export function recordProblems(node, questions) {
    if (!node.record_model) {
        return [{ text: _t("The step “%s” needs a kind of record to create.", node.name), short: _t("No record type yet") }];
    }
    const problems = [];
    const ids = new Set(questions.map((q) => String(q.id)));
    for (const mapping of node.mappings) {
        if (mapping.source === "question" && !mapping.question_id) {
            problems.push({
                text: _t("The step “%s” has a field with no question chosen.", node.name),
                short: _t("A field has no question"),
            });
        }
        if (mapping.source === "template") {
            for (const [, token] of mapping.value.matchAll(PLACEHOLDER)) {
                if (!REQUEST_TOKENS.includes(token) && !ids.has(token)) {
                    problems.push({
                        text: _t("The step “%(step)s” uses {%(name)s}, which is not a question.", {
                            step: node.name,
                            name: token,
                        }),
                        short: _t("Unknown {%s}", token),
                    });
                }
            }
        }
    }
    const fields = cache.fields[node.record_model];
    if (fields) {
        const used = new Set(node.mappings.map((m) => m.field));
        const missing = fields.filter((f) => f.required && !used.has(f.name)).map((f) => f.label);
        if (missing.length) {
            problems.push({
                text: _t("The step “%(step)s” must fill: %(fields)s.", { step: node.name, fields: missing.join(", ") }),
                short: _t("Must fill: %s", missing.join(", ")),
            });
        }
    }
    return problems;
}

/**
 * What a Create Record step creates: the kind of record, then one row per
 * field with where its value comes from (an answer, the requester, a fixed
 * value or a text such as "Trip to {Destination}").
 *
 * Mutates ``props.node`` in place. Texts keep {question id} placeholders; the
 * question names are shown instead while editing.
 */
export class RecordEditor extends Component {
    static template = "angels_forms.RecordEditor";
    static components = { MultiRecordSelector, RecordSelector };

    setup() {
        this.props = useProps(); // node, questions, sources, onChange
        this.node = useState(this.props.node);
        this.orm = useService("orm");
        this.state = useState({ models: [], fields: [], adding: false });
        onWillStart(async () => {
            cache.models ||= await this.orm.call("angels.form", "get_record_models", []);
            this.state.models = cache.models;
            if (this.node.record_model) {
                await this.loadFields(this.node.record_model);
            }
        });
    }

    async loadFields(model) {
        cache.fields[model] ||= await this.orm.call("angels.form", "get_record_fields", [model]);
        this.state.fields = cache.fields[model];
    }
    changed() {
        this.props.onChange();
    }

    // Kind of record
    modelLabel(model) {
        return `${model.name} (${model.model})`;
    }
    get currentModelLabel() {
        const model = this.state.models.find((m) => m.model === this.node.record_model);
        return model ? this.modelLabel(model) : this.node.record_model || "";
    }
    async setModel(text) {
        const typed = text.trim().toLowerCase();
        const model = this.state.models.find((m) =>
            [this.modelLabel(m), m.name, m.model].some((label) => label.toLowerCase() === typed)
        );
        if (!model || model.model === this.node.record_model) {
            return;
        }
        await this.loadFields(model.model);
        this.node.record_model = model.model;
        this.node.record_model_name = model.name;
        this.node.mappings = [];
        for (const field of this.state.fields.filter((f) => f.required)) {
            this.addMapping(field.name);
        }
        this.changed();
    }

    // Fields
    fieldOf(mapping) {
        return this.state.fields.find((f) => f.name === mapping.field);
    }
    fieldLabel(mapping) {
        return this.fieldOf(mapping)?.label || mapping.field;
    }
    get freeFields() {
        const used = new Set(this.node.mappings.map((m) => m.field));
        return this.state.fields.filter((f) => !used.has(f.name));
    }
    get missingFields() {
        const used = new Set(this.node.mappings.map((m) => m.field));
        return this.state.fields.filter((f) => f.required && !used.has(f.name));
    }
    get missingText() {
        return this.missingFields.map((f) => f.label).join(", ");
    }
    startAdding() {
        this.state.adding = true;
    }
    setAttachFiles(value) {
        this.node.attach_files = value;
        this.changed();
    }
    questionsFor(field) {
        const types = questionTypes(field);
        return this.props.questions.filter((q) => types.includes(q.type));
    }
    sourcesFor(field) {
        const sources = ["value"];
        if (TEXT_TYPES.includes(field.type)) {
            sources.unshift("template");
            sources.push("requester");
        } else if (RELATION_QUESTIONS[field.relation]) {
            sources.push("requester");
        }
        return sources.map((key) => ({ key, label: this.props.sources[key] }));
    }
    addMapping(name) {
        const field = this.state.fields.find((f) => f.name === name);
        if (!field) {
            return;
        }
        const question = this.questionsFor(field).find((q) => q.name.toLowerCase() === field.label.toLowerCase())
            || this.questionsFor(field)[0];
        this.node.mappings.push({
            field: name,
            source: question ? "question" : TEXT_TYPES.includes(field.type) ? "template" : "value",
            question_id: question ? question.id : false,
            value: "",
        });
        this.state.adding = false;
        this.changed();
    }
    removeMapping(mapping) {
        this.node.mappings.splice(this.node.mappings.indexOf(mapping), 1);
        this.changed();
    }

    // Where the value comes from: "q:<id>" for a question, else the source.
    sourceKey(mapping) {
        return mapping.source === "question" ? `q:${mapping.question_id}` : mapping.source;
    }
    setSource(mapping, key) {
        if (key.startsWith("q:")) {
            const question = this.props.questions.find((q) => `q:${q.id}` === key);
            Object.assign(mapping, { source: "question", question_id: question ? question.id : false, value: "" });
        } else {
            Object.assign(mapping, { source: key, question_id: false, value: "" });
        }
        this.changed();
    }
    setValue(mapping, value) {
        mapping.value = value === false || value === undefined || value === null ? "" : String(value);
        this.changed();
    }
    valueKind(field) {
        if (["integer", "float", "monetary"].includes(field.type)) {
            return "number";
        }
        if (field.type === "many2one") {
            return "record";
        }
        if (field.type === "many2many") {
            return "records";
        }
        return ["boolean", "selection", "date", "datetime"].includes(field.type) ? field.type : "text";
    }
    /** Date and time are stored as the server writes them ("2026-11-02 09:30:00"). */
    inputValue(mapping, kind) {
        return kind === "datetime" ? mapping.value.replace(" ", "T").slice(0, 16) : mapping.value;
    }
    setInput(mapping, kind, value) {
        this.setValue(mapping, kind === "datetime" && value ? `${value.replace("T", " ")}:00` : value);
    }
    recordId(mapping) {
        return parseInt(mapping.value, 10) || false;
    }
    recordIds(mapping) {
        return mapping.value.split(",").map((id) => parseInt(id, 10)).filter(Boolean);
    }

    // Text with answers
    get requestTokens() {
        return [
            { token: "reference", label: _t("Reference") },
            { token: "requester", label: _t("Requester") },
        ];
    }
    get tokens() {
        return [...this.requestTokens, ...this.props.questions.map((q) => ({ token: String(q.id), label: q.name }))];
    }
    onTokenSelect(mapping, ev) {
        if (ev.target.value) {
            this.insertToken(mapping, ev.target.value);
        }
        ev.target.value = "";
    }
    templateText(mapping) {
        return mapping.value.replace(PLACEHOLDER, (match, token) => {
            const item = this.tokens.find((t) => t.token === token);
            return item ? `{${item.label}}` : match;
        });
    }
    setTemplate(mapping, text) {
        mapping.value = text.replace(PLACEHOLDER, (match, name) => {
            const item = this.tokens.find((t) => t.label.toLowerCase() === name.trim().toLowerCase());
            return item ? `{${item.token}}` : match;
        });
        this.changed();
    }
    insertToken(mapping, token) {
        const space = mapping.value && !mapping.value.endsWith(" ") ? " " : "";
        mapping.value += `${space}{${token}}`;
        this.changed();
    }

    get summary() {
        if (!this.node.record_model) {
            return _t("Choose what kind of record the request creates.");
        }
        const parts = this.node.mappings.map((m) => `${this.fieldLabel(m)} ← ${this.sourceText(m)}`);
        return _t("Creates a %(model)s: %(fields)s", {
            model: this.node.record_model_name || this.node.record_model,
            fields: parts.join(" · ") || "…",
        });
    }
    sourceText(mapping) {
        if (mapping.source === "question") {
            return this.props.questions.find((q) => q.id === mapping.question_id)?.name || "?";
        }
        if (mapping.source === "template") {
            return `“${this.templateText(mapping)}”`;
        }
        if (mapping.source === "requester") {
            return this.props.sources.requester;
        }
        const field = this.fieldOf(mapping);
        const choice = field?.selection && field.selection.find(([key]) => key === mapping.value);
        if (field?.type === "boolean") {
            return mapping.value === "true" ? _t("Yes") : _t("No");
        }
        return mapping.value ? `“${choice ? choice[1] : mapping.value}”` : "—";
    }
}
