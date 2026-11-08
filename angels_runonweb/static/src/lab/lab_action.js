import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { LabPage } from "./lab_page";

let nextId = 0;

// Thin shell: Odoo opens the action, the page draws itself with its own markup and CSS.
export class RunOnWebLabAction extends Component {
    static template = "angels_runonweb.LabAction";

    setup() {
        const orm = useService("orm");
        const runonweb = useService("angels_runonweb");
        this.hostId = `o-row-host-${++nextId}`;
        onMounted(() => {
            this.page = new LabPage(document.getElementById(this.hostId), {
                call: (method, ...args) => orm.call("angels.runonweb", method, args),
                runonweb,
            });
            this.page.start();
        });
        onWillUnmount(() => this.page?.destroy());
    }
}

registry.category("actions").add("angels_runonweb_lab", RunOnWebLabAction);
