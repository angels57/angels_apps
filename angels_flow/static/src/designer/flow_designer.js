import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { useProps, useState } from "../common/owl_compat";
import { FlowEditor } from "../flow_editor/flow_editor";
import { nodeTypes } from "../flow_editor/node_types";

const PEOPLE_TYPES = ["approve", "task", "notify"];

function waitText(node) {
    const amount = node.wait_amount || 0;
    if (node.wait_unit === "hours") {
        return amount === 1 ? _t("1 hour") : _t("%s hours", amount);
    }
    return amount === 1 ? _t("1 day") : _t("%s days", amount);
}

// The Wait step, offered by flows on records (their ports include it).
nodeTypes.add("wait", {
    icon: "fa-hourglass-half",
    sequence: 45,
    palette: true,
    defaults: { wait_amount: 1, wait_unit: "days" },
    summary: (node) => _t("Waits %s, then goes on", waitText(node)),
    pills: (node) => [{ icon: "fa-clock-o", text: waitText(node) }],
});

/**
 * Designer of a flow on records: the flow editor, with the fields of the
 * flow's model as what conditions test and as users a step can go to.
 * Its settings (model, when it starts) are in the form of the flow.
 */
export class FlowDesignerAction extends Component {
    static template = "angels_flow.FlowDesignerAction";
    static components = { FlowEditor };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.nameService = useService("name");
        this.actionService = useService("action");
        this.flowId = this.props.action.context?.active_id;
        this.state = useState({
            data: null,
            dirty: false,
            saving: false,
            version: 0,
            focusNodeId: false,
            names: { "res.users": {}, "res.groups": {} },
        });
        onWillStart(() => this.load());
        useSetupAction({
            beforeLeave: () => (this.state.dirty ? this.save() : true),
        });
    }

    async load() {
        this.setData(await this.orm.call("angels.flow", "get_design_data", [[this.flowId]]));
    }
    setData(data) {
        this.state.data = data;
        this.state.dirty = false;
        // Remounts the flow editor on the saved data.
        this.state.version++;
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

    get data() {
        return this.state.data;
    }
    get breadcrumbs() {
        return (this.env.config?.breadcrumbs || []).slice(0, -1);
    }
    get labels() {
        return this.data.labels;
    }
    get userSourceTexts() {
        return {
            label: _t("User in a field of the record"),
            placeholder: _t("Choose a field"),
            empty: _t("The model has no user field."),
        };
    }
    touch() {
        this.state.dirty = true;
    }
    clearFocus() {
        this.state.focusNodeId = false;
    }
    setWait(node, name, value) {
        node[name] = name === "wait_amount" ? Math.max(1, parseInt(value, 10) || 1) : value;
        this.touch();
    }

    // Conditions in plain words, for the steps on the board.
    conditionText(condition) {
        const source = this.data.sources.find((s) => s.id === condition.source_id);
        if (!source) {
            return _t("a removed field");
        }
        const operator = this.labels.operators[condition.operator];
        if (["set", "not_set"].includes(condition.operator)) {
            return `${source.name} ${operator}`;
        }
        let value = condition.value || "…";
        if (source.type === "boolean") {
            value = condition.value === "1" ? _t("checked") : _t("not checked");
        } else if (source.options) {
            value = source.options.find((o) => o.value === condition.value)?.label || value;
        }
        return `${source.name} ${operator} ${value}`;
    }
    conditionsText(item) {
        const glue = item.match === "any" ? _t(" or ") : _t(" and ");
        return item.conditions.map((c) => this.conditionText(c)).join(glue);
    }

    /** What blocks saving, as {text, short, nodeId}. */
    problems() {
        const problems = [];
        for (const node of this.data.nodes) {
            const add = (text, short) => problems.push({ text, short, nodeId: node.id });
            if (!node.name.trim()) {
                add(_t("A step of the flow has no name."), _t("No name"));
            }
            const missing =
                (node.assign_type === "users" && !node.user_ids.length) ||
                (node.assign_type === "group" && !node.group_id) ||
                (node.assign_type === "field" && !node.user_field_id);
            if (PEOPLE_TYPES.includes(node.type) && missing) {
                add(_t("The step “%s” has nobody to send to.", node.name), _t("Nobody to send to"));
            }
        }
        return problems;
    }
    get nodeProblems() {
        const byNode = {};
        for (const problem of this.problems()) {
            (byNode[problem.nodeId] ||= []).push(problem);
        }
        return byNode;
    }

    async save() {
        const problems = this.problems();
        if (problems.length) {
            this.notification.add(problems.map((p) => p.text).join(" "), {
                type: "danger",
                title: _t("Cannot save yet"),
            });
            return false;
        }
        this.state.saving = true;
        try {
            this.setData(await this.orm.call("angels.flow", "save_design", [[this.flowId], { nodes: this.data.nodes }]));
            this.notification.add(_t("Flow saved."), { type: "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }
    async openSettings() {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "angels.flow",
            res_id: this.flowId,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("angels_flow_designer", FlowDesignerAction);
