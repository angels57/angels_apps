/** @odoo-module ignore */
/**
 * Angels Sign — signature pad with three modes: Auto (the name in a handwriting
 * font), Draw and Load (PNG/JPEG fitted into the pad), plus an optional frame
 * "Signed with Angels Sign" (in the page language) with the document code. The pad keeps what was
 * entered and redraws it, so the frame and the font can change at any time.
 * The result is always the canvas as PNG, so the server validates one format.
 */
(function () {
    'use strict';

    var INK = '#0a1a6b';
    var FRAME = '#5f97a3';
    var TEXT = {
        en: { frame: 'Signed with Angels Sign', image: 'Use a PNG or JPEG image up to 2 MB.' },
        es: { frame: 'Firmado con Angels Sign', image: 'Usa una imagen PNG o JPEG de hasta 2 MB.' },
    };
    var FONTS = ['LaBelleAurore', 'MarckScript', 'ShadowsIntoLight', 'Zeyada', 'ReenieBeanie', 'OoohBaby'];

    function t(key) {
        return TEXT[window.AngelsSign && window.AngelsSign.lang && window.AngelsSign.lang() === 'es' ? 'es' : 'en'][key];
    }

    function Pad(root, onChange) {
        this.root = root;
        this.onChange = onChange || function () {};
        this.canvas = root.querySelector('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.hint = root.querySelector('.es-canvas-hint');
        this.text = root.querySelector('.es-pad-text');
        this.file = root.querySelector('.es-pad-file');
        this.clearButton = root.querySelector('.es-pad-clear');
        this.frameInput = root.querySelector('.es-pad-frame-input');
        this.fontList = root.querySelector('.es-font-list');
        this.code = root.getAttribute('data-frame-code') || '';
        this.font = FONTS[0];
        this.mode = 'type';
        this.strokes = [];     // Draw: list of point lists, in canvas units
        this.image = null;     // Load: the image element
        this.adopted = null;   // image shown by load(), until something new is entered
        this.filled = false;
        this.drawing = false;
        this._bind();
        this.setMode('type', true);
        this._loadFonts();
    }

    Pad.prototype._bind = function () {
        var self = this;
        this.root.querySelectorAll('.es-pad-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { self.setMode(tab.getAttribute('data-mode')); });
        });
        this.clearButton.addEventListener('click', function () { self.clear(); });
        this.text.addEventListener('input', function () {
            if (self.mode !== 'type') { self.setMode('type', true); }
            self._render();
        });
        this.file.addEventListener('change', function () { self._readFile(); });
        this.frameInput.addEventListener('change', function () { self.adopted = null; self._render(); });

        var toggle = this.root.querySelector('.es-font-toggle');
        toggle.addEventListener('click', function (ev) {
            ev.stopPropagation();
            self.fontList.classList.toggle('es-hidden');
        });
        this.fontList.querySelectorAll('.es-font-item').forEach(function (item) {
            item.addEventListener('click', function () {
                self.font = item.getAttribute('data-font');
                self.fontList.classList.add('es-hidden');
                self.setMode('type', true);
            });
        });
        document.addEventListener('click', function (ev) {
            if (!self.fontList.contains(ev.target)) { self.fontList.classList.add('es-hidden'); }
        });

        var start = function (ev) {
            if (self.mode !== 'draw') { return; }
            ev.preventDefault();
            self.canvas.setPointerCapture(ev.pointerId);
            self.drawing = true;
            self.adopted = null;
            self.strokes.push([self._point(ev)]);
            self._render();
        };
        var move = function (ev) {
            if (!self.drawing) { return; }
            ev.preventDefault();
            self.strokes[self.strokes.length - 1].push(self._point(ev));
            self._render();
        };
        var end = function () { self.drawing = false; };
        this.canvas.addEventListener('pointerdown', start);
        this.canvas.addEventListener('pointermove', move);
        this.canvas.addEventListener('pointerup', end);
        this.canvas.addEventListener('pointercancel', end);
        // The frame text follows the language until a signature is adopted.
        document.addEventListener('es-lang', function () { if (!self.adopted) { self._render(); } });
    };

    /** The handwriting fonts ship with Odoo (web/static/fonts/sign); draw again once loaded. */
    Pad.prototype._loadFonts = function () {
        var self = this;
        if (!document.fonts || !document.fonts.load) { return; }
        Promise.all(FONTS.map(function (font) { return document.fonts.load('40px "' + font + '"'); }))
            .then(function () { self._render(); }, function () {});
    };

    Pad.prototype._point = function (ev) {
        var rect = this.canvas.getBoundingClientRect();
        return {
            x: (ev.clientX - rect.left) * (this.canvas.width / rect.width),
            y: (ev.clientY - rect.top) * (this.canvas.height / rect.height),
        };
    };

    /** Area left for the signature: inside the frame when it is on. */
    Pad.prototype._box = function () {
        var w = this.canvas.width;
        var h = this.canvas.height;
        if (!this.frameInput.checked) { return { x: w * 0.05, y: h * 0.1, w: w * 0.9, h: h * 0.8 }; }
        return { x: w * 0.1, y: h * 0.17, w: w * 0.84, h: h * 0.55 };
    };

    Pad.prototype._drawFrame = function () {
        var ctx = this.ctx;
        var sx = this.canvas.width / 600;
        var sy = this.canvas.height / 200;
        var r = 18 * Math.min(sx, sy);
        ctx.save();
        ctx.strokeStyle = FRAME;
        ctx.lineWidth = 3 * Math.min(sx, sy);
        ctx.beginPath();
        ctx.moveTo(112 * sx, 18 * sy);
        ctx.lineTo(22 * sx + r, 18 * sy);
        ctx.arcTo(22 * sx, 18 * sy, 22 * sx, 18 * sy + r, r);
        ctx.lineTo(22 * sx, 182 * sy - r);
        ctx.arcTo(22 * sx, 182 * sy, 22 * sx + r, 182 * sy, r);
        ctx.lineTo(112 * sx, 182 * sy);
        ctx.stroke();
        ctx.strokeStyle = '#c4cad3';
        ctx.lineWidth = 1.5 * Math.min(sx, sy);
        ctx.beginPath();
        ctx.moveTo(62 * sx, 152 * sy);
        ctx.lineTo(560 * sx, 152 * sy);
        ctx.stroke();
        ctx.fillStyle = FRAME;
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'left';
        ctx.font = 'bold ' + Math.round(15 * sy) + 'px "Segoe UI", Arial, sans-serif';
        ctx.fillText(t('frame'), 120 * sx, 18 * sy);
        if (this.code) {
            ctx.font = Math.round(14 * sy) + 'px Menlo, Consolas, monospace';
            ctx.fillText(this.code + '...', 120 * sx, 182 * sy);
        }
        ctx.restore();
    };

    Pad.prototype._render = function () {
        var ctx = this.ctx;
        var w = this.canvas.width;
        var h = this.canvas.height;
        ctx.clearRect(0, 0, w, h);
        if (this.adopted) {
            ctx.drawImage(this.adopted, 0, 0, w, h);
            this._setFilled(true);
            return;
        }
        if (this.frameInput.checked) { this._drawFrame(); }
        ctx.strokeStyle = INK;
        ctx.fillStyle = INK;
        var filled = false;
        var box = this._box();
        if (this.mode === 'type') {
            var value = (this.text.value || '').trim();
            if (value) {
                var size = Math.round(box.h * 1.1);
                do {
                    ctx.font = size + 'px "' + this.font + '", cursive';
                    size -= 2;
                } while (ctx.measureText(value).width > box.w && size > 10);
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(value, box.x + box.w / 2, box.y + box.h / 2);
                filled = true;
            }
        } else if (this.mode === 'draw') {
            ctx.lineWidth = Math.max(2, w / 200);
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            this.strokes.forEach(function (points) {
                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                points.forEach(function (p) { ctx.lineTo(p.x, p.y); });
                if (points.length === 1) { ctx.lineTo(points[0].x + 0.1, points[0].y); }
                ctx.stroke();
            });
            filled = this.strokes.some(function (points) { return points.length > 1; });
        } else if (this.mode === 'upload' && this.image) {
            var ratio = Math.min(box.w / this.image.width, box.h / this.image.height);
            var iw = this.image.width * ratio;
            var ih = this.image.height * ratio;
            ctx.drawImage(this.image, box.x + (box.w - iw) / 2, box.y + (box.h - ih) / 2, iw, ih);
            filled = true;
        }
        this._setFilled(filled);
    };

    Pad.prototype._setFilled = function (filled) {
        this.filled = filled;
        if (this.hint) { this.hint.classList.toggle('hidden', filled || this.mode === 'type'); }
        this.clearButton.classList.toggle('es-hidden', !filled || this.mode === 'type');
        this.onChange(this);
    };

    Pad.prototype.clear = function () {
        this.adopted = null;
        this.strokes = [];
        this.image = null;
        this.file.value = '';
        this._render();
    };

    Pad.prototype.setMode = function (mode, silent) {
        this.mode = mode;
        this.adopted = null;
        this.root.querySelectorAll('.es-pad-tab').forEach(function (tab) {
            tab.classList.toggle('active', tab.getAttribute('data-mode') === mode);
        });
        this.canvas.style.cursor = mode === 'draw' ? 'crosshair' : 'default';
        this.root.classList.toggle('es-pad-drawing', mode === 'draw');
        this._render();
        if (mode === 'upload' && !silent) { this.file.click(); }
    };

    Pad.prototype._readFile = function () {
        var self = this;
        var file = this.file.files && this.file.files[0];
        if (!file) { return; }
        if (file.size > 2 * 1024 * 1024 || !/^image\/(png|jpeg)$/.test(file.type)) {
            this.file.value = '';
            window.alert(t('image'));
            return;
        }
        var img = new Image();
        img.onload = function () {
            URL.revokeObjectURL(img.src);
            self.image = img;
            self.adopted = null;
            self._render();
        };
        img.src = URL.createObjectURL(file);
    };

    /** Show an image adopted earlier (used to undo a cancelled edit). */
    Pad.prototype.load = function (dataURL) {
        var self = this;
        var img = new Image();
        img.onload = function () {
            self.adopted = img;
            self._render();
        };
        img.src = dataURL;
    };

    Pad.prototype.dataURL = function () {
        return this.filled ? this.canvas.toDataURL('image/png') : '';
    };

    window.AngelsSign = window.AngelsSign || {};
    window.AngelsSign.Pad = Pad;
})();
