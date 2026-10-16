/** Loads each PDF once with Odoo's pdf.js; renders pages and searches their text. */
export class PdfCache {
    constructor() {
        this.docs = new Map();
        this.texts = new Map();
    }

    get(doc) {
        if (!this.docs.has(doc.id)) {
            this.docs.set(doc.id, globalThis.pdfjsLib.getDocument({ url: doc.url }).promise);
        }
        return this.docs.get(doc.id);
    }

    async sizes(doc) {
        const pdf = await this.get(doc);
        const sizes = [];
        for (let number = 1; number <= pdf.numPages; number++) {
            const viewport = (await pdf.getPage(number)).getViewport({ scale: 1 });
            sizes.push({ w: viewport.width, h: viewport.height });
        }
        return sizes;
    }

    async render(doc, number, canvas, cssWidth) {
        const page = await (await this.get(doc)).getPage(number);
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: (cssWidth / base.width) * (window.devicePixelRatio || 1) });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    }

    async pageText(doc, number) {
        const key = `${doc.id}-${number}`;
        if (!this.texts.has(key)) {
            const page = await (await this.get(doc)).getPage(number);
            const content = await page.getTextContent();
            this.texts.set(key, content.items.map((i) => i.str).join(" ").toLowerCase());
        }
        return this.texts.get(key);
    }
}
