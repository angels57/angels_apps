import { Component, onMounted, useExternalListener, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { useProps, useState } from "../common/owl_compat";
import { startPointerDrag } from "../common/pointer_drag";
import { ConditionEditor } from "./condition_editor";
import { nodeIcon, nodeTypes } from "./node_types";

const PEOPLE_TYPES = ["approve", "task", "notify"];
const NODE_W = 220;
const NODE_H = 88;
const GRID = 20;
const SNAP = 8;
const COLUMN = 280;
const ROW = 130;
const ZOOM_MIN = 0.4;
const ZOOM_MAX = 1.5;

/**
 * The steps a document goes through, drawn as boxes linked by arrows, like the
 * Integration Workflow builder. Drag a step from the palette, move it (it
 * snaps to the grid and lines up with the others), and drag from one of its
 * outputs (Yes / No, Approved / Rejected, Then) to the next step.
 *
 * The host gives what conditions read (``sources``), the users a step can be
 * sent to from the document (``userSources``, optional) and its own settings
 * for a step (``inspector`` slot, with ``node``). Kinds of step come from the
 * ``angels_flow.node_types`` registry.
 *
 * Mutates ``props.nodes`` in place and calls ``props.onChange``.
 */
export class FlowEditor extends Component {
    static template = "angels_flow.FlowEditor";
    static components = { ConditionEditor, MultiRecordSelector, RecordSelector };

    setup() {
        // nodes, sources, userSources, labels, ports, operatorsByType, names, loadNames, conditionsText,
        // onChange, onRemoveNode, nodePills, problems (by step id), focusNodeId (step to select when
        // opened), onFocused, startText (what starts the flow), userSourceTexts ({label, placeholder,
        // empty}), readonly (only look at it), trail ({visited: [step ids in order], current: step id}:
        // a way through the flow to show); slots: inspector (with node), help
        this.props = useProps();
        this.nodes = useState(this.props.nodes);
        this.names = useState(this.props.names);
        this.state = useState({
            selectedId: this.props.focusNodeId || false,
            link: null,
            connecting: null,
            guides: [],
            zoom: 1,
            hoverId: false, // the step under the mouse: its arrows stand out
            addMenu: null, // {id, port}: the free output whose "+" menu is open
        });
        this.board = useRef("board");
        this.scroller = useRef("scroller");
        this.newId = 0;
        useExternalListener(window, "keydown", (ev) => this.onKeyDown(ev));
        onMounted(() => {
            this.fit();
            if (this.props.focusNodeId) {
                this.board.el.querySelector(`[data-node-id="${this.props.focusNodeId}"]`)
                    ?.scrollIntoView({ block: "center", inline: "center" });
                this.props.onFocused();
            }
        });
    }

    // ------------------------------------------------------------------
    // Getters
    // ------------------------------------------------------------------

    get selected() {
        return this.nodes.find((n) => n.id === this.state.selectedId);
    }
    get palette() {
        return nodeTypes
            .getEntries()
            .filter(([type, kind]) => kind.palette && this.props.ports[type])
            .sort(([, a], [, b]) => a.sequence - b.sequence)
            .map(([type, kind]) => ({ type, icon: kind.icon, label: this.props.labels.node_types[type] }));
    }
    // Choices shown as chips; the first one is what an empty value means.
    get endChoices() {
        return [
            { value: "approved", label: _t("Approved") },
            { value: "rejected", label: _t("Rejected") },
        ];
    }
    get assignChoices() {
        const choices = [
            { value: "users", label: _t("Specific users") },
            { value: "group", label: _t("Members of a group") },
        ];
        if (this.props.userSources) {
            choices.push({ value: "field", label: this.userSourceTexts.label });
        }
        return choices;
    }
    get unitChoices() {
        return [
            { value: "days", label: _t("Days") },
            { value: "hours", label: _t("Hours") },
        ];
    }
    get ruleChoices() {
        return [
            { value: "any", label: _t("One person is enough") },
            { value: "all", label: _t("Everyone must approve") },
        ];
    }
    isChosen(node, prop, choice) {
        const choices = {
            end_state: this.endChoices,
            assign_type: this.assignChoices,
            approval_rule: this.ruleChoices,
            on_deadline: this.deadlineChoices,
            deadline_unit: this.unitChoices,
        }[prop];
        const current = choices.some((c) => c.value === node[prop]) ? node[prop] : choices[0].value;
        return current === choice.value;
    }
    get deadlineChoices() {
        return [
            { value: "remind", label: _t("Remind them") },
            { value: "escalate", label: _t("Send it to someone else too") },
            { value: "expire", label: _t("Go on by “Expired”") },
        ];
    }
    durationText(amount, unit) {
        if (unit === "hours") {
            return amount === 1 ? _t("1 hour") : _t("%s hours", amount);
        }
        return amount === 1 ? _t("1 day") : _t("%s days", amount);
    }
    setDeadline(node, value) {
        node.deadline_amount = Math.max(0, parseInt(value, 10) || 0);
        if (!this.hasExpiredOutput(node) && node.links.expired !== undefined) {
            node.links.expired = false;
        }
        this.changed();
    }
    setOnDeadline(node, value) {
        node.on_deadline = value;
        if (value !== "expire" && node.links.expired !== undefined) {
            node.links.expired = false;
        }
        this.changed();
    }
    get userSources() {
        return this.props.userSources || [];
    }
    get userSourceTexts() {
        return {
            label: _t("User chosen in the form"),
            placeholder: _t("Choose a question"),
            empty: _t("Add a User question to the form first."),
            ...this.props.userSourceTexts,
        };
    }
    get boardSize() {
        return {
            width: Math.max(1400, ...this.nodes.map((n) => n.x + NODE_W + 320)),
            height: Math.max(640, ...this.nodes.map((n) => n.y + NODE_H + 200)),
        };
    }
    get boardStyle() {
        const { width, height } = this.boardSize;
        return `width: ${width}px; height: ${height}px; transform: scale(${this.state.zoom});`;
    }
    /** The scrollable area takes the size of the zoomed board. */
    get stageStyle() {
        const { width, height } = this.boardSize;
        const zoom = this.state.zoom;
        return `width: ${width * zoom}px; height: ${height * zoom}px;`;
    }
    get zoomLabel() {
        return `${Math.round(this.state.zoom * 100)}%`;
    }
    nodeStyle(node) {
        return `left: ${node.x}px; top: ${node.y}px; width: ${NODE_W}px; height: ${NODE_H}px;`;
    }
    nodeClass(node) {
        const people = PEOPLE_TYPES.includes(node.type);
        return {
            o_af_node: true,
            [`o_af_node_${node.type}`]: true,
            [`o_af_node_${node.end_state}`]: node.type === "end",
            [`o_af_stage_${(node.color || 0) % 12}`]: people,
            o_af_selected: node.id === this.state.selectedId,
            o_af_node_invalid: this.problemsOf(node).length > 0,
            o_af_node_visited: this.visited.has(node.id) && node.id !== this.props.trail?.current,
            o_af_node_current: Boolean(this.props.trail) && node.id === this.props.trail.current,
            o_af_node_dimmed: Boolean(this.props.trail) && !this.visited.has(node.id),
            o_af_node_target: this.state.connecting && node.type !== "start",
        };
    }
    kindLabel(node) {
        return this.props.labels.node_types[node.type];
    }
    /** Up to 3 people who receive the step, as avatars; the others as "+N". */
    avatars(node) {
        return node.assign_type === "users" ? node.user_ids.slice(0, 3) : [];
    }
    moreAvatars(node) {
        return node.assign_type === "users" ? Math.max(0, node.user_ids.length - 3) : 0;
    }
    avatarUrl(id) {
        return `/web/image/res.users/${id}/avatar_128`;
    }
    recipientsIcon(node) {
        return node.assign_type === "group" ? "fa-users" : "fa-user-circle-o";
    }
    /** Small facts of the kind of step; they replace its summary at the bottom. */
    kindPills(node) {
        return nodeTypes.get(node.type, {}).pills?.(node) || [];
    }
    /** Small facts shown at the bottom of a step. */
    pills(node) {
        const pills = [...this.kindPills(node)];
        if (node.deadline_amount > 0 && ["approve", "task"].includes(node.type)) {
            pills.push({ icon: "fa-clock-o", text: this.durationText(node.deadline_amount, node.deadline_unit),
                         title: _t("Deadline"), muted: true });
        }
        if (node.type === "approve" && node.approval_rule === "all") {
            pills.push({ icon: "fa-users", text: _t("Everyone"), title: _t("Everyone must approve"), muted: true });
        }
        pills.push(...(this.props.nodePills?.(node) || []));
        return pills;
    }
    problemsOf(node) {
        return this.props.problems?.[node.id] || [];
    }
    problemsText(node) {
        return this.problemsOf(node).map((p) => p.text).join("\n");
    }
    icon(node) {
        return nodeIcon(node.type);
    }
    hasExpiredOutput(node) {
        return node.deadline_amount > 0 && node.on_deadline === "expire";
    }
    ports(node) {
        const ports = this.props.ports[node.type].filter((port) => port !== "expired" || this.hasExpiredOutput(node));
        return ports.map((port, index, all) => ({
            port,
            label: this.portLabel(node, port),
            top: (NODE_H * (index + 1)) / (all.length + 1),
            linked: Boolean(node.links[port]),
            tone: this.portTone(node, port),
        }));
    }
    /** Green for the way forward when there is a choice, red for No / Rejected. */
    portTone(node, port) {
        if (port === "no" || port === "reject") {
            return "no";
        }
        if (port === "expired") {
            return "late";
        }
        return port === "yes" || node.type === "approve" ? "yes" : "plain";
    }
    portLabel(node, port) {
        if (port === "yes") {
            return _t("Yes");
        }
        if (port === "no") {
            return _t("No");
        }
        if (port === "reject") {
            return _t("Rejected");
        }
        if (port === "expired") {
            return _t("Expired");
        }
        if (node.type === "approve") {
            return _t("Approved");
        }
        if (node.type === "task") {
            return _t("Done");
        }
        return _t("Then");
    }
    hasPeople(node) {
        return PEOPLE_TYPES.includes(node.type);
    }

    /** Arrows between steps, as SVG paths. */
    get links() {
        const links = [];
        const hover = this.state.hoverId;
        for (const node of this.nodes) {
            for (const { port, top, label, tone } of this.ports(node)) {
                const target = this.nodes.find((n) => n.id === node.links[port]);
                if (!target) {
                    continue;
                }
                const x1 = node.x + NODE_W;
                const y1 = node.y + top;
                const x2 = target.x;
                const y2 = target.y + NODE_H / 2;
                const selected = this.state.link?.id === node.id && this.state.link?.port === port;
                const lit = (hover && (hover === node.id || hover === target.id))
                    || this.trailPairs.has(`${node.id}>${target.id}`);
                links.push({
                    key: `${node.id}-${port}`,
                    node,
                    port,
                    d: this.curve(x1, y1, x2, y2),
                    mid: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 },
                    className: `o_af_link o_af_link_${port}${selected ? " o_af_link_selected" : ""}${lit ? " o_af_link_lit" : ""}`,
                    pillClass: `o_af_link_pill o_af_link_pill_${tone}${selected ? " selected" : ""}${lit ? " lit" : ""}`,
                    label,
                    tone,
                    // One output needs no name on its arrow; a choice (Yes / No...) does.
                    showPill: tone !== "plain" || selected,
                    selected,
                });
            }
        }
        return links;
    }
    get draftLink() {
        const connecting = this.state.connecting;
        if (!connecting) {
            return "";
        }
        const node = this.nodes.find((n) => n.id === connecting.id);
        const top = this.ports(node).find((p) => p.port === connecting.port).top;
        return this.curve(node.x + NODE_W, node.y + top, connecting.x, connecting.y);
    }
    /** Steps of the trail, and its arrows as "from>to" pairs. */
    get visited() {
        return new Set(this.props.trail?.visited || []);
    }
    get trailPairs() {
        const visited = this.props.trail?.visited || [];
        return new Set(visited.slice(1).map((id, index) => `${visited[index]}>${id}`));
    }
    get svgClass() {
        return `o_af_flow_svg${this.state.hoverId || this.props.trail ? " o_af_flow_dim" : ""}`;
    }
    curve(x1, y1, x2, y2) {
        const dx = Math.max(60, Math.abs(x2 - x1) / 2);
        return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
    }

    // ------------------------------------------------------------------
    // Plain-language summary of a step
    // ------------------------------------------------------------------

    recipientsText(node) {
        if (node.assign_type === "users") {
            const names = node.user_ids.map((id) => this.names["res.users"][id] || "...");
            return names.join(", ") || _t("nobody yet");
        }
        if (node.assign_type === "group") {
            return node.group_id
                ? _t("group %s", this.names["res.groups"][node.group_id] || "...")
                : _t("no group yet");
        }
        const field = this.userSources.find((f) => f.id === node.user_field_id);
        return field ? _t("the user in “%s”", field.name) : _t("no question yet");
    }
    summary(node) {
        switch (node.type) {
            case "start":
                return this.props.startText || _t("When the requester sends the form");
            case "condition":
                return node.conditions.length ? this.props.conditionsText(node) : _t("No condition yet");
            case "approve":
                return _t("Approval by %s", this.recipientsText(node));
            case "task":
                return _t("%s completes it", this.recipientsText(node));
            case "notify":
                return _t("Inform %s", this.recipientsText(node));
            case "back":
                return _t("The requester corrects it and sends it again");
            case "end":
                return node.end_state === "rejected" ? _t("The request is rejected") : _t("The request is approved");
        }
        return nodeTypes.get(node.type, {}).summary?.(node) || "";
    }

    // ------------------------------------------------------------------
    // Editing
    // ------------------------------------------------------------------

    changed() {
        this.props.onChange();
    }
    toBoard(x, y) {
        const rect = this.board.el.getBoundingClientRect();
        return { x: (x - rect.left) / this.state.zoom, y: (y - rect.top) / this.state.zoom };
    }
    setZoom(zoom) {
        this.state.zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(zoom * 20) / 20));
    }
    /** Zoom so that every step fits in the visible area. */
    fit() {
        const scroller = this.scroller.el;
        if (!scroller) {
            return;
        }
        const width = Math.max(...this.nodes.map((n) => n.x + NODE_W)) + 100;
        const height = Math.max(...this.nodes.map((n) => n.y + NODE_H)) + 60;
        this.setZoom(Math.min(1, scroller.clientWidth / width, scroller.clientHeight / height));
        scroller.scrollTo(0, 0);
    }
    nextColor() {
        const used = new Set(this.nodes.filter((n) => PEOPLE_TYPES.includes(n.type)).map((n) => n.color));
        for (let color = 1; color < 12; color++) {
            if (!used.has(color)) {
                return color;
            }
        }
        return (this.nodes.length % 11) + 1;
    }
    addNode(type, x, y) {
        const node = {
            id: `new_node_${++this.newId}`,
            name: this.props.labels.node_types[type],
            type,
            x: Math.max(0, Math.round(x / GRID) * GRID),
            y: Math.max(0, Math.round(y / GRID) * GRID),
            color: PEOPLE_TYPES.includes(type) ? this.nextColor() : 0,
            links: Object.fromEntries(this.props.ports[type].map((port) => [port, false])),
            end_state: "approved",
            assign_type: "users",
            user_ids: [],
            group_id: false,
            user_field_id: false,
            approval_rule: "any",
            match: "all",
            conditions: [],
            deadline_amount: 0,
            deadline_unit: "days",
            on_deadline: "remind",
            escalate_user_id: false,
            ...nodeTypes.get(type, {}).defaults,
        };
        this.nodes.push(node);
        this.state.selectedId = node.id;
        this.changed();
        return node;
    }
    /** Click in the palette: the new step goes after the selected one, linked to it. */
    addAfterSelected(type) {
        const from = this.selected;
        if (!from) {
            const scroller = this.scroller.el;
            const zoom = this.state.zoom;
            this.addNode(type, scroller.scrollLeft / zoom + 80, scroller.scrollTop / zoom + 80);
            return;
        }
        const node = this.addNode(type, from.x + COLUMN, from.y);
        const port = this.props.ports[from.type].find((p) => !from.links[p]);
        if (port) {
            from.links[port] = node.id;
        }
    }
    select(node) {
        if (this.props.readonly) {
            return;
        }
        this.state.selectedId = node.id;
        this.state.link = null;
        this.state.addMenu = null;
    }
    clearSelection(ev) {
        if (ev.target === ev.currentTarget || ev.target.closest("svg") === ev.target) {
            this.state.selectedId = false;
            this.state.link = null;
            this.state.addMenu = null;
        }
    }
    hover(node) {
        this.state.hoverId = node ? node.id : false;
    }

    // "+" on a free output: choose a kind of step, it is added there, already linked.
    toggleAddMenu(node, port) {
        const open = this.state.addMenu;
        this.state.addMenu = open && open.id === node.id && open.port === port ? null : { id: node.id, port };
        this.state.link = null;
    }
    get addMenu() {
        const open = this.state.addMenu;
        const node = open && this.nodes.find((n) => n.id === open.id);
        if (!node) {
            return null;
        }
        const { top, label } = this.ports(node).find((p) => p.port === open.port);
        return {
            node,
            port: open.port,
            title: _t("After “%s”", label),
            style: `left: ${node.x + NODE_W + 24}px; top: ${node.y + top + 18}px;`,
        };
    }
    addFromPort(node, port, type) {
        const top = this.ports(node).find((p) => p.port === port).top;
        const x = node.x + COLUMN;
        let y = Math.max(0, node.y + top - NODE_H / 2);
        while (this.nodes.some((n) => Math.abs(n.x - x) < NODE_W && Math.abs(n.y - y) < NODE_H + GRID)) {
            y += ROW;
        }
        const added = this.addNode(type, x, y);
        node.links[port] = added.id;
        this.state.addMenu = null;
        this.changed();
    }
    removeNode(node) {
        if (node.type === "start") {
            return;
        }
        for (const other of this.nodes) {
            for (const port of Object.keys(other.links)) {
                if (other.links[port] === node.id) {
                    other.links[port] = false;
                }
            }
        }
        this.props.onRemoveNode?.(node);
        this.nodes.splice(this.nodes.indexOf(node), 1);
        this.state.selectedId = false;
        this.changed();
    }
    selectLink(link) {
        if (this.props.readonly) {
            return;
        }
        this.state.link = { id: link.node.id, port: link.port };
        this.state.selectedId = false;
    }
    removeLink(link) {
        link.node.links[link.port] = false;
        this.state.link = null;
        this.changed();
    }
    setProp(node, name, value) {
        node[name] = value;
        this.changed();
    }
    async setUsers(node, ids) {
        this.setProp(node, "user_ids", ids);
        await this.props.loadNames("res.users", ids);
    }
    async setGroup(node, id) {
        this.setProp(node, "group_id", id);
        if (id) {
            await this.props.loadNames("res.groups", [id]);
        }
    }
    setUserField(node, value) {
        const question = this.userSources.find((f) => String(f.id) === value);
        this.setProp(node, "user_field_id", question ? question.id : false);
    }

    onKeyDown(ev) {
        if (this.props.readonly) {
            return;
        }
        if (ev.key === "Escape" && this.state.addMenu) {
            this.state.addMenu = null;
            return;
        }
        if (ev.target.closest?.("input, textarea, select, [contenteditable]") || ev.key !== "Delete") {
            return;
        }
        const link = this.links.find((l) => l.selected);
        if (link) {
            this.removeLink(link);
        } else if (this.selected) {
            this.removeNode(this.selected);
        } else {
            return;
        }
        ev.preventDefault();
    }

    // Palette: drag a step onto the board, or click to add it after the selection.
    onPalettePointerDown(item, ev) {
        startPointerDrag(ev, {
            label: item.label,
            onDrop: (x, y) => {
                if (document.elementFromPoint(x, y)?.closest(".o_af_flow_board")) {
                    const point = this.toBoard(x, y);
                    this.addNode(item.type, point.x - NODE_W / 2, point.y - NODE_H / 2);
                }
            },
            onClick: () => this.addAfterSelected(item.type),
        });
    }

    // Move a step: it snaps to the grid, and lines up with the other steps.
    onNodePointerDown(node, ev) {
        if (this.props.readonly || ev.target.closest(".o_af_port, .o_af_port_add, button")) {
            return;
        }
        this.select(node);
        const start = { x: ev.clientX, y: ev.clientY, nodeX: node.x, nodeY: node.y };
        const others = this.nodes.filter((n) => n !== node);
        const zoom = this.state.zoom;
        startPointerDrag(ev, {
            onMove: (x, y) => {
                const guides = [];
                let nx = Math.max(0, start.nodeX + (x - start.x) / zoom);
                let ny = Math.max(0, start.nodeY + (y - start.y) / zoom);
                const alignX = others.find((o) => Math.abs(o.x - nx) < SNAP);
                const alignY = others.find((o) => Math.abs(o.y - ny) < SNAP);
                if (alignX) {
                    nx = alignX.x;
                    guides.push({ axis: "x", pos: nx });
                } else {
                    nx = Math.round(nx / GRID) * GRID;
                }
                if (alignY) {
                    ny = alignY.y;
                    guides.push({ axis: "y", pos: ny + NODE_H / 2 });
                } else {
                    ny = Math.round(ny / GRID) * GRID;
                }
                node.x = nx;
                node.y = ny;
                this.state.guides = guides;
            },
            onDrop: () => {
                this.state.guides = [];
                this.changed();
            },
            onCancel: () => {
                node.x = start.nodeX;
                node.y = start.nodeY;
                this.state.guides = [];
            },
        });
    }

    // Connect: drag from an output to the next step. A click selects the existing arrow.
    onPortPointerDown(node, port, ev) {
        ev.stopPropagation();
        if (this.props.readonly) {
            return;
        }
        startPointerDrag(ev, {
            onMove: (x, y) => {
                this.state.connecting = { id: node.id, port, ...this.toBoard(x, y) };
            },
            onDrop: (x, y) => {
                this.state.connecting = null;
                const element = document.elementFromPoint(x, y)?.closest(".o_af_node[data-node-id]");
                const target = element && this.nodes.find((n) => String(n.id) === element.dataset.nodeId);
                if (target && target !== node && target.type !== "start") {
                    node.links[port] = target.id;
                    this.changed();
                }
            },
            onClick: () => {
                if (node.links[port]) {
                    this.state.link = { id: node.id, port };
                    this.state.selectedId = false;
                }
            },
            onCancel: () => (this.state.connecting = null),
        });
    }

    /** Put the steps in columns, following the arrows from Start. */
    arrange() {
        const start = this.nodes.find((n) => n.type === "start");
        const depth = new Map([[start, 0]]);
        const queue = [start];
        while (queue.length) {
            const node = queue.shift();
            for (const port of this.props.ports[node.type]) {
                const target = this.nodes.find((n) => n.id === node.links[port]);
                if (target && !depth.has(target)) {
                    depth.set(target, depth.get(node) + 1);
                    queue.push(target);
                }
            }
        }
        const last = Math.max(...depth.values()) + 1;
        const columns = new Map();
        for (const node of this.nodes) {
            const column = depth.has(node) ? depth.get(node) : last;
            columns.set(column, [...(columns.get(column) || []), node]);
        }
        const tallest = Math.max(...[...columns.values()].map((c) => c.length));
        for (const [column, nodes] of columns) {
            const offset = ((tallest - nodes.length) * ROW) / 2;
            nodes.forEach((node, index) => {
                node.x = 40 + column * COLUMN;
                node.y = 40 + offset + index * ROW;
            });
        }
        this.changed();
        this.fit();
    }
}
