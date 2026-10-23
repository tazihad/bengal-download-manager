"""
Tests for autostart desktop entry resolution, creation, and cleanup.
"""

import os
import sys
import tempfile
import pytest

from core.utils import (
    get_autostart_filepath,
    is_autostart_enabled,
    set_autostart_enabled,
    get_executable_command,
    is_running_in_flatpak,
    is_user_flatpak,
    get_flatpak_autostart_icon,
    get_flatpak_autostart_commandline,
    get_flatpak_autostart_state,
    sync_flatpak_autostart,
    FLATPAK_AUTOSTART_SETTINGS_KEY,
    LEGACY_AUTOSTART_FILENAMES,
)


def test_get_autostart_filepath_default(monkeypatch):
    """Default autostart filepath should point to bd.com.zihad.BengalDownloadManager.desktop."""
    monkeypatch.delenv("SNAP", raising=False)
    path = get_autostart_filepath()
    assert os.path.basename(path) == "bd.com.zihad.BengalDownloadManager.desktop"
    assert ".config/autostart" in path


def test_get_autostart_filepath_snap_custom(tmp_path, monkeypatch):
    """Under Snap, get_autostart_filepath should inspect snap.yaml for autostart field."""
    snap_meta = tmp_path / "meta"
    snap_meta.mkdir(parents=True)
    snap_yaml = snap_meta / "snap.yaml"
    snap_yaml.write_text("name: bengal-download-manager\napps:\n  bdm:\n    autostart: bd.com.zihad.BengalDownloadManager.desktop\n")

    monkeypatch.setenv("SNAP", str(tmp_path))
    path = get_autostart_filepath()
    assert os.path.basename(path) == "bd.com.zihad.BengalDownloadManager.desktop"


def test_autostart_enable_disable_lifecycle(tmp_path, monkeypatch):
    """Verify set_autostart_enabled creates entry, cleans orphans, and disables cleanly."""
    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))

    # Pre-populate orphan legacy files
    orphan = autostart_dir / "bengal-download-manager.desktop"
    orphan.write_text("[Desktop Entry]\nName=Legacy\n")
    assert orphan.exists()

    # Enable autostart
    assert set_autostart_enabled(True, start_minimized=True)
    active_path = autostart_dir / "bd.com.zihad.BengalDownloadManager.desktop"
    assert active_path.exists()
    content = active_path.read_text()
    assert "--minimized" in content
    assert "StartupWMClass=bd.com.zihad.BengalDownloadManager" in content

    # Verify orphan was cleaned up
    assert not orphan.exists()
    assert is_autostart_enabled()

    # Disable autostart
    assert set_autostart_enabled(False)
    assert not active_path.exists()
    assert not is_autostart_enabled()


def test_get_executable_command_modes(monkeypatch):
    """Verify get_executable_command correctly detects Flatpak, Snap, AppImage, and Dev."""
    # Flatpak
    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert get_executable_command(start_minimized=True) == "flatpak run bd.com.zihad.BengalDownloadManager --minimized"

    # Snap
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("SNAP_NAME", "bengal-download-manager")
    monkeypatch.setenv("SNAP", "/snap/bengal-download-manager/current")
    assert get_executable_command(start_minimized=False) == "bengal-download-manager"
    assert get_executable_command(start_minimized=True) == "bengal-download-manager --minimized"


def test_snap_desktop_entry_icon_specification():
    """Verify snap desktop entry declares canonical ${SNAP}/meta/gui/icon.png for start menu integration."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop_path = os.path.join(repo_root, "snap", "gui", "bengal-download-manager.desktop")
    assert os.path.exists(desktop_path)

    with open(desktop_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Icon=${SNAP}/meta/gui/icon.png" in content
    assert "Exec=bengal-download-manager %u" in content
    assert "StartupWMClass=bengal-download-manager_bengal-download-manager" in content


def test_autostart_snap_icon_path(tmp_path, monkeypatch):
    """Under Snap, set_autostart_enabled should write canonical snap icon path."""
    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir(parents=True)
    monkeypatch.setenv("SNAP", str(snap_dir))
    monkeypatch.setenv("SNAP_INSTANCE_NAME", "bengal-download-manager")

    assert set_autostart_enabled(True)
    active_path = autostart_dir / "bengal-download-manager.desktop"
    assert active_path.exists()
    content = active_path.read_text()
    assert "Icon=/snap/bengal-download-manager/current/meta/gui/icon.png" in content


def test_flatpak_autostart_portal_lifecycle(tmp_path, monkeypatch):
    """Under Flatpak, set_autostart_enabled should invoke org.freedesktop.portal.Background and manage sandbox desktop entry."""
    import subprocess
    from unittest.mock import MagicMock

    autostart_dir = tmp_path / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/")))
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")

    assert is_running_in_flatpak()

    gdbus_calls = []

    def mock_run(cmd, *args, **kwargs):
        gdbus_calls.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "(objectpath '/org/freedesktop/portal/desktop/request/1_99/t',)"
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)

    # 1. Enable autostart with minimized
    assert set_autostart_enabled(True, start_minimized=True)

    assert len(gdbus_calls) == 1
    call_str = " ".join(gdbus_calls[0])
    assert "org.freedesktop.portal.Background.RequestBackground" in call_str
    assert "'autostart': <true>" in call_str
    assert "'--minimized'" in call_str

    sandbox_file = autostart_dir / "bd.com.zihad.BengalDownloadManager.desktop"
    assert sandbox_file.exists()
    content = sandbox_file.read_text()
    assert "Icon=" in content
    assert is_autostart_enabled()

    # 2. Disable autostart
    assert set_autostart_enabled(False)
    assert len(gdbus_calls) == 2
    disable_call_str = " ".join(gdbus_calls[1])
    assert "org.freedesktop.portal.Background.RequestBackground" in disable_call_str
    assert "'autostart': <false>" in disable_call_str

    assert not sandbox_file.exists()
    assert not is_autostart_enabled()


def test_flatpak_icon_resolution_user_and_system(tmp_path, monkeypatch):
    """Verify get_flatpak_autostart_icon returns user icon for --user and system icon for system-wide."""
    fake_info = tmp_path / ".flatpak-info"
    monkeypatch.setattr(os.path, "exists", lambda p: True if p == "/.flatpak-info" else (p == str(fake_info)))
    
    # User flatpak info
    fake_info.write_text("[Instance]\napp-path=/home/testuser/.local/share/flatpak/app/bd.com.zihad.BengalDownloadManager\n")
    import builtins
    orig_open = builtins.open
    def mock_open(path, *args, **kwargs):
        if path == "/.flatpak-info":
            return orig_open(str(fake_info), *args, **kwargs)
        return orig_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", mock_open)

    assert is_user_flatpak()
    user_icon = get_flatpak_autostart_icon()
    assert ".local/share/flatpak" in user_icon

    # System flatpak info
    fake_info.write_text("[Instance]\napp-path=/var/lib/flatpak/app/bd.com.zihad.BengalDownloadManager\n")
    assert not is_user_flatpak()
    sys_icon = get_flatpak_autostart_icon()
    assert "/var/lib/flatpak" in sys_icon


def test_flatpak_autostart_persistent_settings_detection(tmp_path, monkeypatch):
    """Verify is_autostart_enabled checks persistent settings.json inside Flatpak sandbox."""
    import json
    from core.utils import get_config_dir

    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    settings_file = cfg_dir / "settings.json"
    settings_file.write_text(json.dumps({"autostart_enabled": True, "start_minimized": True}))

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "sandbox_home" / p.lstrip("~/")))

    # Even if sandbox desktop file does NOT exist, is_autostart_enabled returns True from settings
    assert is_autostart_enabled()

    # When autostart_enabled is False in settings, returns False
    settings_file.write_text(json.dumps({"autostart_enabled": False, "start_minimized": False}))
    assert not is_autostart_enabled()


def test_mainwindow_start_minimized_tray_state(qapp, monkeypatch):
    """Verify MainWindow(start_minimized=True) initializes immediately with _is_in_tray=True."""
    from ui.main_window import MainWindow

    # Prevent network/service initialization during unit test
    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)

    win = MainWindow(start_ipc=False, start_minimized=True)
    assert win.start_minimized is True
    assert win._is_in_tray is True
    assert not win.isVisible()
    win.close()


def test_setup_tray_icon_retry_timer(qapp, monkeypatch):
    """Verify setup_tray_icon arms a retry timer if system tray host is initially unavailable."""
    from ui.main_window import MainWindow
    from PyQt6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)

    win = MainWindow(start_ipc=False, start_minimized=False)
    assert win.tray_icon is None
    assert hasattr(win, "_tray_retry_timer")
    assert win._tray_retry_timer.isActive()
    win._tray_retry_timer.stop()
    win.close()


def test_is_autostart_enabled_null_settings_falls_through(tmp_path, monkeypatch):
    """A null autostart_enabled value must not be reported as a false negative."""
    import json

    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "settings.json"
    cfg_file.write_text(json.dumps({"autostart_enabled": None, "start_minimized": True}))

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/")))

    # No desktop entry visible: falls through to the file checks -> False
    assert not is_autostart_enabled()

    # With a desktop entry present, the null value must not mask it
    autostart_dir = tmp_path / "home" / ".config" / "autostart"
    autostart_dir.mkdir(parents=True)
    (autostart_dir / "bd.com.zihad.BengalDownloadManager.desktop").write_text("[Desktop Entry]\nName=BDM\n")
    assert is_autostart_enabled()


def test_set_autostart_preserves_malformed_settings(tmp_path, monkeypatch):
    """A malformed settings.json must never be replaced by a partial payload."""
    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "settings.json"
    original = '{"theme": "BDM Dark", broken json'
    cfg_file.write_text(original)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/")))
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))

    set_autostart_enabled(True)

    # File is left untouched instead of being wiped down to two keys
    assert cfg_file.read_text() == original


def test_disable_autostart_clears_start_minimized(tmp_path, monkeypatch):
    """Turning autostart off must clear the stale start_minimized flag."""
    import json

    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "settings.json"
    cfg_file.write_text(json.dumps({"start_minimized": True, "theme": "BDM Dark"}))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/")))
    orig_exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p))

    set_autostart_enabled(False)

    data = json.loads(cfg_file.read_text())
    assert data["start_minimized"] is False
    assert data["autostart_enabled"] is False
    assert data["theme"] == "BDM Dark"


def test_save_settings_never_persists_null_autostart(qapp, monkeypatch, tmp_path):
    """load/save_settings must round-trip autostart_enabled as a real boolean."""
    import json
    from core.utils import get_config_dir
    from ui.main_window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    cfg_dir = get_config_dir()
    cfg_file = os.path.join(cfg_dir, "settings.json")
    # Legacy settings file: autostart_enabled key absent (upgrade from <= 0.3.3)
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({"theme": "BDM Dark"}, f)

    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)

    win = MainWindow(start_ipc=False)
    win.save_settings()

    with open(cfg_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["autostart_enabled"] is not None
    assert isinstance(saved["autostart_enabled"], bool)
    assert isinstance(saved["start_minimized"], bool)
    win.close()


def test_tray_action_label_tracks_visibility(qapp, monkeypatch):
    """The tray toggle label must read Hide while visible and Show while hidden."""
    from ui.main_window import MainWindow
    from PyQt6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)

    win = MainWindow(start_ipc=False, start_minimized=False)
    if win.action_tray_toggle is None:
        pytest.skip("QSystemTrayIcon unavailable in this environment")

    win.show()
    assert win.action_tray_toggle.text() == "Hide"

    win.hide()
    assert win.action_tray_toggle.text() == "Show"
    win.close()


def test_tray_retry_gives_up_and_restores_hidden_window(qapp, monkeypatch):
    """Without any tray host, a minimized launch must restore a visible window."""
    from ui.main_window import MainWindow
    from PyQt6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)

    win = MainWindow(start_ipc=False, start_minimized=True)
    assert not win.isVisible()

    # Drive the retry callback to its give-up threshold
    win._tray_retry_count = 9
    win._tray_retry_timer.timeout.emit()

    assert not win._tray_retry_timer.isActive()
    assert win.isVisible()
    win.close()


def test_flatpak_portal_gdbus_uses_clean_environment(tmp_path, monkeypatch):
    """gdbus must not inherit PyInstaller's LD_LIBRARY_PATH (which breaks GLib)."""
    import subprocess
    from unittest.mock import MagicMock
    from core.utils import _set_flatpak_autostart_portal

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI00000002b4J0PN")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI00000002b4J0PN", raising=False)

    captured = {}

    def mock_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        res = MagicMock()
        res.returncode = 0
        res.stdout = "(objectpath '/org/freedesktop/portal/desktop/request/1_1/t',)"
        res.stderr = ""
        return res

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert _set_flatpak_autostart_portal(True, start_minimized=True)
    assert captured["env"] is not None
    assert "LD_LIBRARY_PATH" not in captured["env"]
    assert not any("_MEI" in value for value in captured["env"].values())
    assert "'--minimized'" in " ".join(captured["cmd"])


def test_flatpak_portal_qtdbus_fallback_includes_commandline(tmp_path, monkeypatch):
    """The QDBus fallback must send commandline, otherwise --minimized is lost."""
    from unittest.mock import MagicMock
    import PyQt6.QtDBus as QtDBus
    from core.utils import _set_flatpak_autostart_portal

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )
    monkeypatch.setattr("core.utils.shutil.which", lambda name: None)

    captured = {}

    class FakeBus:
        def isConnected(self):
            return True

        def call(self, msg):
            captured["args"] = msg.arguments()
            reply = MagicMock()
            reply.type.return_value = QtDBus.QDBusMessage.MessageType.ReplyMessage
            return reply

    monkeypatch.setattr(
        QtDBus.QDBusConnection, "sessionBus", staticmethod(lambda: FakeBus())
    )

    assert _set_flatpak_autostart_portal(True, start_minimized=True)
    options = captured["args"][1]
    assert options["autostart"] is True
    assert options["commandline"] == ["bengal-download-manager", "--minimized"]


def test_flatpak_autostart_records_portal_state(tmp_path, monkeypatch):
    """settings.json must record autostart/minimized intent and portal state."""
    import json
    import subprocess
    from unittest.mock import MagicMock

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )

    def mock_run(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        res.stdout = "()"
        res.stderr = ""
        return res

    monkeypatch.setattr(subprocess, "run", mock_run)

    cfg_file = tmp_path / "config" / "bengal-download-manager" / "settings.json"

    assert set_autostart_enabled(True, start_minimized=True)
    cfg = json.loads(cfg_file.read_text())
    assert cfg["autostart_enabled"] is True
    assert cfg["start_minimized"] is True
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["registered"] is True
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["commandline"] == [
        "bengal-download-manager",
        "--minimized",
    ]

    assert set_autostart_enabled(False)
    cfg = json.loads(cfg_file.read_text())
    assert cfg["autostart_enabled"] is False
    assert cfg["start_minimized"] is False
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["registered"] is True
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["commandline"] == []


def test_flatpak_autostart_failure_records_unregistered_state(tmp_path, monkeypatch):
    """A failed portal call must not masquerade as a successful registration."""
    import json

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )
    monkeypatch.setattr(
        "core.utils._set_flatpak_autostart_portal", lambda *a, **k: False
    )

    assert not set_autostart_enabled(True, start_minimized=True)
    cfg_file = tmp_path / "config" / "bengal-download-manager" / "settings.json"
    cfg = json.loads(cfg_file.read_text())
    assert cfg["autostart_enabled"] is True
    assert cfg["start_minimized"] is True
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["registered"] is False
    assert cfg[FLATPAK_AUTOSTART_SETTINGS_KEY]["commandline"] == []


def test_sync_flatpak_autostart_repairs_drift(tmp_path, monkeypatch):
    """A missing or stale portal commandline is re-registered exactly once."""
    import json

    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "settings.json"
    cfg_file.write_text(
        json.dumps(
            {
                "autostart_enabled": True,
                "start_minimized": True,
                "theme": "BDM Dark",
            }
        )
    )

    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )

    calls = []

    def fake_portal(enabled, start_minimized=False):
        calls.append((enabled, start_minimized))
        return True

    monkeypatch.setattr("core.utils._set_flatpak_autostart_portal", fake_portal)

    updates = []
    assert sync_flatpak_autostart(on_update=updates.append)
    assert calls == [(True, True)]
    data = json.loads(cfg_file.read_text())
    assert data["theme"] == "BDM Dark"
    assert data[FLATPAK_AUTOSTART_SETTINGS_KEY]["registered"] is True
    assert data[FLATPAK_AUTOSTART_SETTINGS_KEY]["commandline"] == [
        "bengal-download-manager",
        "--minimized",
    ]
    assert updates and updates[0]["registered"] is True

    # No drift -> no portal call.
    assert not sync_flatpak_autostart()
    assert calls == [(True, True)]

    # Stale registration without --minimized -> repaired once.
    data[FLATPAK_AUTOSTART_SETTINGS_KEY] = {
        "registered": True,
        "commandline": ["bengal-download-manager"],
    }
    cfg_file.write_text(json.dumps(data))
    assert sync_flatpak_autostart()
    assert calls == [(True, True), (True, True)]


def test_sync_flatpak_autostart_noops_outside_flatpak_and_when_disabled(
    tmp_path, monkeypatch
):
    """Startup repair only applies to enabled Flatpak autostart."""
    import json

    cfg_dir = tmp_path / "config" / "bengal-download-manager"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "settings.json"
    cfg_file.write_text(json.dumps({"autostart_enabled": False, "start_minimized": True}))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path / "home" / p.lstrip("~/"))
    )
    orig_exists = os.path.exists
    monkeypatch.setattr(
        os.path, "exists", lambda p: False if p == "/.flatpak-info" else orig_exists(p)
    )

    calls = []
    monkeypatch.setattr(
        "core.utils._set_flatpak_autostart_portal",
        lambda *a, **k: calls.append(a) or True,
    )

    # Not Flatpak -> no repair even though autostart is disabled here.
    assert not sync_flatpak_autostart()

    # Flatpak, but autostart disabled -> no repair.
    monkeypatch.setenv("FLATPAK_ID", "bd.com.zihad.BengalDownloadManager")
    assert not sync_flatpak_autostart()
    assert calls == []


def test_save_settings_preserves_flatpak_autostart_block(qapp, monkeypatch, tmp_path):
    """save_settings must not drop the recorded portal state block."""
    import json
    from core.utils import get_config_dir
    from ui.main_window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    cfg_dir = get_config_dir()
    block = {
        "registered": True,
        "commandline": ["bengal-download-manager"],
        "updated_at": 1,
    }
    with open(os.path.join(cfg_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"theme": "BDM Dark", FLATPAK_AUTOSTART_SETTINGS_KEY: block}, f)

    monkeypatch.setattr(MainWindow, "start_aria2_daemon", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_data", lambda self: None)

    win = MainWindow(start_ipc=False)
    win.save_settings()

    with open(os.path.join(cfg_dir, "settings.json"), "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved[FLATPAK_AUTOSTART_SETTINGS_KEY] == block
    win.close()
