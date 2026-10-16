/** @odoo-module ignore */
/**
 * Easy Sign — signature pad with three modes: draw, type (name in a script
 * font) and upload (PNG/JPEG fitted into the pad). The result is always the
 * canvas as PNG, so the server validates a single format.
 */
(function () {
    'use strict';

    var SCRIPT_FONT = '"Z003", "URW Chancery L", "Apple Chancery", "Segoe Script", "Brush Script MT", cursive';

    function Pad(root, onChange) {
        this.root = root;
        this.onChange = onChange || function () {};
        this.canvas = root.querySelector('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.hint = root.querySelector('.es-canvas-hint');
        this.status = root.querySelector('.es-pad-status');
        this.text = root.querySelector('.es-pad-text');
        this.file = root.querySelector('.es-pad-file');
        this.mode = 'draw';
        this.filled = false;
        this.drawing = false;
        this._bind();
        this.clear();
    }

    Pad.prototype._bind = function () {
        var self = this;
        this.root.querySelectorAll('.es-pad-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { self.setMode(tab.getAttribute('data-mode')); });
        });
        this.root.querySelector('.es-pad-clear').addEventListener('click', function () {
            self.clear();
            if (self.text) { self.text.value = ''; }
            if (self.file) { self.file.value = ''; }
        });
        this.text.addEventListener('input', function () { self._drawText(); });
        this.file.addEventListener('change', function () { self._drawFile(); });
        var start = function (ev) {
            if (self.mode !== 'draw') { return; }
            ev.preventDefault();
            self.drawing = true;
            var p = self._point(ev);
            self.ctx.beginPath();
            self.ctx.moveTo(p.x, p.y);
        };
        var move = function (ev) {
            if (!self.drawing) { return; }
            ev.preventDefault();
            var p = self._point(ev);
            self.ctx.lineTo(p.x, p.y);
            self.ctx.stroke();
            self._setFilled(true);
        };
        var end = function () { self.drawing = false; };
        this.canvas.addEventListener('pointerdown', start);
        this.canvas.addEventListener('pointermove', move);
        window.addEventListener('pointerup', end);
        this.canvas.addEventListener('pointerleave', end);
    };

    Pad.prototype._point = function (ev) {
        var rect = this.canvas.getBoundingClientRect();
        return {
            x: (ev.clientX - rect.left) * (this.canvas.width / rect.width),
            y: (ev.clientY - rect.top) * (this.canvas.height / rect.height),
        };
    };

    Pad.prototype._reset = function () {
        var ctx = this.ctx;
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.strokeStyle = '#1a1a2e';
        ctx.fillStyle = '#1a1a2e';
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
    };

    Pad.prototype._setFilled = function (filled) {
        this.filled = filled;
        if (this.hint) { this.hint.classList.toggle('hidden', filled); }
        if (this.status) { this.status.textContent = filled ? '✓' : ''; }
        this.onChange(this);
    };

    Pad.prototype.clear = function () {
        this._reset();
        this._setFilled(false);
    };

    Pad.prototype.setMode = function (mode) {
        this.mode = mode;
        this.root.querySelectorAll('.es-pad-tab').forEach(function (tab) {
            tab.classList.toggle('active', tab.getAttribute('data-mode') === mode);
        });
        this.text.classList.toggle('es-hidden', mode !== 'type');
        this.file.classList.toggle('es-hidden', mode !== 'upload');
        this.canvas.style.cursor = mode === 'draw' ? 'crosshair' : 'default';
        this.clear();
        if (mode === 'type') {
            this.text.focus();
            this._drawText();
        } else if (mode === 'upload') {
            this.file.click();
        }
    };

    Pad.prototype._drawText = function () {
        this._reset();
        var value = (this.text.value || '').trim();
        if (!value) { this._setFilled(false); return; }
        var size = Math.round(this.canvas.height * 0.45);
        var ctx = this.ctx;
        do {
            ctx.font = 'italic ' + size + 'px ' + SCRIPT_FONT;
            size -= 2;
        } while (ctx.measureText(value).width > this.canvas.width * 0.9 && size > 10);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(value, this.canvas.width / 2, this.canvas.height / 2);
        this._setFilled(true);
    };

    Pad.prototype._drawFile = function () {
        var self = this;
        var file = this.file.files && this.file.files[0];
        if (!file) { return; }
        if (file.size > 2 * 1024 * 1024 || !/^image\/(png|jpeg)$/.test(file.type)) {
            this.file.value = '';
            window.alert('Use a PNG or JPEG image up to 2 MB.');
            return;
        }
        var img = new Image();
        img.onload = function () {
            self._reset();
            var ratio = Math.min(self.canvas.width / img.width, self.canvas.height / img.height);
            var w = img.width * ratio;
            var h = img.height * ratio;
            self.ctx.drawImage(img, (self.canvas.width - w) / 2, (self.canvas.height - h) / 2, w, h);
            URL.revokeObjectURL(img.src);
            self._setFilled(true);
        };
        img.src = URL.createObjectURL(file);
    };

    Pad.prototype.dataURL = function () {
        return this.filled ? this.canvas.toDataURL('image/png') : '';
    };

    window.EasySign = window.EasySign || {};
    window.EasySign.Pad = Pad;
})();
