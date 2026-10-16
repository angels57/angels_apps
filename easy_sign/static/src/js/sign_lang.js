/** @odoo-module ignore */
/**
 * Easy Sign — English/Arabic switch for the public signing pages.
 * Texts live in data-en / data-ar attributes of every .es-i18n element.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'es_lang';

    function readLang() {
        try {
            return window.localStorage.getItem(STORAGE_KEY) || 'en';
        } catch (e) {
            return 'en';
        }
    }

    function applyLang(lang) {
        var root = document.documentElement;
        root.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
        root.setAttribute('lang', lang);
        var label = document.getElementById('esLangLabel');
        if (label) {
            label.textContent = lang === 'ar' ? 'English' : '\u0639\u0631\u0628\u064a';
        }
        document.querySelectorAll('.es-i18n').forEach(function (el) {
            var txt = el.getAttribute('data-' + lang);
            if (txt) { el.textContent = txt; }
        });
        try {
            window.localStorage.setItem(STORAGE_KEY, lang);
        } catch (e) {
            /* storage unavailable: keep the choice for this page only */
        }
        return lang;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var current = applyLang(readLang());
        document.querySelectorAll('.es-lang-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                current = applyLang(current === 'en' ? 'ar' : 'en');
            });
        });
    });
})();
