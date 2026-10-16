import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { FieldPopover } from "./field_popover";
import { clamp, itemLabel } from "./palette";

const SNAP = 0.006;

export class EditorViewer extends Component {
    static template = "easy_sign.EditorViewer";
    static components = { FieldPopover };
    static props = { store: Object };

    setup() {
        this.root = useRef("pages");
        this.itemLabel = itemLabel;
        this.view = useState({ guides: [] });
        this.state = useState(this.props.store.state);
        this.renderedKey = "";
        this.clipboard = null;
        this.onKeyDown = this.onKeyDown.bind(this);
        onMounted(() => {
            this.renderPages();
            window.addEventListener("keydown", this.onKeyDown);
        });
        onPatched(() => this.renderPages());
        onWillUnmount(() => window.removeEventListener("keydown", this.onKeyDown));
    }

    get store() {
        return this.props.store;
    }
    itemsOf(docId, page) {
        return this.state.items.filter((item) => item.document_id === docId && item.page === page);
    }
    partyOf(item) {
        return this.state.parties.find((p) => p.id === item[this.store.partyField]) || { name: "?", color: 0 };
    }
    pagesOf(doc) {
        return Array.from({ length: doc.page_count || 0 }, (_v, index) => index + 1);
    }
    itemStyle(item) {
        return `left:${item.pos_x * 100}%;top:${item.pos_y * 100}%;width:${item.width * 100}%;height:${item.height * 100}%;`;
    }
    guidesOf(doc, page) {
        return this.view.guides.filter((g) => g.doc === doc.id && g.page === page);
    }
    guideStyle(guide) {
        return guide.axis === "x" ? `left:${guide.pos * 100}%;` : `top:${guide.pos * 100}%;`;
    }

    async renderPages() {
        const key = this.state.documents.map((d) => d.id).join(",");
        if (key === this.renderedKey || !globalThis.pdfjsLib || !this.root.el) {
            return;
        }
        this.renderedKey = key;
        for (const doc of this.state.documents) {
            const pdf = await globalThis.pdfjsLib.getDocument({ url: doc.url }).promise;
            for (let number = 1; number <= pdf.numPages; number++) {
                const canvas = this.root.el.querySelector(`canvas[data-doc="${doc.id}"][data-page="${number}"]`);
                if (!canvas) {
                    continue;
                }
                const page = await pdf.getPage(number);
                const base = page.getViewport({ scale: 1 });
                const viewport = page.getViewport({ scale: (1000 / base.width) * (window.devicePixelRatio || 1) });
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
            }
        }
    }

    // ------------------------------------------------------------------
    // Selection, move, resize with alignment guides
    // ------------------------------------------------------------------
    onPageClick() {
        this.state.selectedId = false;
    }

    startDrag(ev, item, mode) {
        this.state.selectedId = item.id;
        if (this.store.locked) {
            return;
        }
        ev.preventDefault();
        const pageEl = ev.currentTarget.closest(".o_es_page");
        const rect = pageEl.getBoundingClientRect();
        const start = { x: ev.clientX, y: ev.clientY, pos_x: item.pos_x, pos_y: item.pos_y, width: item.width, height: item.height };
        const others = this.store.itemsOf(item.document_id, item.page).filter((i) => i.id !== item.id);
        const xs = [0.5, ...others.flatMap((o) => [o.pos_x, o.pos_x + o.width / 2, o.pos_x + o.width])];
        const ys = [0.5, ...others.flatMap((o) => [o.pos_y, o.pos_y + o.height / 2, o.pos_y + o.height])];
        let moved = false;
        const onMove = (moveEv) => {
            const dx = (moveEv.clientX - start.x) / rect.width;
            const dy = (moveEv.clientY - start.y) / rect.height;
            moved = moved || Math.abs(dx) + Math.abs(dy) > 0.002;
            const vals = mode === "move"
                ? { pos_x: clamp(start.pos_x + dx, 0, 1 - item.width), pos_y: clamp(start.pos_y + dy, 0, 1 - item.height) }
                : { width: clamp(start.width + dx, 0.01, 1 - item.pos_x), height: clamp(start.height + dy, 0.01, 1 - item.pos_y) };
            Object.assign(item, vals);
            this.view.guides = this.snap(item, mode, xs, ys);
        };
        const onUp = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            this.view.guides = [];
            if (moved) {
                const { pos_x, pos_y, width, height } = item;
                this.store.updateItem(item, { pos_x, pos_y, width, height });
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    /** Snap the item to the nearest guide on each axis; return the guides to draw. */
    snap(item, mode, xs, ys) {
        const guides = [];
        const best = (edges, candidates) => {
            let found = null;
            for (const [edge, value] of edges) {
                for (const c of candidates) {
                    const d = c - value;
                    if (Math.abs(d) < SNAP && (!found || Math.abs(d) < Math.abs(found.d))) {
                        found = { edge, d, c };
                    }
                }
            }
            return found;
        };
        const xEdges = mode === "move"
            ? [["l", item.pos_x], ["c", item.pos_x + item.width / 2], ["r", item.pos_x + item.width]]
            : [["r", item.pos_x + item.width]];
        const yEdges = mode === "move"
            ? [["t", item.pos_y], ["m", item.pos_y + item.height / 2], ["b", item.pos_y + item.height]]
            : [["b", item.pos_y + item.height]];
        const sx = best(xEdges, xs);
        if (sx) {
            if (mode === "move") {
                item.pos_x = clamp(item.pos_x + sx.d, 0, 1 - item.width);
            } else {
                item.width = clamp(item.width + sx.d, 0.01, 1 - item.pos_x);
            }
            guides.push({ axis: "x", pos: sx.c, doc: item.document_id, page: item.page });
        }
        const sy = best(yEdges, ys);
        if (sy) {
            if (mode === "move") {
                item.pos_y = clamp(item.pos_y + sy.d, 0, 1 - item.height);
            } else {
                item.height = clamp(item.height + sy.d, 0.01, 1 - item.pos_y);
            }
            guides.push({ axis: "y", pos: sy.c, doc: item.document_id, page: item.page });
        }
        return guides;
    }

    // ------------------------------------------------------------------
    // Keyboard: Delete, arrows (Shift = x10), Ctrl+C / Ctrl+V, Escape
    // ------------------------------------------------------------------
    onKeyDown(ev) {
        const item = this.store.selected;
        if (!item || this.store.locked || ev.target.closest("input, textarea, select, .modal")) {
            return;
        }
        const page = this.root.el?.querySelector(`.o_es_page[data-doc="${item.document_id}"][data-page="${item.page}"]`);
        const px = page ? 1 / page.clientWidth : 0.001;
        const py = page ? 1 / page.clientHeight : 0.001;
        const step = ev.shiftKey ? 10 : 1;
        const moves = { ArrowLeft: [-px, 0], ArrowRight: [px, 0], ArrowUp: [0, -py], ArrowDown: [0, py] };
        if (moves[ev.key]) {
            ev.preventDefault();
            const [dx, dy] = moves[ev.key];
            this.store.updateItem(item, {
                pos_x: clamp(item.pos_x + dx * step, 0, 1 - item.width),
                pos_y: clamp(item.pos_y + dy * step, 0, 1 - item.height),
            });
        } else if (ev.key === "Delete" || ev.key === "Backspace") {
            ev.preventDefault();
            this.store.deleteItem(item);
        } else if (ev.key === "Escape") {
            this.state.selectedId = false;
        } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "c") {
            this.clipboard = item;
        } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "v" && this.clipboard) {
            ev.preventDefault();
            const src = this.clipboard;
            this.store.duplicateItem(src, {
                pos_x: clamp(src.pos_x + 0.02, 0, 1 - src.width),
                pos_y: clamp(src.pos_y + 0.02, 0, 1 - src.height),
            });
        }
    }

    async copyToAllPages(item) {
        const doc = this.state.documents.find((d) => d.id === item.document_id);
        for (const page of this.pagesOf(doc)) {
            const exists = this.store.itemsOf(doc.id, page).some(
                (o) => o.type === item.type && Math.abs(o.pos_x - item.pos_x) < 0.01 && Math.abs(o.pos_y - item.pos_y) < 0.01
            );
            if (!exists) {
                await this.store.duplicateItem(item, { page });
            }
        }
        this.state.selectedId = item.id;
    }
}
