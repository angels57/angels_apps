import { Component, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState } from "../common/owl_compat";

/** Get Started: start from an example flow, or from scratch, in three steps. */
export class FlowWelcome extends Component {
    static template = "angels_flow.FlowWelcome";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("angels.flow", "get_welcome_data", []);
        });
    }

    async useExample(example) {
        const action = await this.orm.call("angels.flow", "action_use_example", [[example.id]]);
        this.actionService.doAction(action);
    }
    createFlow() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "angels.flow",
            views: [[false, "form"]],
            target: "current",
        });
    }
    openFlows() {
        this.actionService.doAction("angels_flow.action_flow");
    }
}

registry.category("actions").add("angels_flow_welcome", FlowWelcome);
