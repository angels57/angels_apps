import { Component, onWillStart, useExternalListener } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { FormRenderer, WIDTH_COLS } from "../common/form_renderer";
import { useProps, useState } from "../common/owl_compat";
import { ConditionEditor } from "./condition_editor";
import { FlowEditor, STAGE_TYPES } from "./flow_editor";
import { startPointerDrag } from "./pointer_drag";

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
const TITLE_TYPES = ["char", "selection", "date", "partner", "user"];
const PLACEHOLDER_TYPES = ["char", "text", "number", "selection", "user", "partner"];
// Widths a question snaps to while its edge is dragged, as a share of the row.
const WIDTH_STEPS = Object.entries(WIDTH_COLS).map(([width, cols]) => ({ width, share: cols / 12 }));

/**
 * Visual form designer, in three tabs:
 * - Questions: palette on the left, the form laid out as it will look (drag to
 *   add, move next to another question, or stretch its edge), properties on the right;
 * - Flow: the steps a request goes through (see FlowEditor);
 * - Preview: the form as the requester or as one of the steps sees it.
 */
export class FormDesignerAction extends Component {
    static template = "angels_forms.DesignerAction";
    static components = { ConditionEditor, FlowEditor, FormRenderer };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.nameService = useService("name");
        this.formId = this.props.action.context?.active_id;
        this.state = useState({
            data: null,
            tab: "fields",
            selectedId: false,
            dirty: false,
            saving: false,
            drop: null,
            resizing: null,
            previewAs: "requester",
            version: 0,
            previewKey: 0,
            names: { "res.users": {}, "res.groups": {} },
        });
        this.preview = useState({});
        this.newId = 0;
        onWillStart(() => this.load());
        useSetupAction({
            beforeLeave: () => (this.state.dirty ? this.save() : true),
        });
        useExternalListener(window, "keydown", (ev) => this.onKeyDown(ev));
    }

    async load() {
        this.setData(await this.orm.call("angels.form", "get_design_data", [[this.formId]]));
    }

    setData(data) {
        this.state.data = data;
        this.state.dirty = false;
        // Remounts the flow editor on the saved data.
        this.state.version = (this.state.version || 0) + 1;
        this.loadNames();
    }

    async loadNames(model, ids) {
        const nodes = this.state.data.nodes;
        const requests = model
            ? [[model, ids]]
            : [
                  ["res.users", [...new Set(nodes.flatMap((n) => n.user_ids))]],
                  ["res.groups", [...new Set(nodes.map((n) => n.group_id).filter(Boolean))]],
              ];
        for (const [resModel, resIds] of requests) {
            if (resIds.length) {
                Object.assign(this.state.names[resModel], await this.nameService.loadDisplayNames(resModel, resIds));
            }
        }
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
    get nodes() {
        return this.data.nodes;
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
    get questions() {
        return this.fields.filter((f) => f.type !== "section");
    }
    /** Flow steps whose people can fill questions. */
    get stages() {
        return this.nodes.filter((n) => STAGE_TYPES.includes(n.type));
    }
    stageOf(field) {
        return field.node_id ? this.nodes.find((n) => n.id === field.node_id) : false;
    }
    /** Questions a field may depend on: the ones placed before it. */
    sourcesFor(field) {
        const index = this.fields.indexOf(field);
        return this.fields.slice(0, index).filter((f) => f.type !== "section");
    }
    fieldIcon(field) {
        return FIELD_ICONS[field.type] || "fa-question";
    }
    canBeTitle(field) {
        return TITLE_TYPES.includes(field.type);
    }
    hasPlaceholder(field) {
        return PLACEHOLDER_TYPES.includes(field.type);
    }
    /** Conditions that point at a question placed after the field (after a move). */
    brokenConditions(field) {
        const allowed = new Set(this.sourcesFor(field).map((f) => f.id));
        return field.conditions.filter((c) => !allowed.has(c.source_id));
    }
    cellStyle(field) {
        const cols = field.type === "section" ? 12 : WIDTH_COLS[field.width] || 12;
        return `width: ${(cols / 12) * 100}%;`;
    }
    cardClass(field) {
        const stage = this.stageOf(field);
        const drop = this.state.drop;
        return {
            o_af_card: true,
            o_af_card_section: field.type === "section",
            o_af_selected: field.id === this.state.selectedId,
            o_af_card_stage: Boolean(stage),
            [`o_af_stage_${(stage?.color || 0) % 12}`]: Boolean(stage),
            [`o_af_drop_${drop?.side}`]: drop?.id === field.id,
        };
    }
    get widthKeys() {
        return Object.keys(this.labels.widths);
    }
    isPreviewAs(stage) {
        return String(stage.id) === this.state.previewAs;
    }
    get resizeGuides() {
        return WIDTH_STEPS.filter((step) => step.share < 1).map((step) => ({
            left: `${step.share * 100}%`,
            active: this.state.resizing?.width === step.width,
        }));
    }

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
        const glue = item.match === "any" ? _t(" or ") : _t(" and ");
        return item.conditions.map((c) => this.conditionText(c)).join(glue);
    }

    // ------------------------------------------------------------------
    // Editing questions
    // ------------------------------------------------------------------

    touch() {
        this.state.dirty = true;
    }
    setTab(tab) {
        this.state.tab = tab;
        // On small screens the panels stack and the body scrolls: start each tab at the top.
        document.querySelector(".o_af_designer .o_af_body")?.scrollTo(0, 0);
        if (tab === "preview") {
            this.resetPreview();
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
            node_id: false,
            match: "all",
            conditions: [],
        };
    }
    addField(type, index = null) {
        const field = this.newField(type);
        const selected = this.selected;
        if (selected) {
            field.node_id = selected.node_id;
        }
        const selectedIndex = this.fields.indexOf(selected);
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
        for (const item of [...this.fields, ...this.nodes]) {
            item.conditions = item.conditions.filter((c) => c.source_id !== field.id);
        }
        for (const node of this.nodes) {
            if (node.user_field_id === field.id) {
                node.user_field_id = false;
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
        if (index === from || index === from + 1) {
            return;
        }
        this.fields.splice(from, 1);
        this.fields.splice(index > from ? index - 1 : index, 0, field);
        this.touch();
    }
    moveBy(field, delta) {
        const from = this.fields.indexOf(field);
        const to = from + delta;
        if (to >= 0 && to < this.fields.length) {
            this.moveField(field, delta > 0 ? to + 1 : to);
        }
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
    setStage(field, value) {
        const stage = this.stages.find((n) => String(n.id) === value);
        this.setProp(field, "node_id", stage ? stage.id : false);
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

    onKeyDown(ev) {
        const field = this.selected;
        const typing = ev.target.closest?.("input, textarea, select, [contenteditable]");
        if (this.state.tab !== "fields" || !field || typing) {
            return;
        }
        if (ev.key === "Delete") {
            this.removeField(field);
        } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "d") {
            this.duplicate(field);
        } else if (ev.altKey && ev.key === "ArrowUp") {
            this.moveBy(field, -1);
        } else if (ev.altKey && ev.key === "ArrowDown") {
            this.moveBy(field, 1);
        } else {
            return;
        }
        ev.preventDefault();
    }

    // Dragging, as in the Angels Sign editor: a label follows the pointer (mouse,
    // pen or finger) and a bar shows where the question lands.
    onPalettePointerDown(item, ev) {
        startPointerDrag(ev, {
            label: item.label,
            onMove: (x, y) => this.updateDrop(x, y),
            onDrop: () => {
                const index = this.dropIndex();
                this.state.drop = null;
                if (index !== null) {
                    this.addField(item.type, index);
                }
            },
            onClick: () => this.addField(item.type),
            onCancel: () => (this.state.drop = null),
        });
    }
    onCardPointerDown(field, ev) {
        if (ev.target.closest("button, .o_af_resize")) {
            return;
        }
        this.select(field);
        startPointerDrag(ev, {
            label: field.name,
            onMove: (x, y) => this.updateDrop(x, y, field),
            onDrop: () => {
                const index = this.dropIndex();
                this.state.drop = null;
                if (index !== null) {
                    this.moveField(field, index);
                }
            },
            onCancel: () => (this.state.drop = null),
        });
    }
    /** Where a dragged question would land: before or after the card under the pointer. */
    updateDrop(x, y, dragged = null) {
        const target = document.elementFromPoint(x, y);
        const card = target?.closest(".o_af_designer .o_af_card[data-field-id]");
        if (card) {
            const field = this.fields.find((f) => String(f.id) === card.dataset.fieldId);
            if (!field || field === dragged) {
                this.state.drop = null;
                return;
            }
            const rect = card.getBoundingClientRect();
            const fullRow = field.type === "section" || field.width === "full";
            const side = fullRow
                ? y < rect.top + rect.height / 2 ? "top" : "bottom"
                : x < rect.left + rect.width / 2 ? "left" : "right";
            this.state.drop = { id: field.id, side };
        } else if (target?.closest(".o_af_designer .o_af_canvas")) {
            this.state.drop = { id: "end", side: "end" };
        } else {
            this.state.drop = null;
        }
    }
    dropIndex() {
        const drop = this.state.drop;
        if (!drop) {
            return null;
        }
        if (drop.id === "end") {
            return this.fields.length;
        }
        const index = this.fields.findIndex((f) => f.id === drop.id);
        return ["right", "bottom"].includes(drop.side) ? index + 1 : index;
    }
    /** Stretch the right edge of a question: it snaps to 1/4, 1/3, 1/2, 2/3, 3/4 or the full row. */
    onResizePointerDown(field, ev) {
        ev.stopPropagation();
        const paper = ev.currentTarget.closest(".o_af_layout");
        const cell = ev.currentTarget.closest(".o_af_cell");
        const paperRect = paper.getBoundingClientRect();
        const left = cell.getBoundingClientRect().left;
        this.select(field);
        startPointerDrag(ev, {
            immediate: true,
            cursor: "ew-resize",
            onMove: (x) => {
                const share = (x - left) / paperRect.width;
                const step = WIDTH_STEPS.reduce((best, s) =>
                    Math.abs(s.share - share) < Math.abs(best.share - share) ? s : best
                );
                this.state.resizing = { id: field.id, width: step.width };
                if (field.width !== step.width) {
                    this.setProp(field, "width", step.width);
                }
            },
            onDrop: () => (this.state.resizing = null),
            onCancel: () => (this.state.resizing = null),
        });
    }

    // ------------------------------------------------------------------
    // Preview: as the requester, or as one of the steps
    // ------------------------------------------------------------------

    get previewFields() {
        const as = this.state.previewAs;
        return this.fields
            .filter((f) => !f.node_id || String(f.node_id) === as)
            .map((f) => {
                const stage = this.stageOf(f);
                return {
                    ...f,
                    editable: as === "requester" ? !f.node_id : Boolean(f.node_id),
                    stage: stage ? stage.name : false,
                    color: stage ? stage.color : 0,
                };
            });
    }
    setPreviewAs(value) {
        this.state.previewAs = value;
        this.resetPreview();
    }
    resetPreview() {
        for (const key of Object.keys(this.preview)) {
            delete this.preview[key];
        }
        this.state.previewKey++;
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
        for (const node of this.nodes) {
            if (!node.name.trim()) {
                problems.push(_t("A step of the flow has no name."));
            }
            const people = ["approve", "task", "notify"].includes(node.type);
            const missing =
                (node.assign_type === "users" && !node.user_ids.length) ||
                (node.assign_type === "group" && !node.group_id) ||
                (node.assign_type === "field" && !node.user_field_id);
            if (people && missing) {
                problems.push(_t("The step “%s” has nobody to send to.", node.name));
            }
        }
        return problems;
    }

    async save() {
        const problems = this.problems();
        if (problems.length) {
            this.notification.add(problems.join(" "), { type: "danger", title: _t("Cannot save yet") });
            return false;
        }
        this.state.saving = true;
        try {
            const fieldIndex = this.fields.indexOf(this.selected);
            const payload = {
                form: this.data.form,
                fields: this.fields.map((f) => ({ ...f, options: f.options.filter((o) => o.trim()) })),
                nodes: this.nodes,
            };
            const data = await this.orm.call("angels.form", "save_design", [[this.formId], payload]);
            this.setData(data);
            this.state.selectedId = fieldIndex >= 0 ? data.fields[fieldIndex]?.id || false : false;
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
