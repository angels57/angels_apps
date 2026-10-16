import { Component, onMounted, onPatched, useRef } from "@odoo/owl";

export class EditorViewer extends Component {
    static template = "easy_sign.EditorViewer";
    static props = { store: Object };

    setup() {
        this.root = useRef("pages");
        this.renderedKey = "";
        onMounted(() => this.renderPages());
        onPatched(() => this.renderPages());
    }

    get store() {
        return this.props.store;
    }
    get state() {
        return this.store.state;
    }
    pagesOf(doc) {
        return Array.from({ length: doc.page_count || 0 }, (_v, index) => index + 1);
    }
    itemStyle(item) {
        return `left:${item.pos_x * 100}%;top:${item.pos_y * 100}%;width:${item.width * 100}%;height:${item.height * 100}%;`;
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
}
