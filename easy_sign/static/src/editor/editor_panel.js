import { Component } from "@odoo/owl";

export class EditorPanel extends Component {
    static template = "easy_sign.EditorPanel";
    static props = { store: Object };

    get state() {
        return this.props.store.state;
    }
    selectParty(party) {
        this.state.party = party.id;
    }
}
