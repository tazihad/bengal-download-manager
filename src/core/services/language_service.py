"""
Bengal Download Manager - Language & Localization Service
=========================================================
Centralized internationalization (i18n) and language management service.
Handles language catalog definitions, system locale detection, QTranslator
lifecycle, and persistent language settings.
"""

import os
import json
import logging
from typing import Optional, Tuple, List, Dict
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo, QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

from core.utils import get_config_dir

logger = logging.getLogger("bengal.i18n")

# Single Source of Truth for Supported UI Languages.
# Each entry is (code, display_name) where display_name = "English Name - Native Name"
SUPPORTED_LANGUAGES: List[Tuple[str, str]] = [
    ("system", "System Default"),
    ("en", "English"),
    ("sq", "Albanian - Shqip"),
    ("am", "Amharic - አማርኛ"),
    ("ar", "Arabic - العربية"),
    ("hy", "Armenian - Հայերեն"),
    ("az", "Azerbaijani - Azərbaycan dili"),
    ("be", "Belarusian - Беларуская"),
    ("bn", "Bengali - বাংলা"),
    ("bs", "Bosnian - Bosanski"),
    ("bg", "Bulgarian - Български"),
    ("my", "Burmese - မြန်မာ"),
    ("ca", "Catalan - Català"),
    ("zh_CN", "Chinese (Simplified) - 简体中文"),
    ("zh_TW", "Chinese (Traditional) - 繁體中文"),
    ("hr", "Croatian - Hrvatski"),
    ("cs", "Czech - Čeština"),
    ("da", "Danish - Dansk"),
    ("nl", "Dutch - Nederlands"),
    ("nl_BE", "Dutch (Belgium) - Nederlands (België)"),
    ("et", "Estonian - Eesti"),
    ("fa", "Farsi (Persian) - فارسی"),
    ("fil", "Filipino - Filipino"),
    ("fi", "Finnish - Suomi"),
    ("fr", "French - Français"),
    ("gl", "Galician - Galego"),
    ("ka", "Georgian - ქართული"),
    ("de", "German - Deutsch"),
    ("el", "Greek - Ελληνικά"),
    ("gu", "Gujarati - ગુજરાતી"),
    ("ha", "Hausa - Hausa"),
    ("he", "Hebrew - עברית"),
    ("hi", "Hindi - हिन्दी"),
    ("hu", "Hungarian - Magyar"),
    ("ig", "Igbo - Igbo"),
    ("id", "Indonesian - Bahasa Indonesia"),
    ("ga", "Irish - Gaeilge"),
    ("it", "Italian - Italiano"),
    ("ja", "Japanese - 日本語"),
    ("jv", "Javanese - Basa Jawa"),
    ("kn", "Kannada - ಕನ್ನಡ"),
    ("km", "Khmer - ខ្មែរ"),
    ("ko", "Korean - 한국어"),
    ("lo", "Lao - ລາວ"),
    ("lv", "Latvian - Latviešu"),
    ("lt", "Lithuanian - Lietuvių"),
    ("mk", "Macedonian - Македонски"),
    ("ml", "Malayalam - മലയാളം"),
    ("ms", "Malay - Bahasa Melayu"),
    ("mr", "Marathi - मराठी"),
    ("mn", "Mongolian - Монгол"),
    ("ne", "Nepali - नेपाली"),
    ("nb", "Norwegian - Norsk Bokmål"),
    ("ps", "Pashto - پښتو"),
    ("pl", "Polish - Polski"),
    ("pt", "Portuguese - Português"),
    ("pt_BR", "Portuguese (Brazilian) - Português (Brasil)"),
    ("pa", "Punjabi - ਪੰਜਾਬੀ"),
    ("ro", "Romanian - Română"),
    ("ru", "Russian - Русский"),
    ("sr_Cyrl", "Serbian (Cyrillic) - Српски"),
    ("sr_Latn", "Serbian (Latin) - Srpski"),
    ("si", "Sinhala - සිංහල"),
    ("sk", "Slovak - Slovenčina"),
    ("sl", "Slovenian - Slovenščina"),
    ("es", "Spanish - Español"),
    ("sw", "Swahili - Kiswahili"),
    ("sv", "Swedish - Svenska"),
    ("ta", "Tamil - தமிழ்"),
    ("te", "Telugu - తెలుగు"),
    ("th", "Thai - ไทย"),
    ("tr", "Turkish - Türkçe"),
    ("uk", "Ukrainian - Українська"),
    ("ur", "Urdu - اردو"),
    ("ug", "Uyghur - ئۇيغۇرچە"),
    ("uz", "Uzbek - Oʻzbek"),
    ("vi", "Vietnamese - Tiếng Việt"),
    ("cy", "Welsh - Cymraeg"),
    ("yo", "Yoruba - Yorùbá"),
]

# Fast lookup mappings
CODE_TO_DISPLAY: Dict[str, str] = {code: display for code, display in SUPPORTED_LANGUAGES}
DISPLAY_TO_CODE: Dict[str, str] = {display: code for code, display in SUPPORTED_LANGUAGES}

# Global translator references kept alive across application lifetime
_app_translator: Optional[QTranslator] = None
_qt_translator: Optional[QTranslator] = None
CURRENT_LANGUAGE_CODE: str = "system"


def _get_translation_search_dirs() -> List[str]:
    """Return all directories where compiled .qm or source .ts catalogs may reside."""
    search_dirs: List[str] = []
    import sys
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        search_dirs.append(os.path.join(sys._MEIPASS, "assets", "translations"))

    curr = os.path.abspath(__file__)
    for _ in range(5):
        curr = os.path.dirname(curr)
        a_dir = os.path.join(curr, "assets", "translations")
        t_dir = os.path.join(curr, "translations")
        if os.path.isdir(a_dir) and a_dir not in search_dirs:
            search_dirs.append(a_dir)
        if os.path.isdir(t_dir) and t_dir not in search_dirs:
            search_dirs.append(t_dir)

    return search_dirs


def get_available_languages() -> List[str]:
    """
    Return list of human-readable language display strings for UI dropdowns.
    Only includes languages for which translation catalogs (.qm or .ts) exist,
    along with System Default and English.
    """
    discovered_codes = {"system", "en"}

    for s_dir in _get_translation_search_dirs():
        abs_dir = os.path.abspath(s_dir)
        if os.path.isdir(abs_dir):
            try:
                for fname in os.listdir(abs_dir):
                    if fname.startswith("bdm_") and (fname.endswith(".qm") or fname.endswith(".ts")):
                        lang_part = fname[4:].rsplit(".", 1)[0]
                        if lang_part and lang_part != "en":
                            discovered_codes.add(lang_part)
                            discovered_codes.add(lang_part.lower())
            except Exception:
                pass

    available = []
    for code, display in SUPPORTED_LANGUAGES:
        if code in ("system", "en"):
            available.append(display)
        elif code in discovered_codes or code.lower() in discovered_codes or code.split("_")[0] in discovered_codes:
            available.append(display)

    return available


def get_language_code(display_or_code: str) -> str:
    """Resolve display string or existing code into a canonical language code."""
    if not display_or_code:
        return "system"
    clean = display_or_code.strip()
    if clean in DISPLAY_TO_CODE:
        return DISPLAY_TO_CODE[clean]
    if clean in CODE_TO_DISPLAY:
        return clean
    lower = clean.lower()
    for c, d in SUPPORTED_LANGUAGES:
        if c.lower() == lower or d.lower().startswith(lower):
            return c
    return "system"


def get_language_display(code_or_display: str) -> str:
    """Resolve language code or display string into canonical display name."""
    if not code_or_display:
        return "System Default"
    clean = code_or_display.strip()
    if clean in CODE_TO_DISPLAY:
        return CODE_TO_DISPLAY[clean]
    if clean in DISPLAY_TO_CODE:
        return clean
    lower = clean.lower()
    for c, d in SUPPORTED_LANGUAGES:
        if c.lower() == lower:
            return d
    return "System Default"


def normalize_language_code(val: Optional[str]) -> str:
    """Safely normalize arbitrary config values into a valid language code."""
    return get_language_code(val or "system")


def tr(text: str, context: str = "") -> str:
    """Translate text using installed Qt translators with fallback across common contexts."""
    if not text:
        return ""
    if context:
        translated = QCoreApplication.translate(context, text)
        if translated and translated != text:
            return translated
    # Check default and common UI contexts
    for ctx in ["MainWindow", "BDM", "OptionsDialog", "AddUrlDialog"]:
        if ctx != context:
            translated = QCoreApplication.translate(ctx, text)
            if translated and translated != text:
                return translated
    return text


def get_current_language_code() -> str:
    """Retrieve the currently configured language code from memory or settings.json."""
    global CURRENT_LANGUAGE_CODE
    if CURRENT_LANGUAGE_CODE and CURRENT_LANGUAGE_CODE != "system":
        return CURRENT_LANGUAGE_CODE
    try:
        cfg_path = os.path.join(get_config_dir(), "settings.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return normalize_language_code(data.get("language", "system"))
    except Exception as e:
        logger.debug("Failed reading language from settings: %s", e)
    return "system"


def get_current_language_display() -> str:
    """Retrieve the human-readable display name of the current language."""
    return get_language_display(get_current_language_code())


def apply_language(app: Optional[QCoreApplication] = None, lang_code: Optional[str] = None) -> bool:
    """
    Install Qt translators matching the desired language code onto the application instance.
    Removes previously installed translators cleanly before applying new ones.
    Dynamically updates the application-wide font based on the language script.
    Enforces Left-to-Right layout direction so widgets do not move for RTL languages.
    """
    global _app_translator, _qt_translator, CURRENT_LANGUAGE_CODE

    if app is None:
        app = QApplication.instance()
    if app is None:
        return False

    if lang_code is None:
        lang_code = get_current_language_code()

    lang_code = normalize_language_code(lang_code)
    CURRENT_LANGUAGE_CODE = lang_code

    # Remove previous translators if installed
    if _app_translator is not None:
        try:
            app.removeTranslator(_app_translator)
        except Exception:
            pass
        _app_translator = None

    if _qt_translator is not None:
        try:
            app.removeTranslator(_qt_translator)
        except Exception:
            pass
        _qt_translator = None

    # Determine effective target locale
    if lang_code == "system":
        target_locale = QLocale.system().name()
    elif lang_code == "en":
        target_locale = "en_US"
    else:
        target_locale = lang_code

    QLocale.setDefault(QLocale(target_locale))

    # Lock layout direction to LeftToRight so widgets, sidebar, toolbars, and dialogs
    # never flip or shift position when Arabic, Persian, Hebrew, or Urdu is active
    if isinstance(app, QApplication):
        app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    # Update application font immediately for the target language
    if isinstance(app, QApplication):
        try:
            from core.services.theme_service import init_app_font
            app.setFont(init_app_font(lang_code))
        except Exception as e:
            logger.debug("[i18n] Error updating font for '%s': %s", lang_code, e)

    # If pure English, no extra translation catalog needed
    if lang_code == "en":
        logger.debug("[i18n] Language 'en' (locale: en_US) applied.")
        return True

    # 1. Load Qt base system dialog translations (OK, Cancel, Yes, No, file dialog buttons)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    new_qt_trans = QTranslator(app)
    base_loaded = False

    for name_prefix in [f"qtbase_{target_locale}", f"qt_{target_locale}", f"qtbase_{target_locale.split('_')[0]}"]:
        if new_qt_trans.load(name_prefix, qt_translations_path):
            app.installTranslator(new_qt_trans)
            _qt_translator = new_qt_trans
            base_loaded = True
            logger.debug("[i18n] Installed Qt base translator: %s", name_prefix)
            break

    # 2. Search for Bengal DM application translations (compiled .qm binaries)
    search_dirs = _get_translation_search_dirs()

    app_loaded = False
    prefixes = [
        f"bdm_{target_locale}",
        f"bdm_{target_locale.split('_')[0]}",
    ]

    for s_dir in search_dirs:
        abs_dir = os.path.abspath(s_dir)
        if not os.path.isdir(abs_dir):
            continue
        for prefix in prefixes:
            qm_path = os.path.join(abs_dir, f"{prefix}.qm")
            if os.path.isfile(qm_path):
                trans = QTranslator(app)
                if trans.load(qm_path):
                    app.installTranslator(trans)
                    _app_translator = trans
                    app_loaded = True
                    logger.debug("[i18n] Installed QM application translator: %s", qm_path)
                    break
        if app_loaded:
            break

    success = base_loaded or app_loaded or lang_code == "system"
    font_family = app.font().family() if isinstance(app, QApplication) else "N/A"
    logger.debug(
        "[i18n] Language '%s' (locale: %s) applied. Font: %s, Base: %s, App: %s",
        lang_code, target_locale, font_family, base_loaded, app_loaded
    )
    return success
