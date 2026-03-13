# i18n / Translation Plan

## Goals
- English is the base language and canonical source of truth
- Norwegian (`no`) is the first additional language
- Any language can be added in the future with no code changes
- Missing translations fall back silently to English
- No build step, no framework dependency — pure vanilla JS

---

## File structure

```
frontend/
  i18n/
    en.json        ← reference catalogue (all keys; not loaded at runtime)
    no.json        ← Norwegian delta (only keys that differ from English)
  js/
    i18n.js        ← translation engine (loaded on every page)
```

---

## Translation engine — `frontend/js/i18n.js`

Small self-contained module (~80 lines). API:

| Function | Purpose |
|---|---|
| `await i18n.init()` | Detect language, load translation file, apply data-attrs |
| `t('key')` | Translate a string; returns key as-is if no translation |
| `t('key', { n: 3 })` | Interpolation using `{{n}}` placeholders |
| `i18n.setLang('no')` | Persist language choice and reload page |
| `i18n.getLang()` | Returns current language code |

Language detection order:
1. `localStorage.getItem('aacsb_lang')`
2. `navigator.language` (browser preference)
3. Default: `'en'`

Only non-English language files are loaded at runtime. English requires no network request.

---

## Two categories of translatable text

### Category A — Static HTML elements
Rare. Elements whose text never changes dynamically.
Use `data-i18n` attributes, applied by `applyDataAttrs()` on init:

```html
<button data-i18n="Save changes">Save changes</button>
<input data-i18n-placeholder="Search by name…" placeholder="Search by name…">
```

### Category B — JS template literals (majority of text)
Most UI text is generated inside JavaScript template literals.
Wrap with `t()`:

```javascript
// Before
html += `<button>Save changes</button>`;

// After
html += `<button>${t('Save changes')}</button>`;
```

Since `t()` returns the key unchanged when no translation exists, pages are
correct English before any translations are written.

---

## Translation file format

`en.json` — complete reference, documents all keys:
```json
{
  "Save changes": "Save changes",
  "Delete": "Delete",
  "Cancel": "Cancel",
  "{{n}} courses": "{{n}} courses"
}
```

`no.json` — only keys that differ:
```json
{
  "Save changes": "Lagre endringer",
  "Delete": "Slett",
  "Cancel": "Avbryt",
  "{{n}} courses": "{{n}} emner"
}
```

---

## Language switcher

A `<select>` element added to the `<nav>` on every page:

```html
<select id="lang-switcher" onchange="i18n.setLang(this.value)">
    <option value="en">EN</option>
    <option value="no">NO</option>
</select>
```

`i18n.init()` sets the selected option automatically after loading.

---

## Adding a new language (future)

1. Create `frontend/i18n/<code>.json` with any subset of keys
2. Add `<option value="<code>">` to the lang switcher
3. Add `'<code>'` to the `SUPPORTED` array in `i18n.js`

No other changes required.

---

## Rollout order (page by page)

Each step is independent — pages not yet retrofitted continue to show
correct English.

| Step | Scope |
|---|---|
| **1 (done)** | `i18n.js` engine + `en.json` / `no.json` skeleton files |
| **2** | Login page (`index.html`) — first thing users see |
| **3** | Settings page (`settings.html`) |
| **4** | Courses page (`courses.html`) |
| **5** | AOL index + programme pages |
| **6** | Admin, qualifications, research pages (largest scope) |

---

## Backend / API errors (future)

API error messages in `detail:` fields occasionally surface to users.
Two options (defer until needed):

- **Client-side map**: A small `errorTranslations` object in `i18n.js`
  translating known error strings after the fact.
- **Accept-Language header**: Backend reads the header and returns
  localised `detail` messages. Cleaner but more work.

---

## What is NOT in scope

- Right-to-left layout support
- Complex pluralisation rules (Norwegian follows English closely enough)
- Database content (`name_no` / `name_eng` fields are already bilingual)
- Magic link email content (separate task if needed)
