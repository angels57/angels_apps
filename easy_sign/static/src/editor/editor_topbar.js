import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useProps, useState } from "./owl_compat";

/** Send / Sign Now, editable name, tags. */
export class EditorTopbar extends Component {
    static template = "easy_sign.EditorTopbar";

    setup() {
        this.props = useProps(); // store, breadcrumbs, onSend, onSignNow, onProperties
        this.orm = useService("orm");
        this.state = useState(this.props.store.state);
        this.tags = useState({ all: [], open: false });
    }

    get data() {
        return this.state.data;
    }
    get store() {
        return this.props.store;
    }

    async onRename(ev) {
        const name = ev.target.value.trim();
        if (name && name !== this.data.name) {
            this.data.name = await this.orm.call(this.store.resModel, "editor_set_name", [[this.store.resId], name]);
        }
    }

    async openTags() {
        this.tags.all = await this.orm.searchRead("sign.tag", [], ["name", "color"], { order: "name" });
        this.tags.open = true;
    }
    get availableTags() {
        const used = new Set(this.data.tags.map((t) => t.id));
        return this.tags.all.filter((t) => !used.has(t.id));
    }
    async setTags(ids) {
        this.data.tags = await this.orm.call(this.store.resModel, "editor_set_tags", [[this.store.resId], ids]);
    }
    async addTag(tag) {
        this.tags.open = false;
        await this.setTags([...this.data.tags.map((t) => t.id), tag.id]);
    }
    async createTag(ev) {
        if (ev.key !== "Enter" || !ev.target.value.trim()) {
            return;
        }
        const name = ev.target.value.trim();
        const existing = this.tags.all.find((t) => t.name.toLowerCase() === name.toLowerCase());
        const id = existing ? existing.id : (await this.orm.call("sign.tag", "name_create", [name]))[0];
        ev.target.value = "";
        this.tags.open = false;
        await this.setTags([...this.data.tags.map((t) => t.id), id]);
    }
    closeTagsLater() {
        setTimeout(() => (this.tags.open = false), 200);
    }
    removeTag(tag) {
        this.setTags(this.data.tags.filter((t) => t.id !== tag.id).map((t) => t.id));
    }
}
