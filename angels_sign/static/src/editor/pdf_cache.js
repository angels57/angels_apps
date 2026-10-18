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

    /** Render a page; the latest request on a canvas wins and cancels the previous one (pdf.js forbids overlaps). */
    async render(doc, number, canvas, cssWidth) {
        const generation = (canvas._esGeneration || 0) + 1;
        canvas._esGeneration = generation;
        const page = await (await this.get(doc)).getPage(number);
        if (canvas._esGeneration !== generation) {
            return;
        }
        if (canvas._esTask) {
            canvas._esTask.cancel();
            await canvas._esTask.promise.catch(() => {});
            if (canvas._esGeneration !== generation) {
                return;
            }
        }
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: (cssWidth / base.width) * (window.devicePixelRatio || 1) });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const task = page.render({ canvasContext: canvas.getContext("2d"), viewport });
        canvas._esTask = task;
        try {
            await task.promise;
        } catch (error) {
            if (error?.name !== "RenderingCancelledException") {
                throw error;
            }
        } finally {
            if (canvas._esTask === task) {
                canvas._esTask = null;
            }
        }
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
