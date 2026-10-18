#!/usr/bin/env python3
"""
Bengal Download Manager - Internationalization (i18n) & Localization Tool
========================================================================
CLI tool for extracting UI strings, compiling binary .qm catalogs,
and translating via Gemini AI.

Commands:
    extract         Extract translatable strings from code into translations/bdm_en.ts
    compile         Compile all translations/bdm_*.ts files into assets/translations/bdm_*.qm
    translate       Translate strings into target language(s) using Gemini AI
    status          Show translation progress statistics across all languages
"""

import os
import sys
import re
import json
import glob
import time
import struct
import argparse
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Any
from urllib import request, error

# Root repository paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "translations")
ASSETS_TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "assets", "translations")
TEMPLATE_TS = os.path.join(TRANSLATIONS_DIR, "bdm_en.ts")

# Supported UI languages list matching language_service.py
SUPPORTED_LANGUAGES = [
    ("en", "English", "en_US"),
    ("sq", "Albanian - Shqip", "sq_AL"),
    ("am", "Amharic - አማርኛ", "am_ET"),
    ("ar", "Arabic - العربية", "ar_SA"),
    ("hy", "Armenian - Հայերեն", "hy_AM"),
    ("az", "Azerbaijani - Azərbaycan dili", "az_AZ"),
    ("be", "Belarusian - Беларуская", "be_BY"),
    ("bn", "Bengali - বাংলা", "bn_BD"),
    ("bs", "Bosnian - Bosanski", "bs_BA"),
    ("bg", "Bulgarian - Български", "bg_BG"),
    ("my", "Burmese - မြန်မာ", "my_MM"),
    ("ca", "Catalan - Català", "ca_ES"),
    ("zh_CN", "Chinese (Simplified) - 简体中文", "zh_CN"),
    ("zh_TW", "Chinese (Traditional) - 繁體中文", "zh_TW"),
    ("hr", "Croatian - Hrvatski", "hr_HR"),
    ("cs", "Czech - Čeština", "cs_CZ"),
    ("da", "Danish - Dansk", "da_DK"),
    ("nl", "Dutch - Nederlands", "nl_NL"),
    ("nl_BE", "Dutch (Belgium) - Nederlands (België)", "nl_BE"),
    ("et", "Estonian - Eesti", "et_EE"),
    ("fa", "Farsi (Persian) - فارسی", "fa_IR"),
    ("fil", "Filipino - Filipino", "fil_PH"),
    ("fi", "Finnish - Suomi", "fi_FI"),
    ("fr", "French - Français", "fr_FR"),
    ("gl", "Galician - Galego", "gl_ES"),
    ("ka", "Georgian - ქართული", "ka_GE"),
    ("de", "German - Deutsch", "de_DE"),
    ("el", "Greek - Ελληνικά", "el_GR"),
    ("gu", "Gujarati - ગુજરાતી", "gu_IN"),
    ("ha", "Hausa - Hausa", "ha_NG"),
    ("he", "Hebrew - עברית", "he_IL"),
    ("hi", "Hindi - हिन्दी", "hi_IN"),
    ("hu", "Hungarian - Magyar", "hu_HU"),
    ("ig", "Igbo - Igbo", "ig_NG"),
    ("id", "Indonesian - Bahasa Indonesia", "id_ID"),
    ("ga", "Irish - Gaeilge", "ga_IE"),
    ("it", "Italian - Italiano", "it_IT"),
    ("ja", "Japanese - 日本語", "ja_JP"),
    ("jv", "Javanese - Basa Jawa", "jv_ID"),
    ("kn", "Kannada - ಕನ್ನಡ", "kn_IN"),
    ("km", "Khmer - ខ្មែរ", "km_KH"),
    ("ko", "Korean - 한국어", "ko_KR"),
    ("lo", "Lao - ລາວ", "lo_LA"),
    ("lv", "Latvian - Latviešu", "lv_LV"),
    ("lt", "Lithuanian - Lietuvių", "lt_LT"),
    ("mk", "Macedonian - Македонски", "mk_MK"),
    ("ml", "Malayalam - മലയാളം", "ml_IN"),
    ("ms", "Malay - Bahasa Melayu", "ms_MY"),
    ("mr", "Marathi - मराठी", "mr_IN"),
    ("mn", "Mongolian - Монгол", "mn_MN"),
    ("ne", "Nepali - नेपाली", "ne_NP"),
    ("nb", "Norwegian - Norsk Bokmål", "nb_NO"),
    ("ps", "Pashto - پښتو", "ps_AF"),
    ("pl", "Polish - Polski", "pl_PL"),
    ("pt", "Portuguese - Português", "pt_PT"),
    ("pt_BR", "Portuguese (Brazilian) - Português (Brasil)", "pt_BR"),
    ("pa", "Punjabi - ਪੰਜਾਬੀ", "pa_IN"),
    ("ro", "Romanian - Română", "ro_RO"),
    ("ru", "Russian - Русский", "ru_RU"),
    ("sr_Cyrl", "Serbian (Cyrillic) - Српски", "sr_RS"),
    ("sr_Latn", "Serbian (Latin) - Srpski", "sr_RS"),
    ("si", "Sinhala - සිංහල", "si_LK"),
    ("sk", "Slovak - Slovenčina", "sk_SK"),
    ("sl", "Slovenian - Slovenščina", "sl_SI"),
    ("es", "Spanish - Español", "es_ES"),
    ("sw", "Swahili - Kiswahili", "sw_KE"),
    ("sv", "Swedish - Svenska", "sv_SE"),
    ("ta", "Tamil - தமிழ்", "ta_IN"),
    ("te", "Telugu - తెలుగు", "te_IN"),
    ("th", "Thai - ไทย", "th_TH"),
    ("tr", "Turkish - Türkçe", "tr_TR"),
    ("uk", "Ukrainian - Українська", "uk_UA"),
    ("ur", "Urdu - اردو", "ur_PK"),
    ("ug", "Uyghur - ئۇيغۇرچە", "ug_CN"),
    ("uz", "Uzbek - Oʻzbek", "uz_UZ"),
    ("vi", "Vietnamese - Tiếng Việt", "vi_VN"),
    ("cy", "Welsh - Cymraeg", "cy_GB"),
    ("yo", "Yoruba - Yorùbá", "yo_NG"),
]


# ==============================================================================
# 1. Native Qt QM Compiler (Zero External Dependencies)
# ==============================================================================

def elf_hash(source_text: str, comment: str = "") -> int:
    """Calculate the ELF hash used by Qt's QTranslator lookup table."""
    h = 0
    for s in (source_text, comment):
        for b in s.encode("utf-8"):
            h = (h << 4) + b
            g = h & 0xF0000000
            if g:
                h ^= (g >> 24)
            h &= ~g
    if not h:
        h = 1
    return h & 0xFFFFFFFF


def compile_ts_data_to_qm(messages: List[Tuple[str, str, str, str]]) -> bytes:
    """
    Compile translation messages into valid Qt .qm binary bytes.
    messages: list of (context, source_text, translation, comment)
    """
    MAGIC = bytes([0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95,
                   0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD])

    msg_block = bytearray()
    offsets: List[Tuple[int, int]] = []  # (hash, offset)

    for ctx, src, trans, cmt in messages:
        if not trans:
            continue
        h = elf_hash(src, cmt)
        offset = len(msg_block)
        offsets.append((h, offset))

        # Tag_SourceText = 0x06 (UTF-8)
        src_bytes = src.encode("utf-8")
        msg_block.append(0x06)
        msg_block.extend(struct.pack(">I", len(src_bytes)))
        msg_block.extend(src_bytes)

        # Tag_Context = 0x07 (UTF-8)
        ctx_bytes = ctx.encode("utf-8")
        msg_block.append(0x07)
        msg_block.extend(struct.pack(">I", len(ctx_bytes)))
        msg_block.extend(ctx_bytes)

        # Tag_Comment = 0x08 (UTF-8)
        if cmt:
            cmt_bytes = cmt.encode("utf-8")
            msg_block.append(0x08)
            msg_block.extend(struct.pack(">I", len(cmt_bytes)))
            msg_block.extend(cmt_bytes)

        # Tag_Translation = 0x03 (UTF-16BE)
        trans_bytes = trans.encode("utf-16-be")
        msg_block.append(0x03)
        msg_block.extend(struct.pack(">I", len(trans_bytes)))
        msg_block.extend(trans_bytes)

        # Tag_End = 0x01
        msg_block.append(0x01)

    # Sort offsets ascending by hash for binary search lookup
    offsets.sort(key=lambda x: x[0])

    # Hashes block (tag 0x42)
    hash_block = bytearray()
    for h, off in offsets:
        hash_block.extend(struct.pack(">II", h, off))

    out = bytearray(MAGIC)
    # Section: Hashes (0x42)
    out.append(0x42)
    out.extend(struct.pack(">I", len(hash_block)))
    out.extend(hash_block)

    # Section: Messages (0x69)
    out.append(0x69)
    out.extend(struct.pack(">I", len(msg_block)))
    out.extend(msg_block)

    return bytes(out)


def compile_ts_file(ts_path: str, qm_path: str) -> int:
    """Parse a .ts XML file and compile it into a binary .qm file."""
    tree = ET.parse(ts_path)
    root = tree.getroot()

    messages: List[Tuple[str, str, str, str]] = []
    for context in root.findall("context"):
        ctx_name = context.findtext("name") or "BDM"
        for msg in context.findall("message"):
            src = msg.findtext("source")
            if not src:
                continue
            cmt = msg.findtext("comment") or msg.findtext("extracomment") or ""
            trans_elem = msg.find("translation")
            trans_text = ""
            if trans_elem is not None and trans_elem.text:
                trans_text = trans_elem.text
            elif trans_elem is not None:
                # Plural form checks
                num_forms = [nf.text for nf in trans_elem.findall("numerusform") if nf.text]
                if num_forms:
                    trans_text = num_forms[0]

            if trans_text:
                # Strip broken keyboard accelerators ('&') from non-Latin scripts (e.g. Indic, Arabic)
                # where '&' placed before a non-ASCII letter breaks HarfBuzz ligature shaping
                # and orphans combining vowel signs onto dotted circles (◌).
                trans_text = re.sub(r'&(?=[^\x00-\x7f\s])', '', trans_text)
                messages.append((ctx_name, src, trans_text, cmt))

    qm_bytes = compile_ts_data_to_qm(messages)
    os.makedirs(os.path.dirname(os.path.abspath(qm_path)), exist_ok=True)
    with open(qm_path, "wb") as f:
        f.write(qm_bytes)
    return len(messages)


# ==============================================================================
# 2. String Extraction Pipeline
# ==============================================================================

def extract_strings() -> str:
    """Extract translatable strings from the codebase and create translations/bdm_en.ts."""
    os.makedirs(TRANSLATIONS_DIR, exist_ok=True)

    # First, run PyQt6's pylupdate to gather all self.tr() and tr() calls
    try:
        import subprocess
        cmd = [
            sys.executable, "-m", "PyQt6.lupdate.pylupdate",
            "src/ui", "src/core",
            "--ts", TEMPLATE_TS,
            "--no-obsolete",
            "--no-summary"
        ]
        subprocess.run(cmd, cwd=ROOT_DIR, check=True, capture_output=True)
        print("✓ Successfully executed PyQt6 pylupdate on src/ui and src/core")
    except Exception as e:
        print(f"pylupdate note: {e}")

    # Second, scan UI files for explicit tooltips and UI components
    # to guarantee 100% coverage
    additional_strings: Dict[str, set] = {}  # context -> set of strings

    ui_files = glob.glob(os.path.join(ROOT_DIR, "src", "ui", "**", "*.py"), recursive=True)
    ui_patterns = [
        re.compile(r'\.setToolTip\(\s*["\'](.*?)["\']\s*\)'),
        re.compile(r'\.setStatusTip\(\s*["\'](.*?)["\']\s*\)'),
        re.compile(r'\.setPlaceholderText\(\s*["\'](.*?)["\']\s*\)'),
        re.compile(r'\.setWindowTitle\(\s*["\'](.*?)["\']\s*\)'),
        re.compile(r'\.showMessage\(\s*["\'](.*?)["\']\s*,?'),
        re.compile(r'QPushButton\(\s*["\'](.*?)["\']'),
        re.compile(r'QLabel\(\s*["\'](.*?)["\']'),
        re.compile(r'QAction\([^,\)]*["\'](.*?)["\']'),
        re.compile(r'\.addMenu\(\s*["\'](.*?)["\']'),
        re.compile(r'\.addAction\(\s*["\'](.*?)["\']'),
        re.compile(r'QCheckBox\(\s*["\'](.*?)["\']'),
        re.compile(r'QRadioButton\(\s*["\'](.*?)["\']'),
        re.compile(r'QGroupBox\(\s*["\'](.*?)["\']'),
    ]

    for py_file in ui_files:
        ctx_name = os.path.basename(py_file).replace(".py", "").capitalize() + "Dialog"
        if "main_window" in py_file:
            ctx_name = "MainWindow"

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            for pattern in ui_patterns:
                for m in pattern.finditer(content):
                    s = m.group(1).strip()
                    # Filter out non-translatable tokens like icon names, styles, or URLs
                    if (s and len(s) > 1 and not s.startswith("http")
                            and not s.startswith(":") and not s.startswith("%")
                            and not s.startswith("font-") and not s.startswith("color:")
                            and not s.startswith("#") and "\n" not in s):
                        additional_strings.setdefault(ctx_name, set()).add(s)
        except Exception:
            pass

    # Merge additional strings into template .ts
    if os.path.exists(TEMPLATE_TS):
        tree = ET.parse(TEMPLATE_TS)
        root = tree.getroot()
    else:
        root = ET.Element("TS", {"version": "2.1", "language": "en_US", "sourcelanguage": "en_US"})
        tree = ET.ElementTree(root)

    existing: Dict[str, set] = {}
    for ctx in root.findall("context"):
        cname = ctx.findtext("name") or "BDM"
        existing[cname] = set()
        for msg in ctx.findall("message"):
            src = msg.findtext("source")
            if src:
                existing[cname].add(src)

    added_count = 0
    for cname, strings in additional_strings.items():
        ctx_elem = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == cname:
                ctx_elem = ctx
                break
        if ctx_elem is None:
            ctx_elem = ET.SubElement(root, "context")
            name_el = ET.SubElement(ctx_elem, "name")
            name_el.text = cname
            existing[cname] = set()

        for s in strings:
            if s not in existing.get(cname, set()):
                msg = ET.SubElement(ctx_elem, "message")
                src_el = ET.SubElement(msg, "source")
                src_el.text = s
                trans_el = ET.SubElement(msg, "translation")
                trans_el.text = s  # English source translates to itself
                existing[cname].add(s)
                added_count += 1

    # Format English translations to be filled in with the source text
    total_messages = 0
    for ctx in root.findall("context"):
        for msg in ctx.findall("message"):
            total_messages += 1
            src_text = msg.findtext("source") or ""
            trans_elem = msg.find("translation")
            if trans_elem is not None:
                if not trans_elem.text:
                    trans_elem.text = src_text
                if "type" in trans_elem.attrib:
                    del trans_elem.attrib["type"]

    # Write formatted XML
    ET.indent(tree, space="    ")
    tree.write(TEMPLATE_TS, encoding="utf-8", xml_declaration=True)
    print(f"✓ Master template written to {TEMPLATE_TS} ({total_messages} total strings, +{added_count} UI/tooltips added)")
    return TEMPLATE_TS


# ==============================================================================
# 3. Gemini AI Translation Engine
# ==============================================================================

def call_gemini_api(prompt: str, api_key: str, model: str = "gemini-flash-lite-latest", max_retries: int = 5) -> str:
    """Call the official Google Gemini REST API with automatic rate-limit backoff."""
    import time
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries):
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                res_json = json.loads(body)
                candidates = res_json.get("candidates", [])
                if not candidates:
                    raise ValueError("No candidates returned from Gemini API")
                text = candidates[0]["content"]["parts"][0]["text"]
                return text
        except error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            # Retry on rate limits (429) and temporary high-demand service spikes (503 / 5xx)
            if (e.code == 429 or e.code == 503 or e.code >= 500) and attempt < max_retries - 1:
                # If daily quota limit exceeded, don't spin pointlessly
                if "Quota exceeded" in err_body and "retry in" in err_body:
                    raise RuntimeError(f"Gemini API Quota Exceeded for {model}: {err_body}")
                wait_time = (2 ** attempt) * 4
                print(f"    [Temporary API {e.code}] Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            raise RuntimeError(f"Gemini API HTTP Error {e.code}: {err_body}")
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            raise RuntimeError(f"Gemini API request failed: {e}")
    raise RuntimeError("Gemini API max retries exceeded.")


def translate_language_gemini(target_lang: str, target_name: str, api_key: str, batch_size: int = 60, model: str = "gemini-flash-lite-latest"):
    """Translate all strings in bdm_en.ts into target language using Gemini AI."""
    if not os.path.exists(TEMPLATE_TS):
        extract_strings()

    tree = ET.parse(TEMPLATE_TS)
    root = tree.getroot()

    target_ts = os.path.join(TRANSLATIONS_DIR, f"bdm_{target_lang}.ts")
    existing_trans: Dict[Tuple[str, str], str] = {}

    if os.path.exists(target_ts):
        try:
            old_tree = ET.parse(target_ts)
            for ctx in old_tree.getroot().findall("context"):
                cname = ctx.findtext("name") or "BDM"
                for msg in ctx.findall("message"):
                    src = msg.findtext("source")
                    trans = msg.findtext("translation")
                    if src and trans and trans != src:
                        existing_trans[(cname, src)] = trans
        except Exception:
            pass

    # Collect strings that need translation
    to_translate: List[Tuple[str, str, ET.Element]] = []  # (context, source, message_element)
    for ctx in root.findall("context"):
        cname = ctx.findtext("name") or "BDM"
        for msg in ctx.findall("message"):
            src = msg.findtext("source")
            if not src:
                continue
            if (cname, src) in existing_trans:
                continue
            to_translate.append((cname, src, msg))

    print(f"\n[{target_lang} - {target_name}] Total strings to translate: {len(to_translate)} (Already translated: {len(existing_trans)})")

    system_instruction = f"""
You are an expert technical translator localizing Bengal Download Manager (BDM), a high-performance open-source desktop download manager.
Translate the provided English UI strings into {target_name} ({target_lang}).

STRICT LOCALIZATION RULES:
1. UI keyboard accelerators:
   - For Latin-based languages (English, Spanish, French, German, etc.): Preserve accelerators like '&File' or '&Tasks' with '&' in an appropriate place.
   - For CJK (Chinese, Japanese, Korean): Use the standard format appending the shortcut, e.g., '文件(&F)' or 'ファイル(&F)'.
   - For Indic scripts (Bengali, Hindi, etc.) and RTL scripts (Arabic, Persian): DO NOT include '&' accelerators inside translated words because '&' severs Unicode combining vowel marks (কার/মাত্রা) and breaks font shaping. Omit the '&' completely.
2. Preserve all format placeholders like '%1', '%2', '%s', '%n', '{{0}}' exactly as they appear.
3. Preserve HTML tags like '<b>', '</i>', '<a href="...">'.
4. Use standard download manager and networking terminology (e.g., 'Download', 'Pause', 'Resume', 'Queue', 'Chunk', 'Speed limit', 'Proxy', 'Aria2', 'Hash').
5. Return a JSON array of objects with 'id' and 'translation'. Example:
[
  {{"id": 0, "translation": "..."}},
  {{"id": 1, "translation": "..."}}
]
"""

    for i in range(0, len(to_translate), batch_size):
        chunk = to_translate[i:i + batch_size]
        payload_items = [{"id": idx, "context": c, "source": s} for idx, (c, s, _) in enumerate(chunk)]
        prompt = system_instruction + "\n\nTranslate this JSON list:\n" + json.dumps(payload_items, ensure_ascii=False)

        print(f"  Translating batch {i + 1} to {min(i + batch_size, len(to_translate))} of {len(to_translate)}...")
        raw_resp = call_gemini_api(prompt, api_key, model=model)
        try:
            results = json.loads(raw_resp, strict=False)
            res_dict = {item["id"]: item["translation"] for item in results if "id" in item and "translation" in item}
            for idx, (c, s, msg_el) in enumerate(chunk):
                if idx in res_dict:
                    existing_trans[(c, s)] = res_dict[idx]
            save_ts_file(root, existing_trans, target_lang, target_ts)
        except Exception as e:
            print(f"  Warning: Failed batch {i + 1}: {e}")
        time.sleep(2.0)

    # Final compile to assets/translations/bdm_<lang>.qm
    save_ts_file(root, existing_trans, target_lang, target_ts)
    print(f"✓ Successfully saved {target_ts}")

    qm_target = os.path.join(ASSETS_TRANSLATIONS_DIR, f"bdm_{target_lang}.qm")
    count = compile_ts_file(target_ts, qm_target)
    print(f"✓ Compiled {qm_target} ({count} translations)")


def save_ts_file(root: ET.Element, existing_trans: Dict[Tuple[str, str], str], target_lang: str, target_ts: str):
    """Write target .ts XML file with current translations."""
    target_root = ET.Element("TS", {"version": "2.1", "language": target_lang, "sourcelanguage": "en_US"})
    target_tree = ET.ElementTree(target_root)

    for ctx in root.findall("context"):
        cname = ctx.findtext("name") or "BDM"
        ctx_elem = ET.SubElement(target_root, "context")
        name_el = ET.SubElement(ctx_elem, "name")
        name_el.text = cname

        for msg in ctx.findall("message"):
            src = msg.findtext("source")
            if not src:
                continue
            msg_el = ET.SubElement(ctx_elem, "message")
            for loc in msg.findall("location"):
                msg_el.append(loc)
            src_el = ET.SubElement(msg_el, "source")
            src_el.text = src
            cmt = msg.findtext("comment") or msg.findtext("extracomment")
            if cmt:
                cmt_el = ET.SubElement(msg_el, "extracomment")
                cmt_el.text = cmt

            trans_text = existing_trans.get((cname, src))
            trans_el = ET.SubElement(msg_el, "translation")
            if trans_text:
                trans_el.text = trans_text
            else:
                trans_el.text = src
                trans_el.attrib["type"] = "unfinished"

    ET.indent(target_tree, space="    ")
    target_tree.write(target_ts, encoding="utf-8", xml_declaration=True)


# ==============================================================================
# 4. Status & Compilation CLI Handlers
# ==============================================================================

def compile_all():
    """Compile all translations/bdm_*.ts files to assets/translations/bdm_*.qm."""
    os.makedirs(ASSETS_TRANSLATIONS_DIR, exist_ok=True)
    ts_files = glob.glob(os.path.join(TRANSLATIONS_DIR, "bdm_*.ts"))
    if not ts_files:
        print("No .ts files found in translations/. Run 'extract' first.")
        return

    print(f"Compiling {len(ts_files)} translation files to binary .qm format...")
    compiled_count = 0
    for ts in sorted(ts_files):
        fname = os.path.basename(ts)
        qm_name = fname.replace(".ts", ".qm")
        qm_path = os.path.join(ASSETS_TRANSLATIONS_DIR, qm_name)
        count = compile_ts_file(ts, qm_path)
        print(f"  • {fname:20} -> {qm_name:20} ({count:4d} strings)")
        compiled_count += 1
    print(f"✓ All {compiled_count} translation catalogs compiled successfully into {ASSETS_TRANSLATIONS_DIR}")


def show_status():
    """Print translation completion status table across all languages."""
    ts_files = glob.glob(os.path.join(TRANSLATIONS_DIR, "bdm_*.ts"))
    if not ts_files:
        print("No translation catalogs found. Run 'extract' first.")
        return

    print("================================================================================")
    print(f" {'Language':<12} {'Display Name':<35} {'Total':<8} {'Done':<8} {'Pending':<8} {'%'}")
    print("--------------------------------------------------------------------------------")

    lang_map = {code: name for code, name, _ in SUPPORTED_LANGUAGES}

    for ts in sorted(ts_files):
        code = os.path.basename(ts).replace("bdm_", "").replace(".ts", "")
        name = lang_map.get(code, "Unknown")
        try:
            tree = ET.parse(ts)
            total = 0
            done = 0
            unfinished = 0
            for msg in tree.getroot().iter("message"):
                total += 1
                trans = msg.find("translation")
                if trans is not None and trans.text:
                    if trans.attrib.get("type") == "unfinished":
                        unfinished += 1
                    else:
                        done += 1
                else:
                    unfinished += 1
            pct = (done / total * 100) if total > 0 else 0
            print(f" {code:<12} {name[:34]:<35} {total:<8} {done:<8} {unfinished:<8} {pct:>5.1f}%")
        except Exception:
            print(f" {code:<12} {name[:34]:<35} ERROR")

    print("================================================================================")


# ==============================================================================
# Main CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Bengal Download Manager i18n & Translation Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract
    subparsers.add_parser("extract", help="Extract all translatable UI strings into translations/bdm_en.ts")

    # compile
    subparsers.add_parser("compile", help="Compile all translations/bdm_*.ts into assets/translations/bdm_*.qm")

    # status
    subparsers.add_parser("status", help="Show translation status table")

    # translate
    trans_p = subparsers.add_parser("translate", help="Translate strings using Gemini AI")
    trans_p.add_argument("--lang", type=str, help="Target language code (e.g. 'bn', 'ar', 'es') or 'all'")
    trans_p.add_argument("--api-key", type=str, default=os.getenv("GEMINI_API_KEY"), help="Google Gemini API Key")
    trans_p.add_argument("--batch-size", type=int, default=60, help="Number of strings per Gemini API request")
    trans_p.add_argument("--model", type=str, default="gemini-flash-lite-latest", help="Gemini model name")

    args = parser.parse_args()

    if args.command == "extract":
        extract_strings()
    elif args.command == "compile":
        compile_all()
    elif args.command == "status":
        show_status()
    elif args.command == "translate":
        if not args.api_key:
            print("Error: Gemini API key required. Provide --api-key or set GEMINI_API_KEY environment variable.")
            sys.exit(1)
        lang_map = {code: name for code, name, _ in SUPPORTED_LANGUAGES}
        if args.lang == "all":
            for code, name, _ in SUPPORTED_LANGUAGES:
                if code == "en" or code == "system":
                    continue
                translate_language_gemini(code, name, args.api_key, args.batch_size, args.model)
        elif args.lang:
            target_langs = [l.strip() for l in args.lang.split(",") if l.strip()]
            for target_code in target_langs:
                name = lang_map.get(target_code, target_code)
                translate_language_gemini(target_code, name, args.api_key, args.batch_size, args.model)
        else:
            print("Error: Specify target language via --lang <code> or --lang all")
            sys.exit(1)


if __name__ == "__main__":
    main()
