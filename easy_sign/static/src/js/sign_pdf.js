/** @odoo-module ignore */
/**
 * Easy Sign — renders the PDF pages with Odoo's pdf.js and places the signer's
 * fields on top, positioned in % of the page so they follow any zoom.
 */
(function () {
    'use strict';

    var LABELS = { signature: 'Sign here', initials: 'Initials', stamp: 'Stamp' };

    function el(tag, cls, attrs) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
        return node;
    }

    function Fields(container, onChange) {
        this.container = container;
        this.onChange = onChange || function () {};
        this.documents = JSON.parse(container.getAttribute('data-documents') || '[]');
        this.fields = JSON.parse(container.getAttribute('data-fields') || '[]');
        this.inputs = {};      // field id -> function returning its value
        this.nodes = {};       // field id -> overlay element
        this.images = { signature: '', initials: '' };
        this.stamps = {};
    }

    Fields.prototype.render = function () {
        var self = this;
        var pdfjsLib = window.pdfjsLib;
        this.container.innerHTML = '';
        var chain = Promise.resolve();
        this.documents.forEach(function (doc) {
            chain = chain.then(function () {
                var title = el('div', 'es-pages-title');
                title.textContent = doc.name;
                self.container.appendChild(title);
                return pdfjsLib.getDocument({ url: doc.url }).promise.then(function (pdf) {
                    var pages = [];
                    for (var n = 1; n <= pdf.numPages; n++) { pages.push(n); }
                    return pages.reduce(function (prev, number) {
                        return prev.then(function () { return self._renderPage(pdf, doc, number); });
                    }, Promise.resolve());
                });
            });
        });
        return chain.then(function () { self.onChange(); });
    };

    Fields.prototype._renderPage = function (pdf, doc, number) {
        var self = this;
        return pdf.getPage(number).then(function (page) {
            var wrap = el('div', 'es-page');
            var canvas = el('canvas');
            wrap.appendChild(canvas);
            self.container.appendChild(wrap);
            var base = page.getViewport({ scale: 1 });
            var width = self.container.clientWidth - 32 || base.width;
            var viewport = page.getViewport({ scale: (width / base.width) * (window.devicePixelRatio || 1) });
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            self.fields.filter(function (f) { return f.doc === doc.id && f.page === number; })
                .forEach(function (field) { wrap.appendChild(self._buildField(field)); });
            return page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport }).promise;
        });
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
                var pad = document.querySelector('[data-pad="' + field.type + '"]') || document.querySelector('[data-pad="signature"]');
                if (pad) { pad.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
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

    Fields.prototype.focusNextMissing = function () {
        var next = this.missing()[0];
        var node = next && this.nodes[next.id];
        if (node) {
            node.scrollIntoView({ behavior: 'smooth', block: 'center' });
            var input = node.querySelector('input, textarea, select, button');
            if (input) { input.focus({ preventScroll: true }); }
            node.classList.add('es-flash');
            setTimeout(function () { node.classList.remove('es-flash'); }, 1200);
        }
        return next;
    };

    window.EasySign = window.EasySign || {};
    window.EasySign.Fields = Fields;
})();
