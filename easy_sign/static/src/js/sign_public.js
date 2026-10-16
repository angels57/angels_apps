/** @odoo-module ignore */
/**
 * Easy Sign — public signing page: wires the pads, the document fields, the
 * optional one-time code and the sign / decline requests.
 */
(function () {
    'use strict';

    function byId(id) { return document.getElementById(id); }
    function show(node, visible) { if (node) { node.classList.toggle('es-hidden', !visible); } }

    function post(url, data) {
        var form = new FormData();
        Object.keys(data).forEach(function (key) { form.append(key, data[key]); });
        return fetch(url, { method: 'POST', body: form, credentials: 'same-origin' }).then(function (response) {
            return response.json().then(function (json) { return json; }, function () {
                return { success: false, error: 'Your session has expired. Please reload the page and try again.' };
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
        var otpBox = byId('esOtp');
        var otpInput = byId('esOtpInput');
        var msgError = byId('msgError');
        var progress = byId('esProgress');
        var progressText = byId('esProgressText');
        var otpRequested = false;

        function showError(text) {
            show(byId('msgSuccess'), false);
            byId('msgErrorText').textContent = text;
            show(msgError, true);
            msgError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        var pads = {};
        var fields;
        function refresh() {
            if (!fields) { return; }
            fields.setImages(pads.signature ? pads.signature.dataURL() : '', pads.initials ? pads.initials.dataURL() : '');
        }
        function updateProgress() {
            if (!fields || !fields.fields.length) { return; }
            var missing = fields.missing().length;
            show(progress, missing > 0);
            progressText.textContent = missing + (missing === 1 ? ' required field left' : ' required fields left');
        }
        document.querySelectorAll('[data-pad]').forEach(function (node) {
            pads[node.getAttribute('data-pad')] = new window.EasySign.Pad(node, refresh);
        });
        fields = new window.EasySign.Fields(pagesNode, updateProgress);
        fields.render().catch(function () {
            pagesNode.textContent = 'The document could not be displayed. Reload the page to try again.';
        });
        byId('btnNextField').addEventListener('click', function () { fields.focusNextMissing(); });

        function setLoading(loading) {
            btnSign.disabled = loading;
            show(byId('btnSignText'), !loading);
            show(byId('btnSignSpinner'), loading);
        }

        function requestOtp() {
            return post('/sign/otp/' + token, { csrf_token: csrf }).then(function (result) {
                if (!result.success) { showError(result.error); return; }
                otpRequested = true;
                show(otpBox, true);
                otpInput.focus();
            });
        }

        btnSign.addEventListener('click', function () {
            show(msgError, false);
            if (pads.signature && !pads.signature.filled) {
                showError('Please add your signature.');
                return;
            }
            if (fields.focusNextMissing()) {
                showError('Please complete the highlighted required fields.');
                return;
            }
            if (needsOtp && !otpRequested) { requestOtp(); return; }
            if (needsOtp && !/^\d{6}$/.test((otpInput.value || '').trim())) {
                showError('Enter the 6-digit code we sent you.');
                otpInput.focus();
                return;
            }
            setLoading(true);
            post('/sign/submit/' + token, {
                csrf_token: csrf,
                signature: pads.signature ? pads.signature.dataURL() : '',
                signature_method: pads.signature ? pads.signature.mode : 'draw',
                initials: pads.initials ? pads.initials.dataURL() : '',
                values: JSON.stringify(fields.values()),
                otp: needsOtp ? otpInput.value.trim() : '',
            }).then(function (result) {
                setLoading(false);
                if (!result.success) { showError(result.error || 'An unexpected error occurred.'); return; }
                show(byId('msgSuccess'), true);
                btnSign.style.display = 'none';
                show(byId('btnShowDecline'), false);
                setTimeout(function () { window.location.href = '/sign/view/' + token; }, 1200);
            }).catch(function () {
                setLoading(false);
                showError('Network error. Please check your connection and try again.');
            });
        });

        byId('btnOtpResend').addEventListener('click', requestOtp);

        var declineForm = byId('declineForm');
        byId('btnShowDecline').addEventListener('click', function () {
            show(declineForm, true);
            show(byId('btnShowDecline'), false);
        });
        byId('btnCancelDecline').addEventListener('click', function () {
            show(declineForm, false);
            show(byId('btnShowDecline'), true);
        });
        byId('btnConfirmDecline').addEventListener('click', function () {
            var button = byId('btnConfirmDecline');
            button.disabled = true;
            post('/sign/decline/' + token, {
                csrf_token: button.getAttribute('data-csrf'),
                reason: (byId('declineReason').value || '').trim(),
            }).then(function (result) {
                button.disabled = false;
                if (!result.success) { showError(result.error || 'Failed to decline. Please try again.'); return; }
                show(declineForm, false);
                show(byId('msgDeclined'), true);
                btnSign.style.display = 'none';
                setTimeout(function () { window.location.href = '/sign/view/' + token; }, 1200);
            }).catch(function () {
                button.disabled = false;
                showError('Network error. Please check your connection and try again.');
            });
        });
    });
})();
