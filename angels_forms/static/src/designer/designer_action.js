import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { FormRenderer } from "../common/form_renderer";
import { useProps, useState } from "../common/owl_compat";
import { ConditionEditor } from "./condition_editor";

export const FIELD_ICONS = {
    section: "fa-header",
    char: "fa-font",
    text: "fa-align-left",
    number: "fa-hashtag",
    date: "fa-calendar",
    datetime: "fa-clock-o",
    boolean: "fa-toggle-on",
    selection: "fa-list-ul",
    user: "fa-user",
    partner: "fa-address-book-o",
    file: "fa-paperclip",
};
const RULE_ICONS = { approve: "fa-check-circle", notify_submit: "fa-paper-plane", notify_done: "fa-bell" };
const TITLE_TYPES = ["char", "selection", "date", "partner", "user"];
const PLACEHOLDER_TYPES = ["char", "text", "number", "selection", "user", "partner"];
const DRAG_TYPE = "application/x-angels-form-type";
const DRAG_MOVE = "application/x-angels-form-move";

/**
 * Visual form designer: palette of question types on the left, the form in the
 * middle (drag to add or reorder), properties of the selection on the right.
 * A second tab holds the routing rules, a third one a live preview.
 */
export class FormDesignerAction extends Component {
    static template = "angels_forms.DesignerAction";
    static components = { ConditionEditor, FormRenderer, MultiRecordSelector, RecordSelector };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.nameService = useService("name");
        this.formId = this.props.action.context?.active_id;
        this.state = useState({
            data: null,
            tab: "fields",
            selectedId: false,
            selectedRuleId: false,
            dirty: false,
            saving: false,
            dropIndex: null,
            previewKey: 0,
            names: { "res.users": {}, "res.groups": {} },
        });
        this.preview = useState({});
        this.newId = 0;
        onWillStart(() => this.load());
        useSetupAction({
            beforeLeave: () => (this.state.dirty ? this.save() : true),
        });
    }

    async load() {
        this.setData(await this.orm.call("angels.form", "get_design_data", [[this.formId]]));
    }

    setData(data) {
        this.state.data = data;
        this.state.dirty = false;
        this.loadNames();
    }

    async loadNames() {
        const rules = this.state.data.rules;
        const users = [...new Set(rules.flatMap((r) => r.user_ids))];
        const groups = [...new Set(rules.map((r) => r.group_id).filter(Boolean))];
        const [userNames, groupNames] = await Promise.all([
            this.nameService.loadDisplayNames("res.users", users),
            this.nameService.loadDisplayNames("res.groups", groups),
        ]);
        Object.assign(this.state.names["res.users"], userNames);
        Object.assign(this.state.names["res.groups"], groupNames);
    }

    // ------------------------------------------------------------------
    // Getters
    // ------------------------------------------------------------------

    get breadcrumbs() {
        return (this.env.config?.breadcrumbs || []).slice(0, -1);
    }
    get data() {
        return this.state.data;
    }
    get fields() {
        return this.data.fields;
    }
    get rules() {
        return this.data.rules;
    }
    get labels() {
        return this.data.labels;
    }
    get palette() {
        return Object.keys(FIELD_ICONS).map((type) => ({
            type,
            icon: FIELD_ICONS[type],
            label: this.labels.types[type],
        }));
    }
    get selected() {
        return this.fields.find((f) => f.id === this.state.selectedId);
    }
    get selectedRule() {
        return this.rules.find((r) => r.id === this.state.selectedRuleId);
    }
    get questions() {
        return this.fields.filter((f) => f.type !== "section");
    }
    get userQuestions() {
        return this.fields.filter((f) => f.type === "user");
    }
    /** Questions a field may depend on: the ones placed before it. */
    sourcesFor(field) {
        const index = this.fields.indexOf(field);
        return this.fields.slice(0, index).filter((f) => f.type !== "section");
    }
    fieldIcon(field) {
        return FIELD_ICONS[field.type] || "fa-question";
    }
    ruleIcon(rule) {
        return RULE_ICONS[rule.rule_type];
    }
    canBeTitle(field) {
        return TITLE_TYPES.includes(field.type);
    }
    hasPlaceholder(field) {
        return PLACEHOLDER_TYPES.includes(field.type);
    }
    /** Conditions that point at a question placed after the field (after a reorder). */
    brokenConditions(field) {
        const allowed = new Set(this.sourcesFor(field).map((f) => f.id));
        return field.conditions.filter((c) => !allowed.has(c.source_id));
    }

    // ------------------------------------------------------------------
    // Plain-language summaries
    // ------------------------------------------------------------------

    conditionText(condition) {
        const source = this.fields.find((f) => f.id === condition.source_id);
        if (!source) {
            return _t("a removed question");
        }
        const operator = this.labels.operators[condition.operator];
        if (["set", "not_set"].includes(condition.operator)) {
            return `${source.name} ${operator}`;
        }
        let value = condition.value;
        if (source.type === "boolean") {
            value = condition.value === "1" ? _t("checked") : _t("not checked");
        }
        return `${source.name} ${operator} ${value}`;
    }
    conditionsText(item) {
        if (!item.conditions.length) {
            return "";
        }
        const glue = item.match === "any" ? _t(" or ") : _t(" and ");
        return item.conditions.map((c) => this.conditionText(c)).join(glue);
    }
    recipientsText(rule) {
        if (rule.assign_type === "users") {
            const names = rule.user_ids.map((id) => this.state.names["res.users"][id] || "...");
            return names.join(", ") || _t("nobody yet");
        }
        if (rule.assign_type === "group") {
            return rule.group_id
                ? _t("group %s", this.state.names["res.groups"][rule.group_id] || "...")
                : _t("no group yet");
        }
        const field = this.fields.find((f) => f.id === rule.user_field_id);
        return field ? _t("the user in “%s”", field.name) : _t("no question yet");
    }
    ruleText(rule) {
        const who = this.recipientsText(rule);
        const action = {
            approve: _t("Ask %s for approval", who),
            notify_submit: _t("Inform %s when the request is sent", who),
            notify_done: _t("Inform %s when the request is approved", who),
        }[rule.rule_type];
        const when = this.conditionsText(rule);
        return when ? _t("If %(when)s: %(action)s", { when, action }) : action;
    }

    // ------------------------------------------------------------------
    // Editing
    // ------------------------------------------------------------------

    touch() {
        this.state.dirty = true;
    }
    setTab(tab) {
        this.state.tab = tab;
        if (tab === "preview") {
            for (const key of Object.keys(this.preview)) {
                delete this.preview[key];
            }
            this.state.previewKey++;
        }
    }
    setFormProp(name, value) {
        this.data.form[name] = value;
        this.touch();
    }

    newField(type) {
        return {
            id: `new_${++this.newId}`,
            name: this.labels.types[type],
            type,
            required: false,
            help: "",
            placeholder: "",
            options: type === "selection" ? [_t("Option 1"), _t("Option 2")] : [],
            width: "full",
            match: "all",
            conditions: [],
        };
    }
    addField(type, index = null) {
        const field = this.newField(type);
        const selectedIndex = this.fields.indexOf(this.selected);
        const at = index ?? (selectedIndex >= 0 ? selectedIndex + 1 : this.fields.length);
        this.fields.splice(at, 0, field);
        this.state.selectedId = field.id;
        this.touch();
    }
    select(field) {
        this.state.selectedId = field.id;
    }
    duplicate(field) {
        const copy = { ...JSON.parse(JSON.stringify(field)), id: `new_${++this.newId}` };
        copy.name = _t("%s (copy)", field.name);
        this.fields.splice(this.fields.indexOf(field) + 1, 0, copy);
        this.state.selectedId = copy.id;
        this.touch();
    }
    removeField(field) {
        this.fields.splice(this.fields.indexOf(field), 1);
        // Forget everything that pointed at it.
        for (const item of [...this.fields, ...this.rules]) {
            item.conditions = item.conditions.filter((c) => c.source_id !== field.id);
        }
        for (const rule of this.rules) {
            if (rule.user_field_id === field.id) {
                rule.user_field_id = false;
            }
        }
        if (this.data.form.title_field_id === field.id) {
            this.data.form.title_field_id = false;
        }
        this.state.selectedId = false;
        this.touch();
    }
    moveField(field, index) {
        const from = this.fields.indexOf(field);
        this.fields.splice(from, 1);
        this.fields.splice(index > from ? index - 1 : index, 0, field);
        this.touch();
    }
    setProp(field, name, value) {
        field[name] = value;
        if (name === "type") {
            if (value === "selection" && !field.options.length) {
                field.options = [_t("Option 1"), _t("Option 2")];
            }
            if (value === "section") {
                field.required = false;
            }
            if (!this.canBeTitle(field) && this.data.form.title_field_id === field.id) {
                this.data.form.title_field_id = false;
            }
        }
        this.touch();
    }
    setTitle(field, checked) {
        this.data.form.title_field_id = checked ? field.id : false;
        this.touch();
    }
    setOption(field, index, value) {
        field.options[index] = value;
        this.touch();
    }
    addOption(field) {
        field.options.push(_t("Option %s", field.options.length + 1));
        this.touch();
    }
    removeOption(field, index) {
        field.options.splice(index, 1);
        this.touch();
    }

    // Drag and drop: from the palette (new question) or inside the canvas (move).
    onPaletteDragStart(item, ev) {
        ev.dataTransfer.setData(DRAG_TYPE, item.type);
        ev.dataTransfer.effectAllowed = "copy";
    }
    onCardDragStart(field, ev) {
        ev.dataTransfer.setData(DRAG_MOVE, String(field.id));
        ev.dataTransfer.effectAllowed = "move";
    }
    onCardDragOver(index, ev) {
        ev.preventDefault();
        const rect = ev.currentTarget.getBoundingClientRect();
        this.state.dropIndex = ev.clientY > rect.top + rect.height / 2 ? index + 1 : index;
    }
    onCanvasDragOver(ev) {
        ev.preventDefault();
        if (ev.target === ev.currentTarget) {
            this.state.dropIndex = this.fields.length;
        }
    }
    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.dropIndex = null;
        }
    }
    onDrop(ev) {
        ev.preventDefault();
        const index = this.state.dropIndex ?? this.fields.length;
        this.state.dropIndex = null;
        const type = ev.dataTransfer.getData(DRAG_TYPE);
        const moved = ev.dataTransfer.getData(DRAG_MOVE);
        if (type) {
            this.addField(type, index);
        } else if (moved) {
            const field = this.fields.find((f) => String(f.id) === moved);
            if (field) {
                this.moveField(field, index);
            }
        }
    }

    // Routing rules
    addRule() {
        const rule = {
            id: `new_${++this.newId}`,
            name: _t("Approval"),
            rule_type: "approve",
            assign_type: "users",
            user_ids: [],
            group_id: false,
            user_field_id: false,
            approval_rule: "any",
            match: "all",
            conditions: [],
        };
        this.rules.push(rule);
        this.state.selectedRuleId = rule.id;
        this.touch();
    }
    selectRule(rule) {
        this.state.selectedRuleId = rule.id;
    }
    removeRule(rule) {
        this.rules.splice(this.rules.indexOf(rule), 1);
        this.state.selectedRuleId = false;
        this.touch();
    }
    moveRule(rule, delta) {
        const from = this.rules.indexOf(rule);
        const to = from + delta;
        if (to < 0 || to >= this.rules.length) {
            return;
        }
        this.rules.splice(from, 1);
        this.rules.splice(to, 0, rule);
        this.touch();
    }
    setRuleProp(rule, name, value) {
        rule[name] = value;
        this.touch();
    }
    setRuleUserField(rule, value) {
        const question = this.userQuestions.find((f) => String(f.id) === value);
        this.setRuleProp(rule, "user_field_id", question ? question.id : false);
    }
    async setRuleUsers(rule, ids) {
        rule.user_ids = ids;
        this.touch();
        Object.assign(this.state.names["res.users"], await this.nameService.loadDisplayNames("res.users", ids));
    }
    async setRuleGroup(rule, id) {
        rule.group_id = id;
        this.touch();
        if (id) {
            Object.assign(this.state.names["res.groups"], await this.nameService.loadDisplayNames("res.groups", [id]));
        }
    }

    // ------------------------------------------------------------------
    // Saving
    // ------------------------------------------------------------------

    problems() {
        const problems = [];
        if (!this.data.form.name.trim()) {
            problems.push(_t("The form needs a name."));
        }
        for (const field of this.fields) {
            if (!field.name.trim()) {
                problems.push(_t("A question has no label."));
            }
            if (field.type === "selection" && !field.options.some((o) => o.trim())) {
                problems.push(_t("“%s” needs at least one choice.", field.name));
            }
            if (this.brokenConditions(field).length) {
                problems.push(_t("“%s” depends on a question placed after it.", field.name));
            }
        }
        for (const rule of this.rules) {
            const missing =
                (rule.assign_type === "users" && !rule.user_ids.length) ||
                (rule.assign_type === "group" && !rule.group_id) ||
                (rule.assign_type === "field" && !rule.user_field_id);
            if (missing) {
                problems.push(_t("The rule “%s” has nobody to send to.", rule.name));
            }
        }
        return problems;
    }

    async save() {
        const problems = this.problems();
        if (problems.length) {
            this.notification.add(problems.join("\n"), { type: "danger", title: _t("Cannot save yet") });
            return false;
        }
        this.state.saving = true;
        try {
            const fieldIndex = this.fields.indexOf(this.selected);
            const ruleIndex = this.rules.indexOf(this.selectedRule);
            const payload = {
                form: this.data.form,
                fields: this.fields.map((f) => ({ ...f, options: f.options.filter((o) => o.trim()) })),
                rules: this.rules,
            };
            const data = await this.orm.call("angels.form", "save_design", [[this.formId], payload]);
            this.setData(data);
            this.state.selectedId = fieldIndex >= 0 ? data.fields[fieldIndex]?.id || false : false;
            this.state.selectedRuleId = ruleIndex >= 0 ? data.rules[ruleIndex]?.id || false : false;
            this.notification.add(_t("Form saved."), { type: "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async togglePublished() {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        const published = !this.data.form.published;
        await this.orm.write("angels.form", [this.formId], { published });
        this.data.form.published = published;
        this.notification.add(published ? _t("The form is open for requests.") : _t("The form is closed."), {
            type: "info",
        });
    }
}

registry.category("actions").add("angels_forms_designer", FormDesignerAction);
