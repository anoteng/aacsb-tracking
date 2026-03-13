/**
 * i18n.js — lightweight translation engine
 *
 * English is the base language. The English key IS the English string,
 * so no en.json is needed at runtime — missing translations fall back
 * to displaying the key as-is.
 *
 * Usage:
 *   await i18n.init();
 *
 *   t('Save changes')               → 'Lagre endringer' (or 'Save changes')
 *   t('{{n}} courses', { n: 3 })    → '3 emner'
 *
 * Adding a new language:
 *   1. Add frontend/i18n/<code>.json with any subset of keys
 *   2. Add an <option value="<code>"> to the lang switcher in nav
 */

const i18n = (() => {
    let translations = {};
    let currentLang = 'en';

    const SUPPORTED = ['en', 'no'];

    function detectLang() {
        const saved = localStorage.getItem('aacsb_lang');
        if (saved && SUPPORTED.includes(saved)) return saved;
        const browser = (navigator.language || 'en').split('-')[0].toLowerCase();
        return SUPPORTED.includes(browser) ? browser : 'en';
    }

    async function init() {
        currentLang = detectLang();

        if (currentLang !== 'en') {
            try {
                const res = await fetch(`/aacsb/static/i18n/${currentLang}.json`);
                if (res.ok) {
                    translations = await res.json();
                }
            } catch (_) {
                // Network error — fall back to English silently
            }
        }

        _applyDataAttrs();
        _updateLangSwitcher();
    }

    function t(key, vars = {}) {
        let str = Object.prototype.hasOwnProperty.call(translations, key)
            ? translations[key]
            : key;
        for (const [k, v] of Object.entries(vars)) {
            str = str.split(`{{${k}}}`).join(String(v));
        }
        return str;
    }

    function setLang(lang) {
        if (!SUPPORTED.includes(lang)) return;
        localStorage.setItem('aacsb_lang', lang);
        location.reload();
    }

    function getLang() {
        return currentLang;
    }

    /** Translate elements marked with data-i18n="key" in the DOM. */
    function _applyDataAttrs() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            el.textContent = t(el.dataset.i18n);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            el.placeholder = t(el.dataset.i18nPlaceholder);
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            el.title = t(el.dataset.i18nTitle);
        });
    }

    function _updateLangSwitcher() {
        const sel = document.getElementById('lang-switcher');
        if (sel) sel.value = currentLang;
    }

    return { init, t, setLang, getLang };
})();
