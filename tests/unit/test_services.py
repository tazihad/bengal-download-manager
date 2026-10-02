"""Unit tests for core.services."""

import pytest


class TestNormalizeThemeName:
    def test_none_returns_default(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name(None) == "BDM Auto (Default)"

    def test_empty_returns_default(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name("") == "BDM Auto (Default)"

    def test_bdm_auto_variants(self):
        from core.services.theme_service import normalize_theme_name
        for v in ["bdm auto", "BDMAuto", "automatic", "auto", "BDM Auto (Default)"]:
            assert normalize_theme_name(v) == "BDM Auto (Default)"

    def test_bdm_dark_variants(self):
        from core.services.theme_service import normalize_theme_name
        for v in ["bdm dark", "BDMDark", "dark", "BDM Dark"]:
            assert normalize_theme_name(v) == "BDM Dark"

    def test_system(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name("system") == "System"

    def test_bdm_light(self):
        from core.services.theme_service import normalize_theme_name
        for v in ["bdm light", "light", "BDMLight"]:
            assert normalize_theme_name(v) == "BDM Light"

    def test_unknown_passthrough(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name("Kirigami Dark") == "Kirigami Dark"

    def test_whitespace_stripped(self):
        from core.services.theme_service import normalize_theme_name
        assert normalize_theme_name("  system  ") == "System"


class TestNormalizeAccentName:
    def test_none_returns_default(self):
        from core.services.theme_service import normalize_accent_name
        assert normalize_accent_name(None) == "BDM (Default)"

    def test_default_variants(self):
        from core.services.theme_service import normalize_accent_name
        for v in ["bdm", "default", "BDM (Default)"]:
            assert normalize_accent_name(v) == "BDM (Default)"

    def test_system(self):
        from core.services.theme_service import normalize_accent_name
        assert normalize_accent_name("system") == "System"

    def test_unknown_passthrough(self):
        from core.services.theme_service import normalize_accent_name
        assert normalize_accent_name("Crimson Red") == "Crimson Red"


class TestNormalizeIconThemeName:
    def test_none_returns_default(self):
        from core.services.theme_service import normalize_icon_theme_name
        assert normalize_icon_theme_name(None) == "BDM Auto (Default)"

    def test_bdm_dark(self):
        from core.services.theme_service import normalize_icon_theme_name
        assert normalize_icon_theme_name("bdm dark") == "BDM Dark"

    def test_bdm_auto(self):
        from core.services.theme_service import normalize_icon_theme_name
        for v in ["bdm auto", "default", "automatic", "BDM Auto (Default)"]:
            assert normalize_icon_theme_name(v) == "BDM Auto (Default)"


class TestNormalizeTrayIconName:
    def test_none_returns_default(self):
        from core.services.theme_service import normalize_tray_icon_name
        assert normalize_tray_icon_name(None) == "App Icon (Default)"

    def test_default(self):
        from core.services.theme_service import normalize_tray_icon_name
        assert normalize_tray_icon_name("app icon") == "App Icon (Default)"

    def test_unknown_passthrough(self):
        from core.services.theme_service import normalize_tray_icon_name
        assert normalize_tray_icon_name("Monochrome Light") == "Monochrome Light"


class TestNormalizeTitlebarName:
    def test_none_returns_default(self):
        from core.services.theme_service import normalize_titlebar_name
        assert normalize_titlebar_name(None) == "Automatic"

    def test_auto(self):
        from core.services.theme_service import normalize_titlebar_name
        for v in ["auto", "automatic", "system", "default"]:
            assert normalize_titlebar_name(v) == "Automatic"

    def test_light(self):
        from core.services.theme_service import normalize_titlebar_name
        assert normalize_titlebar_name("light") == "Light"

    def test_dark(self):
        from core.services.theme_service import normalize_titlebar_name
        assert normalize_titlebar_name("dark") == "Dark"


class TestLanguageService:
    def test_get_language_code_none(self):
        from core.services.language_service import get_language_code
        assert get_language_code(None) == "system"

    def test_get_language_code_empty(self):
        from core.services.language_service import get_language_code
        assert get_language_code("") == "system"

    def test_get_language_code_valid_code(self):
        from core.services.language_service import get_language_code
        assert get_language_code("en") == "en"

    def test_get_language_code_display(self):
        from core.services.language_service import get_language_code, get_language_display
        from core.services.language_service import SUPPORTED_LANGUAGES
        code, display = SUPPORTED_LANGUAGES[0]
        assert get_language_code(display) == code

    def test_get_language_display_none(self):
        from core.services.language_service import get_language_display
        assert get_language_display(None) == "System Default"

    def test_get_language_display_valid(self):
        from core.services.language_service import get_language_display, get_language_code
        from core.services.language_service import SUPPORTED_LANGUAGES
        code, display = SUPPORTED_LANGUAGES[0]
        assert get_language_display(code) == display

    def test_normalize_language_code(self):
        from core.services.language_service import normalize_language_code
        assert normalize_language_code(None) == "system"
        assert normalize_language_code("en") == "en"

    def test_supported_languages_not_empty(self):
        from core.services.language_service import SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) > 0


class TestProxyService:
    def test_flag_us(self):
        from core.services.proxy_service import country_code_to_flag
        assert country_code_to_flag("US") == "\U0001F1FA\U0001F1F8"

    def test_flag_bd(self):
        from core.services.proxy_service import country_code_to_flag
        assert country_code_to_flag("BD") == "\U0001F1E7\U0001F1E9"

    def test_flag_empty(self):
        from core.services.proxy_service import country_code_to_flag
        assert country_code_to_flag("") == "\U0001F310"

    def test_flag_invalid_length(self):
        from core.services.proxy_service import country_code_to_flag
        assert country_code_to_flag("USA") == "\U0001F310"

    def test_flag_lowercase(self):
        from core.services.proxy_service import country_code_to_flag
        assert country_code_to_flag("us") == "\U0001F1FA\U0001F1F8"

    def test_proxy_result_success_summary(self):
        from core.services.proxy_service import ProxyDetectionResult
        r = ProxyDetectionResult(is_working=True, ip="1.2.3.4", country="Germany", country_code="DE", flag_emoji="\U0001F1E9\U0001F1EA")
        s = r.summary()
        assert "working" in s
        assert "1.2.3.4" in s

    def test_proxy_result_failure_summary(self):
        from core.services.proxy_service import ProxyDetectionResult
        r = ProxyDetectionResult(is_working=False, error_message="timeout")
        s = r.summary()
        assert "failed" in s
        assert "timeout" in s

    def test_proxy_result_city_included(self):
        from core.services.proxy_service import ProxyDetectionResult
        r = ProxyDetectionResult(is_working=True, ip="1.2.3.4", country="Germany", city="Berlin", flag_emoji="X")
        assert "Berlin" in r.summary()


class TestPortService:
    def test_port_not_in_use(self):
        from core.services.port_service import is_port_in_use
        assert is_port_in_use(59999) is False

    def test_port_in_use_after_bind(self):
        import socket
        from core.services.port_service import is_port_in_use
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen(1)
        try:
            assert is_port_in_use(port) is True
        finally:
            srv.close()


class TestSocksBridgeParseHostPort:
    def test_host_with_port(self):
        from core.services.socks_bridge import parse_host_port
        assert parse_host_port("example.com:8080") == ("example.com", 8080)

    def test_host_without_port(self):
        from core.services.socks_bridge import parse_host_port
        assert parse_host_port("example.com") == ("example.com", 80)

    def test_ipv6_with_port(self):
        from core.services.socks_bridge import parse_host_port
        assert parse_host_port("[::1]:8443") == ("::1", 8443)

    def test_ipv6_without_port(self):
        from core.services.socks_bridge import parse_host_port
        assert parse_host_port("[::1]") == ("::1", 80)

    def test_default_port(self):
        from core.services.socks_bridge import parse_host_port
        assert parse_host_port("host", default_port=3128) == ("host", 3128)
