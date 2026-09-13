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
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo, QCoreApplication
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


def get_available_languages() -> List[str]:
    """Return list of all human-readable language display strings for UI dropdowns."""
    return [display for _, display in SUPPORTED_LANGUAGES]


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


def get_current_language_code() -> str:
    """Retrieve the currently configured language code from settings.json."""
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

    # If pure English, no extra translation needed
    if lang_code == "en":
        logger.debug("[i18n] Applied English (default) locale.")
        return True

    success = False

    # 1. Load Qt base system dialog translations (OK, Cancel, Yes, No, file dialog buttons)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    new_qt_trans = QTranslator()
    base_loaded = False

    for name_prefix in [f"qtbase_{target_locale}", f"qt_{target_locale}", f"qtbase_{target_locale.split('_')[0]}"]:
        if new_qt_trans.load(name_prefix, qt_translations_path):
            app.installTranslator(new_qt_trans)
            _qt_translator = new_qt_trans
            base_loaded = True
            logger.debug("[i18n] Installed Qt base translator: %s", name_prefix)
            break

    # 2. Search for Bengal DM application translations
    search_dirs = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "translations"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "translations"),
        os.path.join(os.path.dirname(__file__), "..", "..", "translations"),
    ]

    new_app_trans = QTranslator()
    app_loaded = False

    for s_dir in search_dirs:
        abs_dir = os.path.abspath(s_dir)
        if not os.path.isdir(abs_dir):
            continue
        for candidate in [f"bengal_{target_locale}", f"bengal_{target_locale.split('_')[0]}", f"stellar_{target_locale}"]:
            qm_path = os.path.join(abs_dir, f"{candidate}.qm")
            if os.path.isfile(qm_path) and new_app_trans.load(qm_path):
                app.installTranslator(new_app_trans)
                _app_translator = new_app_trans
                app_loaded = True
                logger.debug("[i18n] Installed application translator: %s", qm_path)
                break
        if app_loaded:
            break

    success = base_loaded or app_loaded
    logger.info("[i18n] Language '%s' (locale: %s) applied. Base: %s, App: %s", lang_code, target_locale, base_loaded, app_loaded)
    return success
