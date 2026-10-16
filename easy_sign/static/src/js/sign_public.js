/** @odoo-module ignore */
/**
 * Easy Sign — public signing page: the document viewer (pages, zoom), the
 * ribbon that walks the signer through the fields, the signature / initials,
 * code and decline dialogs, and the sign / decline requests.
 */
(function () {
    'use strict';

    var TEXT = {
        en: {
            start: 'Click to start', sign: 'Sign it', fill: 'Fill in',
            left1: '1 required field left', leftN: '%s required fields left', ready: 'Ready to sign',
            expired: 'Your session has expired. Please reload the page and try again.',
            addSignature: 'Please add your signature.', complete: 'Please complete the highlighted required fields.',
            code: 'Enter the 6-digit code we sent you.', unexpected: 'An unexpected error occurred.',
            network: 'Network error. Please check your connection and try again.',
            declineFailed: 'Failed to decline. Please try again.',
            noDocument: 'The document could not be displayed. Reload the page to try again.',
        },
        ar: {
            start: 'انقر للبدء', sign: 'وقّع', fill: 'املأ',
            left1: 'بقي حقل إلزامي واحد', leftN: 'بقيت %s حقول إلزامية', ready: 'جاهز للتوقيع',
            expired: 'انتهت الجلسة. أعد تحميل الصفحة وحاول مرة أخرى.',
            addSignature: 'يرجى إضافة توقيعك.', complete: 'يرجى إكمال الحقول الإلزامية المحددة.',
            code: 'أدخل الرمز المكون من 6 أرقام الذي أرسلناه إليك.', unexpected: 'حدث خطأ غير متوقع.',
            network: 'خطأ في الشبكة. تحقق من اتصالك وحاول مرة أخرى.',
            declineFailed: 'تعذر الرفض. حاول مرة أخرى.',
            noDocument: 'تعذر عرض الوثيقة. أعد تحميل الصفحة وحاول مرة أخرى.',
        },
    };
    var ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];

    function t(key) {
        var lang = document.documentElement.getAttribute('lang') === 'ar' ? 'ar' : 'en';
        return TEXT[lang][key];
    }
    function byId(id) { return document.getElementById(id); }
    function show(node, visible) { if (node) { node.classList.toggle('es-hidden', !visible); } }

    function post(url, data) {
        var form = new FormData();
        Object.keys(data).forEach(function (key) { form.append(key, data[key]); });
        return fetch(url, { method: 'POST', body: form, credentials: 'same-origin' }).then(function (response) {
            return response.json().then(function (json) { return json; }, function () {
                return { success: false, error: t('expired') };
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var btnSign = byId('btnSign');
        var pagesNode = byId('esPages');
        if (!btnSign || !pagesNode) { return; }
        var token = btnSign.getAttribute('data-token');
        var csrf = btnSign.getAttribute('data-csrf');
        var needsOtp = btnSign.getAttribute('data-otp') === '1';
        var needsSignature = btnSign.getAttribute('data-signature') === '1';
        var viewer = byId('esViewer');
        var ribbon = byId('esRibbon');
        var progressText = byId('esProgressText');
        var otpInput = byId('esOtpInput');
        var started = false;
        var otpRequested = false;
        var toastTimer;

        // ------------------------------------------------------------------
        // Messages
        // ------------------------------------------------------------------
        function toast(id, text) {
            ['msgSuccess', 'msgError', 'msgDeclined'].forEach(function (key) { show(byId(key), key === id); });
            if (text) { byId('msgErrorText').textContent = text; }
            show(byId('esToast'), true);
            clearTimeout(toastTimer);
            if (id === 'msgError') {
                toastTimer = setTimeout(function () { show(byId('esToast'), false); }, 5000);
            }
        }
        function showError(text) { toast('msgError', text); }

        // ------------------------------------------------------------------
        // Dialogs
        // ------------------------------------------------------------------
        var openDialog = null;
        function open(dialog) {
            if (!dialog) { return; }
            closeMenu();
            show(dialog, true);
            openDialog = dialog;
            var focusable = dialog.querySelector('input:not(.es-hidden), textarea, .es-btn-primary, .es-btn-danger');
            if (focusable) { focusable.focus(); }
        }
        function close(dialog) {
            if (!dialog || dialog.classList.contains('es-hidden')) { return; }
            show(dialog, false);
            if (dialog.onClose) { dialog.onClose(); }
            if (openDialog === dialog) { openDialog = null; }
        }
        document.querySelectorAll('.es-dialog').forEach(function (dialog) {
            dialog.addEventListener('click', function (ev) {
                if (ev.target === dialog || ev.target.closest('[data-close]')) { close(dialog); }
            });
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') { close(openDialog); closeMenu(); }
        });

        // ------------------------------------------------------------------
        // Options menu
        // ------------------------------------------------------------------
        var menu = byId('esMenu');
        var btnOptions = byId('esBtnOptions');
        function closeMenu() { show(menu, false); btnOptions.setAttribute('aria-expanded', 'false'); }
        btnOptions.addEventListener('click', function (ev) {
            ev.stopPropagation();
            var opening = menu.classList.contains('es-hidden');
            show(menu, opening);
            btnOptions.setAttribute('aria-expanded', opening ? 'true' : 'false');
        });
        document.addEventListener('click', function (ev) {
            if (!menu.contains(ev.target)) { closeMenu(); }
        });

        // ------------------------------------------------------------------
        // Signature and initials: a pad per dialog, applied on "Adopt"
        // ------------------------------------------------------------------
        var pads = {};
        var adopted = { signature: '', initials: '' };
        var fields;

        function applyImages() {
            if (fields) { fields.setImages(adopted.signature, adopted.initials); }
        }
        document.querySelectorAll('[data-pad]').forEach(function (node) {
            var kind = node.getAttribute('data-pad');
            var dialog = node.closest('.es-dialog');
            var pad = new window.EasySign.Pad(node);
            pads[kind] = pad;
            dialog.querySelector('[data-adopt]').addEventListener('click', function () {
                if (!pad.filled) { pad.root.querySelector('.es-canvas-wrap').classList.add('es-flash'); return; }
                var then = dialog.then;
                adopted[kind] = pad.dataURL();
                dialog.adopting = true;
                close(dialog);
                dialog.adopting = false;
                applyImages();
                if (then) { then(); }
            });
            dialog.onClose = function () {
                // Cancelled: go back to what was adopted before.
                if (!dialog.adopting && pad.dataURL() !== adopted[kind]) {
                    if (adopted[kind]) { pad.load(adopted[kind]); } else { pad.setMode('type', true); }
                }
                dialog.then = null;
                pad.root.querySelector('.es-canvas-wrap').classList.remove('es-flash');
            };
        });
        function openPad(kind, then) {
            var dialog = byId('esDlg_' + kind) || byId('esDlg_signature');
            if (!dialog) { return; }
            dialog.then = then || null;
            open(dialog);
        }

        // ------------------------------------------------------------------
        // Document, progress and ribbon
        // ------------------------------------------------------------------
        function ribbonLabel(field) {
            if (!started) { return t('start'); }
            return field.type === 'signature' || field.type === 'initials' ? t('sign') : t('fill');
        }
        function placeRibbon() {
            var next = fields && fields.missing()[0];
            var node = next && fields.nodes[next.id];
            show(ribbon, !!node);
            btnSign.classList.toggle('es-ready', !next);
            if (!node) { return; }
            ribbon.firstElementChild.textContent = ribbonLabel(next);
            var box = node.getBoundingClientRect();
            var area = pagesNode.getBoundingClientRect();
            // Arrow only when the label would cover the field.
            ribbon.classList.remove('es-ribbon-compact');
            var room = document.documentElement.dir === 'rtl' ? area.right - box.right : box.left - area.left;
            ribbon.classList.toggle('es-ribbon-compact', room < ribbon.offsetWidth + 4);
            ribbon.style.top = (box.top - area.top + pagesNode.offsetTop + box.height / 2 - ribbon.offsetHeight / 2) + 'px';
        }
        function updateProgress() {
            if (!fields) { return; }
            var missing = fields.missing().length;
            progressText.textContent = missing === 0 ? (fields.fields.length ? t('ready') : '')
                : missing === 1 ? t('left1') : t('leftN').replace('%s', missing);
            progressText.classList.toggle('es-progress-done', missing === 0);
            placeRibbon();
        }
        function goNext() {
            started = true;
            var next = fields.missing()[0];
            if (!next) { placeRibbon(); return; }
            var isImage = next.type === 'signature' || next.type === 'initials';
            fields.focusNextMissing(isImage);
            placeRibbon();
            return next;
        }

        fields = new window.EasySign.Fields(pagesNode, {
            onChange: updateProgress,
            onImage: function (field) {
                started = true;
                openPad(field.type, function () { if (fields.missing().length) { goNext(); } });
            },
        });
        fields.render().then(syncPageCount).catch(function () {
            pagesNode.textContent = t('noDocument');
        });

        ribbon.addEventListener('click', function () {
            var wasStarted = started;
            var next = goNext();
            if (wasStarted && next && (next.type === 'signature' || next.type === 'initials')) {
                fields.hooks.onImage(next);
            }
        });

        // ------------------------------------------------------------------
        // Pages and zoom
        // ------------------------------------------------------------------
        var pageInput = byId('esPageInput');
        var zoomSelect = byId('esZoom');
        function syncPageCount() {
            byId('esPageCount').textContent = fields.pages.length;
            syncCurrentPage();
        }
        function currentPage() {
            var middle = viewer.getBoundingClientRect().top + viewer.clientHeight / 3;
            var index = 0;
            fields.pages.forEach(function (entry, i) {
                if (entry.wrap.getBoundingClientRect().top <= middle) { index = i; }
            });
            return index;
        }
        function syncCurrentPage() {
            if (document.activeElement !== pageInput) { pageInput.value = currentPage() + 1; }
        }
        function goToPage(index) {
            var entry = fields.pages[Math.max(0, Math.min(fields.pages.length - 1, index))];
            if (entry) { entry.wrap.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
        }
        viewer.addEventListener('scroll', syncCurrentPage, { passive: true });
        byId('esPrevPage').addEventListener('click', function () { goToPage(currentPage() - 1); });
        byId('esNextPage').addEventListener('click', function () { goToPage(currentPage() + 1); });
        pageInput.addEventListener('change', function () { goToPage(parseInt(pageInput.value, 10) - 1); pageInput.blur(); });
        pageInput.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { pageInput.blur(); } });

        function setZoom(value) {
            var anchor = currentPage();
            var custom = zoomSelect.querySelector('option[data-custom]');
            if (value !== 'auto' && !zoomSelect.querySelector('option[value="' + value + '"]')) {
                if (!custom) {
                    custom = document.createElement('option');
                    custom.setAttribute('data-custom', '1');
                    zoomSelect.appendChild(custom);
                }
                custom.value = value;
                custom.textContent = Math.round(value * 100) + '%';
            }
            zoomSelect.value = String(value);
            fields.setZoom(value).then(placeRibbon);
            placeRibbon();
            goToPage(anchor);
        }
        function step(direction) {
            var scale = fields.scale();
            var list = direction > 0 ? ZOOMS.filter(function (z) { return z > scale + 0.01; })
                : ZOOMS.filter(function (z) { return z < scale - 0.01; }).reverse();
            if (list.length) { setZoom(list[0]); }
        }
        zoomSelect.addEventListener('change', function () {
            setZoom(zoomSelect.value === 'auto' ? 'auto' : Number(zoomSelect.value));
        });
        byId('esZoomIn').addEventListener('click', function () { step(1); });
        byId('esZoomOut').addEventListener('click', function () { step(-1); });

        var resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                if (fields.zoom === 'auto') { fields.layout().then(placeRibbon); }
                placeRibbon();
            }, 150);
        });

        // ------------------------------------------------------------------
        // Sign
        // ------------------------------------------------------------------
        function setLoading(loading) {
            btnSign.disabled = loading;
            if (byId('btnOtpConfirm')) { byId('btnOtpConfirm').disabled = loading; }
            show(byId('btnSignText'), !loading);
            show(byId('btnSignSpinner'), loading);
        }

        function requestOtp() {
            return post('/sign/otp/' + token, { csrf_token: csrf }).then(function (result) {
                if (!result.success) { showError(result.error); return; }
                otpRequested = true;
                otpInput.focus();
            });
        }

        function submit() {
            if (btnSign.disabled) { return; }  // already sending, or done
            var otp = needsOtp ? (otpInput.value || '').trim() : '';
            if (needsOtp && !/^\d{6}$/.test(otp)) {
                showError(t('code'));
                otpInput.focus();
                return;
            }
            setLoading(true);
            post('/sign/submit/' + token, {
                csrf_token: csrf,
                signature: adopted.signature,
                signature_method: pads.signature ? pads.signature.mode : 'draw',
                initials: adopted.initials,
                values: JSON.stringify(fields.values()),
                otp: otp,
            }).then(function (result) {
                setLoading(false);
                if (!result.success) { showError(result.error || t('unexpected')); return; }
                close(byId('esDlgOtp'));
                toast('msgSuccess');
                btnSign.disabled = true;
                show(ribbon, false);
                setTimeout(function () { window.location.href = '/sign/view/' + token; }, 1200);
            }).catch(function () {
                setLoading(false);
                showError(t('network'));
            });
        }

        btnSign.addEventListener('click', function () {
            show(byId('esToast'), false);
            var next = fields.missing()[0];
            if (next) {
                showError(t('complete'));
                goNext();
                if (next.type === 'signature' || next.type === 'initials') { fields.hooks.onImage(next); }
                return;
            }
            if (needsSignature && !adopted.signature) {
                started = true;
                openPad('signature', function () { btnSign.click(); });
                return;
            }
            if (needsOtp) {
                open(byId('esDlgOtp'));
                if (!otpRequested) { requestOtp(); }
                return;
            }
            submit();
        });

        if (needsOtp) {
            byId('btnOtpResend').addEventListener('click', requestOtp);
            byId('btnOtpConfirm').addEventListener('click', submit);
            otpInput.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { submit(); } });
        }

        // ------------------------------------------------------------------
        // Decline
        // ------------------------------------------------------------------
        var declineDialog = byId('esDlgDecline');
        byId('btnShowDecline').addEventListener('click', function () { open(declineDialog); });
        byId('btnConfirmDecline').addEventListener('click', function () {
            var button = byId('btnConfirmDecline');
            button.disabled = true;
            post('/sign/decline/' + token, {
                csrf_token: button.getAttribute('data-csrf'),
                reason: (byId('declineReason').value || '').trim(),
            }).then(function (result) {
                button.disabled = false;
                if (!result.success) { showError(result.error || t('declineFailed')); return; }
                close(declineDialog);
                toast('msgDeclined');
                btnSign.disabled = true;
                show(ribbon, false);
                setTimeout(function () { window.location.href = '/sign/view/' + token; }, 1200);
            }).catch(function () {
                button.disabled = false;
                showError(t('network'));
            });
        });

        // Language switch changes the texts set from here.
        byId('esBtnLang').addEventListener('click', function () { setTimeout(updateProgress, 0); });
    });
})();
