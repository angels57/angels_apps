import { Component, onMounted, onPatched, onWillStart, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const TYPES = [
    ["signature", _t("Signature"), [0.25, 0.06]],
    ["initials", _t("Initials"), [0.08, 0.04]],
    ["text", _t("Text"), [0.25, 0.03]],
    ["date", _t("Date"), [0.15, 0.03]],
    ["checkbox", _t("Checkbox"), [0.025, 0.02]],
    ["textarea", _t("Multiline Text"), [0.35, 0.08]],
    ["radio", _t("Radio"), [0.2, 0.08]],
    ["selection", _t("Selection"), [0.2, 0.03]],
    ["strike", _t("Strikethrough"), [0.3, 0.015]],
    ["stamp", _t("Stamp"), [0.15, 0.1]],
];
const TYPE_LABEL = Object.fromEntries(TYPES.map(([key, label]) => [key, label]));
const TYPE_SIZE = Object.fromEntries(TYPES.map(([key, , size]) => [key, size]));
const LINKABLE = [
    "partner_id.name", "partner_id.email", "partner_id.phone", "partner_id.vat", "partner_id.street",
    "partner_id.city", "partner_id.zip", "partner_id.country_id.name", "partner_id.company_name",
];
const m2oId = (value) => (Array.isArray(value) ? value[0] : value && value.id ? value.id : value);
const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

export class SignLayoutEditor extends Component {
    static template = "easy_sign.SignLayoutEditor";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.types = TYPES;
        this.typeLabel = TYPE_LABEL;
        this.linkable = LINKABLE;
        this.isTemplate = this.props.record.resModel === "sign.template";
        this.parentField = this.isTemplate ? "template_id" : "request_id";
        this.partyField = this.isTemplate ? "role_id" : "request_item_id";
        this.root = useRef("root");
        this.state = useState({ docs: [], items: [], party: false, tool: false, selectedId: false });
        this.needsRender = false;
        onWillStart(async () => {
            await loadPDFJSAssets();
            await this.load(this.props.record);
        });
        onMounted(() => this.renderPages());
        onWillUpdateProps(async (next) => {
            if (this.signature(next.record) !== this.lastSignature) {
                await this.load(next.record);
                this.needsRender = true;
            }
        });
        onPatched(() => {
            if (this.needsRender) {
                this.needsRender = false;
                this.renderPages();
            }
        });
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    get record() {
        return this.props.record;
    }
    get locked() {
        const data = this.record.data;
        return this.isTemplate ? data.request_count > 0 : data.state !== "draft";
    }
    get parties() {
        const list = this.isTemplate ? this.record.data.role_ids : this.record.data.request_item_ids;
        return list.records.map((rec) => ({
            id: rec.resId,
            name: this.isTemplate ? rec.data.display_name : rec.data.signer_name || rec.data.signer_email || "?",
            color: rec.data.color || 1,
        }));
    }
    get hasPendingDocs() {
        return this.record.data.document_ids.records.some((rec) => !rec.resId) || (this.record.isNew && this.record.data.document_ids.records.length);
    }
    get selected() {
        return this.state.items.find((item) => item.id === this.state.selectedId);
    }
    signature(record) {
        return JSON.stringify([record.resId, record.data.document_ids.currentIds]);
    }
    partyOf(item) {
        return this.parties.find((p) => p.id === item[this.partyField]) || { name: "?", color: 0 };
    }
    pagesOf(doc) {
        return Array.from({ length: doc.page_count || 0 }, (_v, index) => index + 1);
    }
    itemsOf(doc, page) {
        return this.state.items.filter((item) => item.document_id === doc.id && item.page === page);
    }
    itemStyle(item) {
        return `left:${item.pos_x * 100}%;top:${item.pos_y * 100}%;width:${item.width * 100}%;height:${item.height * 100}%;`;
    }

    async load(record) {
        this.lastSignature = this.signature(record);
        if (!record.resId) {
            this.state.docs = [];
            this.state.items = [];
            return;
        }
        const domain = [[this.parentField, "=", record.resId]];
        const [docs, items] = await Promise.all([
            this.orm.searchRead("sign.document", domain, ["name", "page_count"], { order: "sequence, id" }),
            this.orm.searchRead("sign.item", domain, [
                "document_id", "page", "pos_x", "pos_y", "width", "height", "type", "required", "readonly",
                "placeholder", "options", "alignment", "linked_field", this.partyField,
            ]),
        ]);
        for (const item of items) {
            item.document_id = m2oId(item.document_id);
            item[this.partyField] = m2oId(item[this.partyField]);
        }
        this.state.docs = docs;
        this.state.items = items;
    }

    async ensureSaved() {
        if (this.record.isNew || this.record.dirty) {
            if (!(await this.record.save())) {
                return false;
            }
        }
        if (this.signature(this.record) !== this.lastSignature) {
            await this.load(this.record);
            this.needsRender = true;
        }
        return true;
    }

    async renderPages() {
        const pdfjsLib = globalThis.pdfjsLib;
        if (!pdfjsLib || !this.root.el) {
            return;
        }
        for (const doc of this.state.docs) {
            const pdf = await pdfjsLib.getDocument({ url: `/web/content/sign.document/${doc.id}/file` }).promise;
            for (const pageNumber of this.pagesOf(doc)) {
                const canvas = this.root.el.querySelector(`canvas[data-doc="${doc.id}"][data-page="${pageNumber}"]`);
                if (!canvas || pageNumber > pdf.numPages) {
                    continue;
                }
                const page = await pdf.getPage(pageNumber);
                const width = Math.max(canvas.parentElement.clientWidth, 900);
                const base = page.getViewport({ scale: 1 });
                const viewport = page.getViewport({ scale: (width / base.width) * (window.devicePixelRatio || 1) });
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
            }
        }
    }

    // ------------------------------------------------------------------
    // Toolbar
    // ------------------------------------------------------------------
    async onLoadDocs() {
        await this.ensureSaved();
    }
    async selectTool(type) {
        if (!(await this.ensureSaved())) {
            return;
        }
        this.state.tool = this.state.tool === type ? false : type;
        if (!this.state.party || !this.parties.some((p) => p.id === this.state.party)) {
            this.state.party = this.parties[0]?.id || false;
        }
    }
    selectParty(party) {
        this.state.party = party.id;
        if (this.selected && !this.locked) {
            this.updateSelected({ [this.partyField]: party.id });
        }
    }

    // ------------------------------------------------------------------
    // Placement, move, resize
    // ------------------------------------------------------------------
    async onPageClick(ev, doc, page) {
        if (this.locked || !this.state.tool) {
            this.state.selectedId = false;
            return;
        }
        if (!this.state.party) {
            this.state.tool = false;
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const type = this.state.tool;
        const [w, h] = TYPE_SIZE[type];
        const vals = {
            [this.parentField]: this.record.resId,
            [this.partyField]: this.state.party,
            document_id: doc.id,
            page,
            type,
            width: w,
            height: h,
            pos_x: clamp((ev.clientX - rect.left) / rect.width, 0, 1 - w),
            pos_y: clamp((ev.clientY - rect.top) / rect.height, 0, 1 - h),
            required: !["checkbox", "strike"].includes(type),
            options: ["radio", "selection"].includes(type) ? `${_t("Option 1")}\n${_t("Option 2")}` : false,
        };
        const [id] = await this.orm.create("sign.item", [vals]);
        this.state.items.push({ id, placeholder: "", readonly: false, alignment: "left", linked_field: false, ...vals });
        this.state.selectedId = id;
        this.state.tool = false;
    }

    startDrag(ev, item, mode) {
        this.state.selectedId = item.id;
        if (this.locked) {
            return;
        }
        ev.preventDefault();
        const pageRect = ev.currentTarget.closest(".o_es_page").getBoundingClientRect();
        const start = { x: ev.clientX, y: ev.clientY, pos_x: item.pos_x, pos_y: item.pos_y, width: item.width, height: item.height };
        let moved = false;
        const onMove = (moveEv) => {
            const dx = (moveEv.clientX - start.x) / pageRect.width;
            const dy = (moveEv.clientY - start.y) / pageRect.height;
            if (Math.abs(dx) + Math.abs(dy) > 0.002) {
                moved = true;
            }
            if (mode === "move") {
                item.pos_x = clamp(start.pos_x + dx, 0, 1 - item.width);
                item.pos_y = clamp(start.pos_y + dy, 0, 1 - item.height);
            } else {
                item.width = clamp(start.width + dx, 0.01, 1 - item.pos_x);
                item.height = clamp(start.height + dy, 0.01, 1 - item.pos_y);
            }
        };
        const onUp = async () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            if (moved) {
                const { pos_x, pos_y, width, height } = item;
                await this.orm.write("sign.item", [item.id], { pos_x, pos_y, width, height });
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    // ------------------------------------------------------------------
    // Properties of the selected field
    // ------------------------------------------------------------------
    async updateSelected(vals) {
        const item = this.selected;
        if (!item) {
            return;
        }
        Object.assign(item, vals);
        await this.orm.write("sign.item", [item.id], vals);
    }
    async deleteSelected() {
        const item = this.selected;
        await this.orm.unlink("sign.item", [item.id]);
        this.state.items = this.state.items.filter((i) => i.id !== item.id);
        this.state.selectedId = false;
    }
    async copyToAllPages() {
        const item = this.selected;
        const doc = this.state.docs.find((d) => d.id === item.document_id);
        const { id, ...vals } = item;
        const pages = this.pagesOf(doc).filter((page) => !this.itemsOf(doc, page).some(
            (other) => other.type === item.type && Math.abs(other.pos_x - item.pos_x) < 0.01 && Math.abs(other.pos_y - item.pos_y) < 0.01
        ));
        if (!pages.length) {
            return;
        }
        const newVals = pages.map((page) => ({ ...vals, page, [this.parentField]: this.record.resId }));
        const ids = await this.orm.create("sign.item", newVals);
        ids.forEach((newId, index) => this.state.items.push({ ...newVals[index], id: newId }));
    }
}

registry.category("fields").add("easy_sign_layout", {
    component: SignLayoutEditor,
    supportedTypes: ["integer"],
});
