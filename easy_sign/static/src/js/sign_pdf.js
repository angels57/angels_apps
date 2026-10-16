/** @odoo-module ignore */
/**
 * Easy Sign — renders the PDF pages with Odoo's pdf.js and places the signer's
 * fields on top, positioned in % of the page so they follow any zoom.
 */
(function () {
    'use strict';

    var LABELS = { signature: 'Sign here', initials: 'Initials', stamp: 'Stamp' };
    var CSS_UNITS = 96 / 72;   // pdf.js: 100% zoom shows PDF points at 96 dpi
    var AUTO_MAX = 1.25;       // "Automatic Zoom" fits the width, up to 125%

    function el(tag, cls, attrs) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
        return node;
    }

    /**
     * @param {HTMLElement} container  pages container (data-documents / data-fields)
     * @param {Object} hooks  onChange(), onImage(field) when a signature/initials box is clicked
     */
    function Fields(container, hooks) {
        this.container = container;
        this.hooks = hooks || {};
        this.onChange = this.hooks.onChange || function () {};
        this.documents = JSON.parse(container.getAttribute('data-documents') || '[]');
        this.fields = JSON.parse(container.getAttribute('data-fields') || '[]');
        this.inputs = {};      // field id -> function returning its value
        this.nodes = {};       // field id -> overlay element
        this.pages = [];       // {page, wrap, canvas, task, generation}
        this.images = { signature: '', initials: '' };
        this.stamps = {};
        this.zoom = 'auto';
    }

    Fields.prototype.render = function () {
        var self = this;
        var pdfjsLib = window.pdfjsLib;
        this.container.innerHTML = '';
        var chain = Promise.resolve();
        this.documents.forEach(function (doc) {
            chain = chain.then(function () {
                if (self.documents.length > 1) {
                    var title = el('div', 'es-pages-title');
                    title.textContent = doc.name;
                    self.container.appendChild(title);
                }
                return pdfjsLib.getDocument({ url: doc.url }).promise.then(function (pdf) {
                    var numbers = [];
                    for (var n = 1; n <= pdf.numPages; n++) { numbers.push(n); }
                    return Promise.all(numbers.map(function (number) { return pdf.getPage(number); }))
                        .then(function (pages) { pages.forEach(function (page, i) { self._addPage(page, doc, i + 1); }); });
                });
            });
        });
        return chain.then(function () { return self.layout(); }).then(function () { self.onChange(); });
    };

    Fields.prototype._addPage = function (page, doc, number) {
        var self = this;
        var wrap = el('div', 'es-page');
        var canvas = el('canvas');
        wrap.appendChild(canvas);
        this.container.appendChild(wrap);
        this.fields.filter(function (f) { return f.doc === doc.id && f.page === number; })
            .forEach(function (field) { wrap.appendChild(self._buildField(field)); });
        this.pages.push({ page: page, wrap: wrap, canvas: canvas, task: null, generation: 0 });
    };

    /** CSS width of a page for the current zoom. */
    Fields.prototype._cssWidth = function (page) {
        var natural = page.getViewport({ scale: 1 }).width * CSS_UNITS;
        if (this.zoom !== 'auto') { return natural * this.zoom; }
        // Measure the scrolling viewer: the pages container grows with its pages.
        var style = window.getComputedStyle(this.container);
        var room = (this.container.parentElement || this.container).clientWidth
            - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return Math.max(160, Math.min(room, natural * AUTO_MAX));
    };

    /** Size every page for the current zoom and (re)draw it. */
    Fields.prototype.layout = function () {
        var self = this;
        return Promise.all(this.pages.map(function (entry) {
            var width = self._cssWidth(entry.page);
            entry.wrap.style.width = width + 'px';
            entry.wrap.style.setProperty('--es-k', (width / entry.page.getViewport({ scale: 1 }).width).toFixed(3));
            return self._draw(entry, width);
        }));
    };

    /** Draw a page; a newer draw of the same page cancels the running one. */
    Fields.prototype._draw = function (entry, cssWidth) {
        var generation = ++entry.generation;
        var start = entry.task ? entry.task.promise.catch(function () {}) : Promise.resolve();
        if (entry.task) { entry.task.cancel(); }
        return start.then(function () {
            if (entry.generation !== generation) { return; }
            var base = entry.page.getViewport({ scale: 1 });
            var viewport = entry.page.getViewport({ scale: (cssWidth / base.width) * (window.devicePixelRatio || 1) });
            entry.canvas.width = viewport.width;
            entry.canvas.height = viewport.height;
            var task = entry.page.render({ canvasContext: entry.canvas.getContext('2d'), viewport: viewport });
            entry.task = task;
            return task.promise.catch(function (error) {
                if (!error || error.name !== 'RenderingCancelledException') { throw error; }
            }).then(function () { if (entry.task === task) { entry.task = null; } });
        });
    };

    Fields.prototype.setZoom = function (zoom) {
        this.zoom = zoom === 'auto' ? 'auto' : Math.min(4, Math.max(0.25, Number(zoom)));
        return this.layout();
    };

    /** Current scale as a number, also for "auto". */
    Fields.prototype.scale = function () {
        if (this.zoom !== 'auto') { return this.zoom; }
        var entry = this.pages[0];
        return entry ? this._cssWidth(entry.page) / (entry.page.getViewport({ scale: 1 }).width * CSS_UNITS) : 1;
    };

    Fields.prototype._buildField = function (field) {
        var self = this;
        var box = el('div', 'es-field es-field-' + field.type + (field.required ? ' es-required' : ''));
        box.style.left = (field.x * 100) + '%';
        box.style.top = (field.y * 100) + '%';
        box.style.width = (field.w * 100) + '%';
        box.style.height = (field.h * 100) + '%';
        var input;
        var changed = function () { self.onChange(); };
        if (field.type === 'signature' || field.type === 'initials') {
            input = el('button', 'es-field-image', { type: 'button' });
            input.textContent = LABELS[field.type];
            input.addEventListener('click', function () {
                if (self.hooks.onImage) { self.hooks.onImage(field); }
            });
            this.inputs[field.id] = function () { return self.images[field.type] || (field.type === 'initials' && self.images.signature) ? '1' : ''; };
        } else if (field.type === 'stamp') {
            input = el('label', 'es-field-image');
            input.textContent = LABELS.stamp;
            var file = el('input', 'es-hidden', { type: 'file', accept: 'image/png,image/jpeg' });
            input.appendChild(file);
            file.addEventListener('change', function () {
                var f = file.files && file.files[0];
                if (!f) { return; }
                var reader = new FileReader();
                reader.onload = function () {
                    self.stamps[field.id] = reader.result;
                    input.style.backgroundImage = 'url(' + reader.result + ')';
                    input.firstChild.textContent = '';
                    changed();
                };
                reader.readAsDataURL(f);
            });
            this.inputs[field.id] = function () { return self.stamps[field.id] || ''; };
        } else if (field.type === 'checkbox' || field.type === 'strike') {
            input = el('input', '', { type: 'checkbox' });
            input.addEventListener('change', function () { box.classList.toggle('es-checked', input.checked); changed(); });
            this.inputs[field.id] = function () { return input.checked ? '1' : ''; };
        } else if (field.type === 'radio') {
            input = el('div', 'es-field-radio');
            field.options.forEach(function (option) {
                var label = el('label');
                var radio = el('input', '', { type: 'radio', name: 'es-radio-' + field.id, value: option });
                radio.addEventListener('change', changed);
                label.appendChild(radio);
                label.appendChild(document.createTextNode(' ' + option));
                input.appendChild(label);
            });
            this.inputs[field.id] = function () {
                var checked = input.querySelector('input:checked');
                return checked ? checked.value : '';
            };
        } else if (field.type === 'selection') {
            input = el('select');
            input.appendChild(el('option', '', { value: '' }));
            field.options.forEach(function (option) {
                var opt = el('option', '', { value: option });
                opt.textContent = option;
                input.appendChild(opt);
            });
            input.value = field.value || '';
            input.addEventListener('change', changed);
            this.inputs[field.id] = function () { return input.value; };
        } else {
            input = field.type === 'textarea' ? el('textarea') : el('input', '', { type: field.type === 'date' ? 'date' : 'text' });
            input.value = field.value || '';
            input.placeholder = field.placeholder;
            input.style.textAlign = field.align;
            input.maxLength = 2000;
            input.addEventListener('input', changed);
            input.addEventListener('change', changed);
            this.inputs[field.id] = function () { return input.value; };
        }
        if (field.readonly) {
            input.disabled = true;
        }
        box.appendChild(input);
        this.nodes[field.id] = box;
        return box;
    };

    Fields.prototype.setImages = function (signature, initials) {
        var self = this;
        this.images.signature = signature;
        this.images.initials = initials;
        this.fields.forEach(function (field) {
            if (field.type !== 'signature' && field.type !== 'initials') { return; }
            var button = self.nodes[field.id] && self.nodes[field.id].firstChild;
            if (!button) { return; }
            var url = field.type === 'initials' ? (initials || signature) : signature;
            button.style.backgroundImage = url ? 'url(' + url + ')' : '';
            button.textContent = url ? '' : LABELS[field.type];
            self.nodes[field.id].classList.toggle('es-done', !!url);
        });
        this.onChange();
    };

    Fields.prototype.values = function () {
        var self = this;
        var out = {};
        this.fields.forEach(function (field) {
            if (!field.readonly) { out[field.id] = self.inputs[field.id](); }
        });
        return out;
    };

    Fields.prototype.missing = function () {
        var self = this;
        return this.fields.filter(function (field) {
            var fn = self.inputs[field.id];
            return field.required && !field.readonly && field.type !== 'strike' && (!fn || !fn());
        });
    };

    /** Scroll to the next required field; focus it unless told not to. */
    Fields.prototype.focusNextMissing = function (noFocus) {
        var next = this.missing()[0];
        var node = next && this.nodes[next.id];
        if (node) {
            node.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            var input = node.querySelector('input, textarea, select');
            if (input && !noFocus) { input.focus({ preventScroll: true }); }
            node.classList.add('es-flash');
            setTimeout(function () { node.classList.remove('es-flash'); }, 1200);
        }
        return next;
    };

    window.EasySign = window.EasySign || {};
    window.EasySign.Fields = Fields;
})();
