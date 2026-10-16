import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { FieldPopover } from "./field_popover";
import { clamp, itemLabel } from "./palette";
import { PdfCache } from "./pdf_cache";

const SNAP = 0.006;
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const PT_TO_PX = 96 / 72;

export class EditorViewer extends Component {
    static template = "easy_sign.EditorViewer";
    static components = { FieldPopover };
    static props = { store: Object };

    setup() {
        this.root = useRef("pages");
        this.itemLabel = (item) => itemLabel(item, this.state.data?.palette);
        this.zooms = ZOOMS;
        this.pdf = new PdfCache();
        this.view = useState({
            guides: [], zoom: "auto", pageIndex: 0, thumbs: false,
            query: "", results: [], resultIndex: -1, sizes: {}, flash: "", width: 900,
        });
        this.state = useState(this.props.store.state);
        this.clipboard = null;
        this.onKeyDown = this.onKeyDown.bind(this);
        this.observer = new IntersectionObserver((entries) => this.onVisible(entries), { rootMargin: "400px" });
        this.resizer = new ResizeObserver(() => this.onResize());
        onMounted(() => {
            window.addEventListener("keydown", this.onKeyDown);
            this.resizer.observe(this.root.el);
            this.onResize();
            this.loadSizes();
        });
        onPatched(() => this.observePages());
        onWillUnmount(() => {
            window.removeEventListener("keydown", this.onKeyDown);
            this.observer.disconnect();
            this.resizer.disconnect();
        });
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
    get allPages() {
        return this.state.documents.flatMap((doc) => this.pagesOf(doc).map((page) => ({ doc, page })));
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

    // ------------------------------------------------------------------
    // Page size, zoom and lazy rendering
    // ------------------------------------------------------------------
    async loadSizes() {
        const sizes = {};
        for (const doc of this.state.documents) {
            (await this.pdf.sizes(doc)).forEach((size, index) => (sizes[`${doc.id}-${index + 1}`] = size));
        }
        this.view.sizes = sizes;
    }
    pageWidth(doc, page) {
        const size = this.view.sizes[`${doc.id}-${page}`] || { w: 595, h: 842 };
        return this.view.zoom === "auto" ? this.view.width : size.w * this.view.zoom * PT_TO_PX;
    }
    pageStyle(doc, page) {
        const size = this.view.sizes[`${doc.id}-${page}`] || { w: 595, h: 842 };
        return `width:${this.pageWidth(doc, page)}px;aspect-ratio:${size.w} / ${size.h};`;
    }
    onResize() {
        if (this.root.el) {
            this.view.width = Math.max(320, Math.min(this.root.el.clientWidth - 48, 1100));
        }
    }
    zoomLabel(zoom) {
        return `${Math.round(zoom * 100)}%`;
    }
    setZoom(zoom) {
        this.view.zoom = zoom;
    }
    zoomStep(delta) {
        const current = this.view.zoom === "auto" ? this.view.width / (595 * PT_TO_PX) : this.view.zoom;
        const next = ZOOMS.find((z) => (delta > 0 ? z > current + 0.01 : false)) ||
            [...ZOOMS].reverse().find((z) => (delta < 0 ? z < current - 0.01 : false));
        if (next) {
            this.view.zoom = next;
        }
    }
    observePages() {
        if (!this.root.el) {
            return;
        }
        for (const el of this.root.el.querySelectorAll(".o_es_page")) {
            this.observer.observe(el);
            if (el.dataset.visible === "1") {
                this.renderPage(el);
            }
        }
    }
    onVisible(entries) {
        for (const entry of entries) {
            entry.target.dataset.visible = entry.isIntersecting ? "1" : "0";
            if (entry.isIntersecting) {
                this.renderPage(entry.target);
            }
        }
    }
    async renderPage(el) {
        const width = Math.round(el.clientWidth);
        if (!width || el.dataset.rendered === String(width)) {
            return;
        }
        el.dataset.rendered = String(width);
        const doc = this.state.documents.find((d) => d.id === Number(el.dataset.doc));
        if (doc) {
            await this.pdf.render(doc, Number(el.dataset.page), el.querySelector("canvas"), width);
        }
    }
    async renderThumb(canvas) {
        if (canvas && !canvas.dataset.rendered) {
            canvas.dataset.rendered = "1";
            const doc = this.state.documents.find((d) => d.id === Number(canvas.dataset.doc));
            await this.pdf.render(doc, Number(canvas.dataset.page), canvas, 110);
        }
    }

    // ------------------------------------------------------------------
    // Page navigation, thumbnails and search
    // ------------------------------------------------------------------
    onScroll() {
        const top = this.root.el.getBoundingClientRect().top + 40;
        const pages = [...this.root.el.querySelectorAll(".o_es_page")];
        const index = pages.findIndex((el) => el.getBoundingClientRect().bottom > top);
        if (index >= 0 && index !== this.view.pageIndex) {
            this.view.pageIndex = index;
        }
    }
    goToPage(index) {
        const pages = this.root.el.querySelectorAll(".o_es_page");
        const target = pages[clamp(index, 0, pages.length - 1)];
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
            this.view.pageIndex = clamp(index, 0, pages.length - 1);
        }
    }
    onPageInput(ev) {
        this.goToPage(Number(ev.target.value) - 1);
    }
    toggleThumbs() {
        this.view.thumbs = !this.view.thumbs;
        if (this.view.thumbs) {
            setTimeout(() => document.querySelectorAll(".o_es_thumb canvas").forEach((c) => this.renderThumb(c)));
        }
    }
    async onSearch(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        const query = ev.target.value.trim().toLowerCase();
        if (query !== this.view.query) {
            this.view.query = query;
            this.view.results = [];
            this.view.resultIndex = -1;
            if (query) {
                const pages = this.allPages;
                for (let index = 0; index < pages.length; index++) {
                    if ((await this.pdf.pageText(pages[index].doc, pages[index].page)).includes(query)) {
                        this.view.results.push(index);
                    }
                }
            }
        }
        if (this.view.results.length) {
            this.view.resultIndex = (this.view.resultIndex + 1) % this.view.results.length;
            const index = this.view.results[this.view.resultIndex];
            this.goToPage(index);
            const { doc, page } = this.allPages[index];
            this.view.flash = `${doc.id}-${page}`;
            setTimeout(() => (this.view.flash = ""), 1500);
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
