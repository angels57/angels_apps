import { Component, onMounted, onWillStart, useExternalListener, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { CONTROL_ICONS, FormRenderer } from "../common/form_renderer";
import {
    COLUMNS,
    WIDTH_COLS,
    byPlace,
    compactRows,
    needsPacking,
    packLayout,
    spanOf,
    widthFitting,
} from "../common/layout";
import { useProps, useState } from "../common/owl_compat";
import { ConditionEditor } from "./condition_editor";
import { FlowEditor, NODE_ICONS, STAGE_TYPES } from "./flow_editor";
import { recordProblems } from "./record_editor";
import { IconPicker } from "./icon_picker";
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
    multi: "fa-check-square-o",
    user: "fa-user",
    partner: "fa-address-book-o",
    file: "fa-paperclip",
};
const TITLE_TYPES = ["char", "selection", "date", "partner", "user"];
const PLACEHOLDER_TYPES = ["char", "text", "number", "selection", "user", "partner"];
// Space between grid cells, in pixels; kept in sync with .o_af_grid in designer.css.
const GAP = 12;

/**
 * Visual form designer, where a form is set up from end to end. Tabs:
 * - Questions: palette on the left, the form on a 12-column grid in the
 *   middle (drag a question anywhere, stretch its edge, edit it in place with
 *   the toolbar on it), properties on the right. A switch above the grid turns
 *   the same view into a live preview of the form.
 * - Flow: the steps a request goes through (see FlowEditor);
 * - Settings: who can fill the form, company, title, self-approval.
 * The icon and color are picked from the icon next to the name.
 */
export class FormDesignerAction extends Component {
    static template = "angels_forms.DesignerAction";
    static components = { ConditionEditor, FlowEditor, FormRenderer, IconPicker, MultiRecordSelector, RecordSelector };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.nameService = useService("name");
        this.actionService = useService("action");
        this.formId = this.props.action.context?.active_id;
        this.isNew = Boolean(this.props.action.context?.angels_forms_new);
        this.state = useState({
            data: null,
            tab: "fields",
            mode: "design",
            selectedId: false,
            dirty: false,
            saving: false,
            target: null,
            dragging: false,
            iconOpen: false,
            restrictGroups: false,
            previewAs: "requester",
            version: 0,
            pendingOpen: false,
            focusNodeId: false,
            previewKey: 0,
            names: { "res.users": {}, "res.groups": {} },
        });
        this.preview = useState({});
        this.grid = useRef("grid");
        this.newId = 0;
        onWillStart(() => this.load());
        useSetupAction({
            beforeLeave: () => (this.state.dirty ? this.save() : true),
        });
        useExternalListener(window, "keydown", (ev) => this.onKeyDown(ev));
        useExternalListener(window, "pointerdown", (ev) => {
            if (this.state.iconOpen && !ev.target.closest?.(".o_af_icon_popover, .o_af_form_icon")) {
                this.state.iconOpen = false;
            }
        });
        // A new form: type its name right away.
        onMounted(() => {
            if (this.isNew) {
                document.querySelector(".o_af_designer .o_af_name_input")?.select();
            }
        });
    }

    async load() {
        this.setData(await this.orm.call("angels.form", "get_design_data", [[this.formId]]));
    }

    setData(data) {
        // Questions saved before the grid existed get a place, in their order.
        const fields = byPlace(data.fields);
        if (needsPacking(fields)) {
            packLayout(fields);
        }
        data.fields = fields;
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
    get widthKeys() {
        return Object.keys(WIDTH_COLS);
    }
    get columns() {
        return [...Array(COLUMNS).keys()];
    }
    get rowCount() {
        return this.fields.length ? Math.max(...this.fields.map((f) => f.row)) + 1 : 0;
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
    isPreviewAs(stage) {
        return String(stage.id) === this.state.previewAs;
    }
    /** How the card draws the input of a question: the same controls as the filled form. */
    mockKind(field) {
        if (field.type === "selection") {
            return field.options.length <= 6 ? "choices" : "search";
        }
        return {
            section: false,
            text: "area",
            boolean: "yesno",
            multi: "choices",
            number: "number",
            date: "date",
            file: "file",
        }[field.type] ?? "input";
    }
    mockIcon(field) {
        return CONTROL_ICONS[field.type] || "fa-pencil";
    }
    mockHint(field) {
        if (field.placeholder) {
            return field.placeholder;
        }
        return {
            number: "0",
            date: _t("Date"),
            datetime: _t("Date and time"),
            user: _t("Choose a user"),
            partner: _t("Choose a contact"),
            selection: _t("Search a choice"),
        }[field.type] || "";
    }
    widthLabel(width) {
        return width === "full" ? "1" : this.labels.widths[width];
    }
    /** Conditions that point at a question placed after the field (after a move). */
    brokenConditions(field) {
        const allowed = new Set(this.sourcesFor(field).map((f) => f.id));
        return field.conditions.filter((c) => !allowed.has(c.source_id));
    }
    cardStyle(field) {
        return `grid-row: ${field.row + 1}; grid-column: ${field.col + 1} / span ${spanOf(field)};`;
    }
    cardClass(field) {
        const stage = this.stageOf(field);
        return {
            o_af_card: true,
            o_af_card_section: field.type === "section",
            o_af_selected: field.id === this.state.selectedId,
            o_af_card_stage: Boolean(stage),
            o_af_card_moving: this.state.dragging && this.state.dragging === field.id,
            [`o_af_stage_${(stage?.color || 0) % 12}`]: Boolean(stage),
        };
    }
    /** Where the dragged question would land: a cell area, or a line for a new row. */
    get targetStyle() {
        const target = this.state.target;
        if (!target) {
            return "";
        }
        if (target.insert) {
            return `top: ${target.y}px;`;
        }
        return `grid-row: ${target.row + 1}; grid-column: ${target.col + 1} / span ${target.span};`;
    }
    get endRowStyle() {
        return `grid-row: ${this.rowCount + 1}; grid-column: 1 / span ${COLUMNS};`;
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
        let value = condition.value || "…";
        if (source.type === "boolean") {
            value = condition.value === "1" ? _t("checked") : _t("not checked");
        }
        return `${source.name} ${operator} ${value}`;
    }
    /** "Only shown when ..." under the conditions of a question. */
    conditionSummary(field) {
        if (!field.conditions.length) {
            return "";
        }
        return _t("Only shown when %s", this.conditionsText(field));
    }
    conditionsText(item) {
        const glue = item.match === "any" ? _t(" or ") : _t(" and ");
        return item.conditions.map((c) => this.conditionText(c)).join(glue);
    }

    // ------------------------------------------------------------------
    // Grid: free cells, targets
    // ------------------------------------------------------------------

    /** Columns taken in ``row`` by questions other than ``except``. */
    takenCells(row, except = null) {
        const taken = new Set();
        for (const field of this.fields) {
            if (field !== except && field.row === row) {
                for (let col = field.col; col < field.col + spanOf(field); col++) {
                    taken.add(col);
                }
            }
        }
        return taken;
    }
    /** The free run of columns [start, end) around ``col`` in ``row``, or false if ``col`` is taken. */
    freeRun(row, col, except = null) {
        const taken = this.takenCells(row, except);
        if (taken.has(col)) {
            return false;
        }
        let start = col;
        let end = col + 1;
        while (start > 0 && !taken.has(start - 1)) {
            start--;
        }
        while (end < COLUMNS && !taken.has(end)) {
            end++;
        }
        return { start, end };
    }
    /**
     * Fit a question in ``row`` at ``col``: same width if there is room, or
     * narrower down to 1/4. Returns ``{col, width}`` or false.
     */
    fitInRow(row, col, width, except = null) {
        const taken = this.takenCells(row, except);
        let anchor = col;
        if (taken.has(anchor)) {
            // The nearest free column on either side.
            anchor = this.columns
                .filter((c) => !taken.has(c))
                .sort((a, b) => Math.abs(a - col) - Math.abs(b - col))[0];
            if (anchor === undefined) {
                return false;
            }
        }
        const run = this.freeRun(row, anchor, except);
        const free = run.end - run.start;
        const fitted = WIDTH_COLS[width] <= free ? width : widthFitting(free);
        if (!fitted) {
            return false;
        }
        const span = WIDTH_COLS[fitted];
        return { col: Math.min(Math.max(col, run.start), run.end - span), width: fitted };
    }
    /** Bands (top, bottom) of each row of the grid, from the cards on screen. */
    rowBands(except = null) {
        const bands = new Map();
        for (const card of this.grid.el.querySelectorAll(".o_af_card[data-row]")) {
            if (except && card.dataset.fieldId === String(except.id)) {
                continue;
            }
            const row = Number(card.dataset.row);
            const rect = card.getBoundingClientRect();
            const band = bands.get(row) || { top: rect.top, bottom: rect.bottom };
            band.top = Math.min(band.top, rect.top);
            band.bottom = Math.max(band.bottom, rect.bottom);
            bands.set(row, band);
        }
        return [...bands.entries()].sort((a, b) => a[0] - b[0]);
    }
    /**
     * The place under the pointer for a question of ``width``: inside an
     * existing row (sharing it), or a new row between two others.
     */
    targetAt(x, y, { width, section = false, field = null }) {
        const grid = this.grid.el;
        const rect = grid.getBoundingClientRect();
        const cell = (rect.width - GAP * (COLUMNS - 1)) / COLUMNS;
        const col = Math.min(COLUMNS - 1, Math.max(0, Math.floor((x - rect.left) / (cell + GAP))));
        const newRow = (row, edge) => {
            const span = section ? COLUMNS : WIDTH_COLS[width];
            return { row, insert: true, col: Math.min(col, COLUMNS - span), span, width, y: edge - rect.top - GAP / 2 };
        };
        const bands = this.rowBands(field);
        for (const [row, band] of bands) {
            if (y < band.top) {
                return newRow(row, band.top);
            }
            if (y <= band.bottom + GAP) {
                const edge = Math.min(16, (band.bottom - band.top) / 4);
                if (section || y < band.top + edge) {
                    return y < (band.top + band.bottom) / 2 ? newRow(row, band.top) : newRow(row + 1, band.bottom + GAP);
                }
                if (y > band.bottom - edge) {
                    return newRow(row + 1, band.bottom + GAP);
                }
                const fit = this.fitInRow(row, col, width, field);
                if (fit) {
                    return { row, insert: false, col: fit.col, span: WIDTH_COLS[fit.width], width: fit.width };
                }
                return newRow(row + 1, band.bottom + GAP);
            }
        }
        const last = bands.at(-1);
        return newRow(last ? last[0] + 1 : 0, last ? last[1].bottom + GAP : rect.top + GAP / 2);
    }
    /** Put ``field`` at ``target``, opening a new row when asked. */
    place(field, target) {
        if (target.insert) {
            for (const other of this.fields) {
                if (other !== field && other.row >= target.row) {
                    other.row++;
                }
            }
        }
        field.row = target.row;
        field.col = target.col;
        if (target.width && field.type !== "section") {
            field.width = target.width;
        }
        this.relayout();
    }
    /** Rows without gaps, and the list in reading order (conditions rely on it). */
    relayout() {
        compactRows(this.fields);
        const ordered = byPlace(this.fields);
        this.fields.splice(0, this.fields.length, ...ordered);
        this.touch();
    }
    /** Where a new question goes without dragging: next to the selection, or in a new row below. */
    placeAfter(anchor, width) {
        if (anchor && anchor.type !== "section") {
            const col = anchor.col + spanOf(anchor);
            if (col < COLUMNS) {
                const fit = this.fitInRow(anchor.row, col, width);
                if (fit && fit.col >= col) {
                    return { row: anchor.row, insert: false, col: fit.col, width: fit.width };
                }
            }
        }
        return { row: anchor ? anchor.row + 1 : this.rowCount, insert: true, col: 0, width };
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
    }
    /** Same view, two modes: design the questions, or try the form as it will be filled. */
    setMode(mode) {
        this.state.mode = mode;
        if (mode === "test") {
            this.resetPreview();
        }
    }
    setFormProp(name, value) {
        this.data.form[name] = value;
        this.touch();
    }
    setLook(values) {
        Object.assign(this.data.form, values);
        this.touch();
    }
    toggleIconPicker() {
        this.state.iconOpen = !this.state.iconOpen;
    }

    // ------------------------------------------------------------------
    // Settings tab
    // ------------------------------------------------------------------

    get titleQuestions() {
        return this.fields.filter((f) => this.canBeTitle(f));
    }
    get restricted() {
        return this.data.form.group_ids.length > 0 || this.state.restrictGroups;
    }
    setRestricted(restricted) {
        this.state.restrictGroups = restricted;
        if (!restricted) {
            this.setFormProp("group_ids", []);
        }
    }
    setTitleQuestion(value) {
        const field = this.titleQuestions.find((f) => String(f.id) === value);
        this.setFormProp("title_field_id", field ? field.id : false);
    }
    /** The plain Odoo form of the form, for anything the designer does not show. */
    async openClassicForm() {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "angels.form",
            res_id: this.formId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    newField(type) {
        return {
            id: `new_${++this.newId}`,
            name: this.labels.types[type],
            type,
            required: false,
            help: "",
            placeholder: "",
            options: ["selection", "multi"].includes(type) ? [_t("Option 1"), _t("Option 2")] : [],
            prefix: "",
            suffix: "",
            width: "full",
            row: 0,
            col: 0,
            node_id: false,
            match: "all",
            conditions: [],
        };
    }
    addField(type, target = null) {
        const field = this.newField(type);
        const selected = this.selected;
        if (selected) {
            field.node_id = selected.node_id;
        }
        const place = target || this.placeAfter(selected, type === "section" ? "full" : "half");
        this.fields.push(field);
        this.place(field, place);
        this.state.selectedId = field.id;
        if (this.state.mode !== "design") {
            this.state.mode = "design";
        }
    }
    select(field) {
        this.state.selectedId = field.id;
    }
    duplicate(field) {
        const copy = { ...JSON.parse(JSON.stringify(field)), id: `new_${++this.newId}` };
        copy.name = _t("%s (copy)", field.name);
        const place = this.placeAfter(field, field.width);
        this.fields.push(copy);
        this.place(copy, place);
        this.state.selectedId = copy.id;
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
            node.mappings = (node.mappings || []).filter((m) => m.source !== "question" || m.question_id !== field.id);
        }
        if (this.data.form.title_field_id === field.id) {
            this.data.form.title_field_id = false;
        }
        this.state.selectedId = false;
        this.relayout();
    }
    setProp(field, name, value) {
        field[name] = value;
        if (name === "type") {
            if (["selection", "multi"].includes(value) && !field.options.length) {
                field.options = [_t("Option 1"), _t("Option 2")];
            }
            if (value === "section") {
                field.required = false;
                this.place(field, { row: field.row, insert: true, col: 0 });
            }
            if (!this.canBeTitle(field) && this.data.form.title_field_id === field.id) {
                this.data.form.title_field_id = false;
            }
        }
        this.touch();
    }
    /** New width from the toolbar or the inspector; a question that no longer fits moves to a new row. */
    setWidth(field, width) {
        const span = WIDTH_COLS[width];
        const taken = this.takenCells(field.row, field);
        const fits = (col) => col + span <= COLUMNS && [...Array(span).keys()].every((i) => !taken.has(col + i));
        if (fits(field.col)) {
            field.width = width;
            this.touch();
            return;
        }
        const col = this.columns.filter(fits).sort((a, b) => Math.abs(a - field.col) - Math.abs(b - field.col))[0];
        if (col !== undefined) {
            this.place(field, { row: field.row, insert: false, col, width });
        } else {
            this.place(field, { row: field.row + 1, insert: true, col: 0, width });
        }
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
    showConditions() {
        document.querySelector(".o_af_designer .o_af_conditions_anchor")?.scrollIntoView({ behavior: "smooth" });
    }

    /** Arrows move the selected question one column, or to the row above / below. */
    moveBy(field, dx, dy) {
        if (dx) {
            const col = field.col + dx;
            const span = spanOf(field);
            const taken = this.takenCells(field.row, field);
            if (col >= 0 && col + span <= COLUMNS && [...Array(span).keys()].every((i) => !taken.has(col + i))) {
                field.col = col;
                this.relayout();
            }
            return;
        }
        const alone = this.takenCells(field.row, field).size === 0;
        const row = field.row + dy;
        if (row < 0 || (alone && row >= this.rowCount)) {
            return;
        }
        const fit = row < this.rowCount && field.type !== "section" ? this.fitInRow(row, field.col, field.width, field) : false;
        if (fit && WIDTH_COLS[fit.width] === spanOf(field)) {
            this.place(field, { row, insert: false, col: fit.col });
        } else {
            // A new row just above / below; a question alone in its row jumps over the next row.
            const target = dy < 0 ? (alone ? row : field.row) : alone ? field.row + 2 : field.row + 1;
            this.place(field, { row: target, insert: true, col: field.col });
        }
    }
    onKeyDown(ev) {
        const field = this.selected;
        const typing = ev.target.closest?.("input, textarea, select, [contenteditable]");
        if (this.state.tab !== "fields" || this.state.mode !== "design" || !field || typing) {
            return;
        }
        const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (ev.key === "Delete") {
            this.removeField(field);
        } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "d") {
            this.duplicate(field);
        } else if (moves[ev.key]) {
            this.moveBy(field, ...moves[ev.key]);
        } else if (ev.key === "Escape") {
            this.state.selectedId = false;
        } else {
            return;
        }
        ev.preventDefault();
    }

    // Dragging, as in the Angels Sign editor: a label follows the pointer (mouse,
    // pen or finger), the grid lights up and the landing place is drawn on it.
    onPalettePointerDown(item, ev) {
        const width = item.type === "section" ? "full" : "half";
        startPointerDrag(ev, {
            label: item.label,
            onMove: (x, y) => {
                this.state.dragging = "new";
                this.state.target = this.overGrid(x, y)
                    ? this.targetAt(x, y, { width, section: item.type === "section" })
                    : null;
            },
            onDrop: () => {
                const target = this.state.target;
                this.endDrag();
                if (target) {
                    this.addField(item.type, target);
                }
            },
            onClick: () => this.addField(item.type),
            onCancel: () => this.endDrag(),
        });
    }
    onCardPointerDown(field, ev) {
        if (ev.target.closest("button, input, textarea, select, .o_af_resize, .o_af_toolbar")) {
            return;
        }
        this.select(field);
        if (ev.pointerType === "touch" && !ev.target.closest(".o_af_grip")) {
            return;
        }
        startPointerDrag(ev, {
            label: field.name,
            onMove: (x, y) => {
                this.state.dragging = field.id;
                this.state.target = this.overGrid(x, y)
                    ? this.targetAt(x, y, { width: field.width, section: field.type === "section", field })
                    : null;
            },
            onDrop: () => {
                const target = this.state.target;
                this.endDrag();
                if (target) {
                    this.place(field, target);
                }
            },
            onCancel: () => this.endDrag(),
        });
    }
    overGrid(x, y) {
        return Boolean(document.elementFromPoint(x, y)?.closest(".o_af_designer .o_af_canvas"));
    }
    endDrag() {
        this.state.target = null;
        this.state.dragging = false;
    }
    /** Stretch the right edge of a question: it snaps to the grid, 1/4 to the full row. */
    onResizePointerDown(field, ev) {
        ev.stopPropagation();
        const rect = this.grid.el.getBoundingClientRect();
        const cell = (rect.width - GAP * (COLUMNS - 1)) / COLUMNS;
        const taken = this.takenCells(field.row, field);
        let limit = COLUMNS;
        for (let col = field.col + 1; col < COLUMNS; col++) {
            if (taken.has(col)) {
                limit = col;
                break;
            }
        }
        this.select(field);
        startPointerDrag(ev, {
            immediate: true,
            cursor: "ew-resize",
            onMove: (x) => {
                const end = Math.round((x - rect.left + GAP / 2) / (cell + GAP));
                const width = widthFitting(Math.min(limit, Math.max(end, field.col + 3)) - field.col);
                if (width) {
                    this.state.target = { row: field.row, insert: false, col: field.col, span: WIDTH_COLS[width], width };
                    if (field.width !== width) {
                        field.width = width;
                        this.touch();
                    }
                }
            },
            onDrop: () => this.endDrag(),
            onCancel: () => this.endDrag(),
        });
    }

    // ------------------------------------------------------------------
    // Test mode: the form as the requester or as one of the steps fills it
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

    /**
     * What blocks saving, as {text, short, tab, nodeId | fieldId}: the full sentence for the
     * notification and the list of pending items, the short one for the step on the diagram.
     */
    problems() {
        const problems = [];
        if (!this.data.form.name.trim()) {
            problems.push({ text: _t("The form needs a name."), tab: "settings" });
        }
        for (const field of this.fields) {
            const add = (text) => problems.push({ text, tab: "fields", fieldId: field.id });
            if (!field.name.trim()) {
                add(_t("A question has no label."));
            }
            if (["selection", "multi"].includes(field.type) && !field.options.some((o) => o.trim())) {
                add(_t("“%s” needs at least one choice.", field.name));
            }
            if (this.brokenConditions(field).length) {
                add(_t("“%s” depends on a question placed after it.", field.name));
            }
        }
        for (const node of this.nodes) {
            const add = (problem) => problems.push({ ...problem, tab: "flow", nodeId: node.id });
            if (!node.name.trim()) {
                add({ text: _t("A step of the flow has no name."), short: _t("No name") });
            }
            const people = ["approve", "task", "notify"].includes(node.type);
            const missing =
                (node.assign_type === "users" && !node.user_ids.length) ||
                (node.assign_type === "group" && !node.group_id) ||
                (node.assign_type === "field" && !node.user_field_id);
            if (people && missing) {
                add({ text: _t("The step “%s” has nobody to send to.", node.name), short: _t("Nobody to send to") });
            }
            if (node.type === "record") {
                recordProblems(node, this.fields.filter((f) => f.type !== "section")).forEach(add);
            }
        }
        return problems;
    }
    /** Problems of each step of the flow, by step id, for the diagram. */
    get nodeProblems() {
        const byNode = {};
        for (const problem of this.problems()) {
            if (problem.nodeId) {
                (byNode[problem.nodeId] ||= []).push(problem);
            }
        }
        return byNode;
    }
    pendingLabel(problems) {
        return problems.length === 1 ? _t("1 pending") : _t("%s pending", problems.length);
    }
    problemIcon(problem) {
        if (problem.nodeId) {
            return NODE_ICONS[this.nodes.find((n) => n.id === problem.nodeId)?.type] || "fa-code-fork";
        }
        return problem.fieldId ? "fa-list-alt" : "fa-sliders";
    }
    clearFocus() {
        this.state.focusNodeId = false;
    }
    togglePending() {
        this.state.pendingOpen = !this.state.pendingOpen;
    }
    /** Open the tab of a pending item and select its question or step. */
    goToProblem(problem) {
        this.state.pendingOpen = false;
        if (problem.nodeId) {
            this.state.focusNodeId = problem.nodeId;
            this.state.version = (this.state.version || 0) + 1;
        } else if (problem.fieldId) {
            this.state.selectedId = problem.fieldId;
        }
        this.setTab(problem.tab);
    }

    async save() {
        const problems = this.problems();
        if (problems.length) {
            this.notification.add(problems.map((p) => p.text).join(" "), { type: "danger", title: _t("Cannot save yet") });
            this.state.pendingOpen = true;
            return false;
        }
        this.state.saving = true;
        try {
            const fieldIndex = this.fields.indexOf(this.selected);
            const payload = {
                form: this.data.form,
                fields: byPlace(this.fields).map((f) => ({ ...f, options: f.options.filter((o) => o.trim()) })),
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
