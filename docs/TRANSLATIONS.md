# Bengal Download Manager — Localization Guide

Bengal Download Manager is localized using standard Qt Linguist XML (`.ts`) translation files and compiled `.qm` binary catalogs. Translations across all supported languages are powered by **Google Gemini AI** and managed directly through the project CLI tooling.

This includes both **in-app UI strings** and **AppStream catalog metadata** (application name, summary, description, screenshot captions) that appear in software centers such as Flathub, GNOME Software, and KDE Discover.

---

## 🌐 1. Architecture & Translation Files

* **Source Strings**: [`translations/bdm_en.ts`](../translations/bdm_en.ts) (Extracted from Python & PyQt6 source code).
* **AppStream Metadata Template**: [`flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml.in`](../flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml.in) (English strings with translator comments).
* **Target Translations**: [`translations/bdm_<lang>.ts`](../translations/) (Language-specific XML catalogs, now including a `Metainfo` context).
* **Compiled Catalogs**: [`assets/translations/bdm_<lang>.qm`](../assets/translations/) (High-performance binary catalogs loaded by `QTranslator` at runtime).
* **Generated AppStream File**: [`flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml`](../flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml) (Emits `<name xml:lang="...">`, `<description xml:lang="...">` etc. from the catalogs).
* **Supported Languages**: Defined in [`src/core/services/language_service.py`](../src/core/services/language_service.py).

---

## 🛠️ 2. Translation Workflow via CLI

The project includes [`scripts/i18n.py`](../scripts/i18n.py) for managing the complete localization lifecycle, including AppStream catalog metadata.

### Step 0: Sync AppStream Metadata Strings into Catalogs
After modifying the `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml.in` template, sync its translatable strings into every `translations/bdm_*.ts` so translators see them:
```bash
uv run python scripts/i18n.py metainfo --sync-catalogs
```
* Adds/updates the `Metainfo` context in each catalog with hints for translators.
* Regenerates `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml` from the template + catalogs.

### Step 1: Extract New UI Strings
Whenever UI code, dialogs, buttons, menus, or tooltips are added or modified:
```bash
uv run python scripts/i18n.py extract
```
* Runs `pylupdate` across `src/ui/` and `src/core/`.
* Synchronizes new and modified strings into `translations/bdm_en.ts`.

### Step 2: Translate Strings with Gemini AI
Translate untranslated strings into target language(s) using Google Gemini:
```bash
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang <lang_code>
```

Examples:
```bash
# Translate a single language (e.g., Bengali)
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang bn

# Translate multiple specific languages
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang es,fr,ja,ar

# Translate all supported languages
GEMINI_API_KEY="YOUR_API_KEY" uv run python scripts/i18n.py translate --lang all
```

Options:
* `--model <model_name>`: Gemini model to use (default: `gemini-flash-lite-latest`).
* `--batch-size <n>`: Number of strings per batch request (default: `60`).

### Step 3: Compile Translation Catalogs
Compile all `.ts` files into binary `.qm` catalogs for runtime **and** regenerate the localized AppStream metadata:
```bash
uv run python scripts/i18n.py compile
```

### Step 3b: Regenerate AppStream Metadata Only
When translation catalogs are already up to date and only the AppStream XML needs refreshing:
```bash
uv run python scripts/i18n.py metainfo
```

### Step 4: Check Translation Status
View completion percentage across all languages:
```bash
uv run python scripts/i18n.py status
```

---

## 🤖 3. AI Translation Pipeline Rules

The translation pipeline in `scripts/i18n.py` enforces strict localization rules:
1. **Accelerators (`&`)**:
   - **Latin scripts**: Keyboard accelerators (e.g., `&File`, `&Tasks`) are preserved.
   - **CJK scripts**: Standard format is used, appending the shortcut (e.g., `文件(&F)`).
   - **Indic & RTL scripts**: Accidental accelerators before non-ASCII characters are stripped to prevent breaking Unicode combining vowel marks (কার/মাত্রা) and Arabic cursive shaping.
2. **Placeholders**: All format placeholders (`%1`, `%2`, `%s`, `%n`, `{0}`) are strictly preserved.
3. **HTML Tags**: Formatting tags (`<b>`, `<i>`, `<a>`) remain intact.
4. **Domain Terminology**: Consistent networking and download manager terms (`Pause`, `Resume`, `Chunk`, `Aria2`, `Hash`) are prioritized.

---

## 🚀 4. CI/CD Validation & Compilation

The [Translations GitHub Action](https://github.com/tazihad/bengal-download-manager/actions/workflows/translations.yml) runs on every push and pull request modifying `translations/**`, `scripts/i18n.py`, or `flatpak/*.metainfo.xml.in`:
1. Compiles all `.ts` files to `.qm` binary catalogs.
2. Regenerates the localized `flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml` from the template and catalogs.
3. Validates translation status and integrity.
4. Automatically commits compiled `.qm` files **and** the generated AppStream metadata back to `main` if changes occurred.

To validate locally that the generated AppStream XML is in sync (exits non-zero if out of date):
```bash
uv run python scripts/i18n.py metainfo --check
```
