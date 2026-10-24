import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { useState } from "../common/owl_compat";
import { FlowEditor } from "./flow_editor";

/** How long, in words: "35 min", "5 h", "2 days". */
export function durationWords(hours) {
    if (hours < 1) {
        return _t("%s min", Math.max(1, Math.round(hours * 60)));
    }
    if (hours < 48) {
        return _t("%s h", Math.round(hours));
    }
    return _t("%s days", Math.round(hours / 24));
}

/**
 * The flow of a request or run, read-only, with the steps it went through,
 * how long each took and where it is now. ``<widget name="angels_flow_trail"/>``
 * on the form of a model built on ``angels.flow.document.mixin``.
 */
export class FlowTrail extends Component {
    static template = "angels_flow.FlowTrail";
    static components = { FlowEditor };
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.nameService = useService("name");
        this.state = useState({ data: null, names: { "res.users": {}, "res.groups": {} } });
        onWillStart(async () => {
            const { resModel, resId } = this.props.record;
            if (resId) {
                const data = await this.orm.call(resModel, "get_flow_trail", [[resId]]);
                const users = [...new Set(data.nodes.flatMap((n) => n.user_ids))];
                const groups = [...new Set(data.nodes.map((n) => n.group_id).filter(Boolean))];
                if (users.length) {
                    Object.assign(this.state.names["res.users"], await this.nameService.loadDisplayNames("res.users", users));
                }
                if (groups.length) {
                    Object.assign(this.state.names["res.groups"], await this.nameService.loadDisplayNames("res.groups", groups));
                }
                this.state.data = data;
            }
        });
    }

    conditionsText(item) {
        return item.conditions.length === 1 ? _t("1 condition") : _t("%s conditions", item.conditions.length);
    }
    get trail() {
        const data = this.state.data;
        return { visited: data.trail.map((e) => e.node), current: data.current };
    }
    /** The time spent at each step it went through. */
    nodePills(node) {
        const entries = this.state.data.trail.filter((e) => e.node === node.id);
        const entry = entries.at(-1);
        if (!entry || node.type === "start") {
            return [];
        }
        if (node.id === this.state.data.current) {
            return [{ icon: "fa-hourglass-half", text: _t("for %s", durationWords(entry.hours)), tone: entry.late ? "late" : "now",
                      title: entry.late ? _t("Late") : _t("Now here") }];
        }
        if (!["approve", "task", "wait"].includes(node.type)) {
            return [];
        }
        const icon = entry.state === "rejected" || entry.state === "expired" ? "fa-times" : "fa-check";
        return [{ icon, text: durationWords(entry.hours), tone: entry.late ? "late" : "ok", title: entry.by || "" }];
    }
}

registry.category("view_widgets").add("angels_flow_trail", { component: FlowTrail });
