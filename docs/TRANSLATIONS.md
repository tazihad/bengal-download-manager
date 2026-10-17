# Bengal Download Manager — Localization & Weblate Guide

Bengal Download Manager is localized using standard Qt Linguist XML (`.ts`) translation files and compiled `.qm` binary catalogs. Anyone can contribute translations through the **Weblate web portal** without writing code or installing development tools.

---

## 🌐 1. Contributing via Weblate (Recommended)

Bengal Download Manager uses **Weblate** for crowdsourced, community-driven localization:

* **File Format**: Standard Qt Linguist XML (`ts`).
* **Source Strings**: [`translations/bdm_en.ts`](../translations/bdm_en.ts) (Generated from Python & PyQt6 source code).
* **Target Translations**: [`translations/bdm_<lang>.ts`](../translations/).
* **Weblate Configuration**: [`.weblate.json`](../.weblate.json) & [`.weblate.yaml`](../.weblate.yaml) in the repository root.

### How Weblate Works with GitHub:
1. Translators edit strings in the Weblate web interface.
2. Weblate automatically runs quality checks (accelerator `&` preservation, Qt placeholders `%1`, HTML tag validity).
3. Weblate commits and pushes updated `translations/bdm_<lang>.ts` files to GitHub.
4. The [Translations GitHub Action](https://github.com/tazihad/bengal-download-manager/actions/workflows/translations.yml) automatically compiles them to `assets/translations/bdm_<lang>.qm`.

---

## 🛠️ 2. Adding or Updating Translations via CLI

The project includes [`scripts/i18n.py`](../scripts/i18n.py) for managing the complete localization lifecycle.

### Extracting New UI Strings
Whenever UI code, dialogs, buttons, or tooltips are added or modified:
```bash
uv run python scripts/i18n.py extract
```
* Runs `pylupdate` across `src/ui/` and `src/core/`.
* Synchronizes strings into `translations/bdm_en.ts`.

### Compiling Translations
To compile all `.ts` files into binary `.qm` catalogs for runtime:
```bash
uv run python scripts/i18n.py compile
```

### Checking Translation Status
To view completion percentage across all languages:
```bash
uv run python scripts/i18n.py status
```

---

## 🤖 3. Pre-Populating Translations with Gemini AI

To bootstrap a new language or fill untranslated gaps:
```bash
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang <lang_code> --model gemini-flash-lite-latest
```

Example for Spanish, French, and Japanese:
```bash
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang es,fr,ja
```

---

## 🎨 4. Setting Up Weblate on a New Instance

To connect this repository to a Weblate instance:

1. **Add Project**: Set Project Name to `Bengal Download Manager` and Project Website to `https://github.com/tazihad/bengal-download-manager`.
2. **Add Component**:
   * **Configuration style**: Repository configuration (`.weblate.yaml` or `.weblate.json` is auto-detected).
   * **Source code repository**: `https://github.com/tazihad/bengal-download-manager.git`
   * **Repository branch**: `main`
   * **File mask**: `translations/bdm_*.ts`
   * **Template for new translations**: `translations/bdm_en.ts`
   * **File format**: `Qt Linguist translation file`
3. **Weblate Push Access**: Add Weblate's SSH public key as a deploy key with write access (or use GitHub App / Personal Access Token) on GitHub.
4. **Webhook**: Add a GitHub Webhook pointing to `https://weblate.example.com/hooks/github/` with `push` events to trigger instantaneous translation updates.
