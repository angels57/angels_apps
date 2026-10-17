import { reactive } from "./owl_compat";

const ITEM_FIELDS = [
    "document_id", "page", "pos_x", "pos_y", "width", "height", "type", "required", "readonly",
    "placeholder", "options", "alignment", "linked_field", "item_type_id",
];
const m2oId = (value) => (Array.isArray(value) ? value[0] : value);

/** Editor data + ORM operations. Field changes are saved after a short delay. */
export class EditorStore {
    constructor(orm, resModel, resId) {
        this.orm = orm;
        this.resModel = resModel;
        this.resId = resId;
        this.pending = new Map();
        this.state = reactive({
            loaded: false,
            data: null,
            documents: [],
            parties: [],
            items: [],
            party: false,
            selectedId: false,
            saving: 0,
        });
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------
    async load() {
        const data = await this.orm.call(this.resModel, "get_editor_data", [[this.resId]]);
        this.partyField = data.party_field;
        for (const item of data.items) {
            item.document_id = m2oId(item.document_id);
            item[this.partyField] = m2oId(item[this.partyField]);
            item.item_type_id = m2oId(item.item_type_id);
        }
        Object.assign(this.state, {
            loaded: true,
            data,
            documents: data.documents,
            parties: data.parties,
            items: data.items,
        });
        if (!this.state.parties.some((p) => p.id === this.state.party)) {
            this.state.party = this.state.parties[0]?.id || false;
        }
    }

    get locked() {
        return this.state.data?.locked;
    }
    get selected() {
        return this.state.items.find((item) => item.id === this.state.selectedId);
    }
    partyOf(item) {
        return this.state.parties.find((p) => p.id === item[this.partyField]) || { name: "?", color: 0 };
    }
    itemsOf(docId, page) {
        return this.state.items.filter((item) => item.document_id === docId && item.page === page);
    }
    countOf(party) {
        return this.state.items.filter((item) => item[this.partyField] === party.id).length;
    }

    // ------------------------------------------------------------------
    // Items
    // ------------------------------------------------------------------
    get parentField() {
        return this.resModel === "sign.template" ? "template_id" : "request_id";
    }

    async createItem(vals) {
        const full = { [this.parentField]: this.resId, [this.partyField]: this.state.party, ...vals };
        this.state.saving++;
        try {
            const [id] = await this.orm.create("sign.item", [full]);
            const item = { id, placeholder: "", readonly: false, alignment: "left", linked_field: false, ...full };
            this.state.items.push(item);
            this.state.selectedId = id;
            return item;
        } finally {
            this.state.saving--;
        }
    }

    updateItem(item, vals) {
        Object.assign(item, vals);
        const pending = this.pending.get(item.id) || { vals: {} };
        clearTimeout(pending.timer);
        Object.assign(pending.vals, vals);
        if (!this.pending.has(item.id)) {
            this.state.saving++;
        }
        pending.timer = setTimeout(() => this.flushItem(item.id), 300);
        this.pending.set(item.id, pending);
    }

    async flushItem(id) {
        const pending = this.pending.get(id);
        if (!pending) {
            return;
        }
        this.pending.delete(id);
        clearTimeout(pending.timer);
        try {
            await this.orm.write("sign.item", [id], pending.vals);
        } finally {
            this.state.saving--;
        }
    }

    async flushAll() {
        await Promise.all([...this.pending.keys()].map((id) => this.flushItem(id)));
    }

    async deleteItem(item) {
        await this.flushItem(item.id);
        await this.orm.unlink("sign.item", [item.id]);
        this.state.items = this.state.items.filter((i) => i.id !== item.id);
        if (this.state.selectedId === item.id) {
            this.state.selectedId = false;
        }
    }

    async duplicateItem(item, overrides) {
        const vals = Object.fromEntries(ITEM_FIELDS.map((f) => [f, item[f]]));
        vals[this.partyField] = item[this.partyField];
        return this.createItem({ ...vals, ...overrides });
    }

    // ------------------------------------------------------------------
    // Parties and documents
    // ------------------------------------------------------------------
    async addParty() {
        const party = await this.orm.call(this.resModel, "editor_add_party", [[this.resId]]);
        this.state.parties.push(party);
        this.state.party = party.id;
        return party;
    }

    async removeParty(party) {
        await this.orm.call(this.resModel, "editor_remove_party", [[this.resId], party.id]);
        await this.load();
    }

    async addDocuments(files) {
        const docs = await this.orm.call(this.resModel, "editor_add_documents", [[this.resId], files]);
        this.state.documents.push(...docs);
        return docs;
    }

    async removeDocument(doc) {
        await this.orm.unlink("sign.document", [doc.id]);
        await this.load();
    }

    async moveDocument(doc, delta) {
        const docs = this.state.documents;
        const index = docs.indexOf(doc);
        const target = index + delta;
        if (target < 0 || target >= docs.length) {
            return;
        }
        docs.splice(index, 1);
        docs.splice(target, 0, doc);
        await Promise.all(docs.map((d, seq) => this.orm.write("sign.document", [d.id], { sequence: seq + 1 })));
    }
}
