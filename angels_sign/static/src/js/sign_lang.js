/** @odoo-module ignore */
/**
 * Angels Sign — English/Spanish switch for the public signing pages.
 * Texts live in data-en / data-es attributes of every .es-i18n element.
 * Without a saved choice the page follows the browser language. Scripts that
 * build texts themselves read window.AngelsSign.lang() and listen to "es-lang".
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'es_lang';
    var LANGS = ['en', 'es'];
    var LABELS = { en: 'English', es: 'Español' };

    function readLang() {
        var saved;
        try {
            saved = window.localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            saved = null;
        }
        if (LANGS.indexOf(saved) !== -1) { return saved; }
        return /^es\b/i.test(navigator.language || '') ? 'es' : 'en';
    }

    var current = 'en';

    function applyLang(lang, save) {
        current = lang;
        document.documentElement.setAttribute('lang', lang);
        document.querySelectorAll('#esLangLabel').forEach(function (label) {
            label.textContent = LABELS[lang === 'en' ? 'es' : 'en'];
        });
        document.querySelectorAll('.es-i18n').forEach(function (el) {
            var txt = el.getAttribute('data-' + lang);
            if (txt) { el.textContent = txt; }
        });
        if (save) {
            try {
                window.localStorage.setItem(STORAGE_KEY, lang);
            } catch (e) {
                /* storage unavailable: keep the choice for this page only */
            }
        }
        document.dispatchEvent(new CustomEvent('es-lang', { detail: lang }));
    }

    window.AngelsSign = window.AngelsSign || {};
    window.AngelsSign.lang = function () { return current; };

    document.addEventListener('DOMContentLoaded', function () {
        applyLang(readLang(), false);
        document.querySelectorAll('.es-lang-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                applyLang(current === 'en' ? 'es' : 'en', true);
            });
        });
    });
})();
