import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { pickPdfFiles } from "./list_upload";
import { useProps, useState } from "./owl_compat";
import { clamp, newItemVals } from "./palette";

export class EditorPanel extends Component {
    static template = "easy_sign.EditorPanel";
    static components = { Dropdown };

    setup() {
        this.props = useProps(); // store
        this.dialog = useService("dialog");
        this.state = useState(this.props.store.state);
    }

    get store() {
        return this.props.store;
    }
    get locked() {
        return this.state.data?.locked;
    }
    get palette() {
        return this.state.data?.palette || [];
    }
    onAddFieldType() {
        this.dialog.add(FormViewDialog, {
            resModel: "sign.item.type",
            title: _t("New Field"),
            onRecordSaved: () => this.store.load(),
        });
    }
    countOf(party) {
        return this.state.items.filter((item) => item[this.store.partyField] === party.id).length;
    }

    selectParty(party) {
        this.state.party = party.id;
    }

    // ------------------------------------------------------------------
    // Documents
    // ------------------------------------------------------------------
    async onAddDocument() {
        const files = await pickPdfFiles();
        if (files.length) {
            await this.store.addDocuments(files);
        }
    }
    docMenu(doc) {
        const items = [
            { label: _t("Rename"), onSelected: () => this.openDialog("sign.document", doc.id, _t("Document")) },
            { label: _t("Move up"), onSelected: () => this.store.moveDocument(doc, -1) },
            { label: _t("Move down"), onSelected: () => this.store.moveDocument(doc, 1) },
        ];
        if (this.state.documents.length > 1) {
            items.push({ label: _t("Remove"), onSelected: () => this.store.removeDocument(doc) });
        }
        return items;
    }

    // ------------------------------------------------------------------
    // Signers / roles
    // ------------------------------------------------------------------
    async onAddParty() {
        const party = await this.store.addParty();
        this.openDialog(party.model, party.id, _t("Signer"));
    }
    partyMenu(party) {
        const items = [{ label: _t("Edit"), onSelected: () => this.openDialog(party.model, party.id, _t("Signer")) }];
        if (!this.locked) {
            items.push({ label: _t("Remove"), onSelected: () => this.store.removeParty(party) });
        }
        return items;
    }
    openDialog(resModel, resId, title) {
        this.dialog.add(FormViewDialog, {
            resModel,
            resId,
            title,
            onRecordSaved: () => this.store.load(),
        });
    }

    // ------------------------------------------------------------------
    // Palette: drag a field onto a page (or click: centre of the visible page)
    // ------------------------------------------------------------------
    onPalettePointerDown(ev, entry) {
        if (this.locked || !this.state.party) {
            return;
        }
        ev.preventDefault();
        const start = { x: ev.clientX, y: ev.clientY };
        const ghost = document.createElement("div");
        ghost.className = `o_es_ghost o_es_c${(this.state.parties.find((p) => p.id === this.state.party)?.color || 0) % 12}`;
        ghost.textContent = entry.label;
        let dragging = false;
        const onMove = (moveEv) => {
            if (!dragging && Math.hypot(moveEv.clientX - start.x, moveEv.clientY - start.y) > 4) {
                dragging = true;
                document.body.appendChild(ghost);
            }
            if (dragging) {
                ghost.style.left = `${moveEv.clientX + 6}px`;
                ghost.style.top = `${moveEv.clientY + 6}px`;
            }
        };
        const onUp = async (upEv) => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            ghost.remove();
            const vals = newItemVals(entry);
            const page = dragging
                ? document.elementFromPoint(upEv.clientX, upEv.clientY)?.closest(".o_es_page")
                : this.visiblePage();
            if (!page) {
                return;
            }
            const rect = page.getBoundingClientRect();
            const x = dragging ? (upEv.clientX - rect.left) / rect.width : 0.5;
            const y = dragging ? (upEv.clientY - rect.top) / rect.height : 0.4;
            await this.store.createItem({
                ...vals,
                document_id: Number(page.dataset.doc),
                page: Number(page.dataset.page),
                pos_x: clamp(x - (dragging ? 0 : vals.width / 2), 0, 1 - vals.width),
                pos_y: clamp(y - vals.height / 2, 0, 1 - vals.height),
            });
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    visiblePage() {
        const pages = [...document.querySelectorAll(".o_es_editor_action .o_es_page")];
        const middle = window.innerHeight / 2;
        return pages.find((p) => {
            const r = p.getBoundingClientRect();
            return r.top <= middle && r.bottom >= middle;
        }) || pages[0];
    }
}
