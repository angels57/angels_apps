import { Component } from "@odoo/owl";
import { useProps, useState } from "./owl_compat";
import { LINKED_LABEL, itemLabel } from "./palette";

const TEXTUAL = ["text", "textarea", "date", "selection"];

/** Properties of the selected field, shown under it. */
export class FieldPopover extends Component {
    static template = "easy_sign.FieldPopover";

    setup() {
        this.props = useProps(); // store, item, onAllPages
        this.linked = Object.entries(LINKED_LABEL);
        this.itemLabel = (item) => itemLabel(item, this.state.data?.palette);
        this.state = useState(this.props.store.state);
    }
    get store() {
        return this.props.store;
    }
    get item() {
        return this.props.item;
    }
    get isTextual() {
        return TEXTUAL.includes(this.item.type);
    }
    get hasOptions() {
        return ["radio", "selection"].includes(this.item.type);
    }
    update(vals) {
        this.store.updateItem(this.item, vals);
    }
    onParty(ev) {
        this.update({ [this.store.partyField]: Number(ev.target.value) });
    }
}
