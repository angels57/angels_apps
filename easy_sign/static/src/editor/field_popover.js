import { Component, useState } from "@odoo/owl";
import { LINKED_LABEL, itemLabel } from "./palette";

const TEXTUAL = ["text", "textarea", "date", "selection"];

/** Properties of the selected field, shown under it. */
export class FieldPopover extends Component {
    static template = "easy_sign.FieldPopover";
    static props = { store: Object, item: Object, onAllPages: Function };

    setup() {
        this.linked = Object.entries(LINKED_LABEL);
        this.itemLabel = itemLabel;
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
