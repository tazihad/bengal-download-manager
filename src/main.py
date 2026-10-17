#!/usr/bin/env python3
"""
Bengal Download Manager - Main Entry Point
==========================================
Clean Architecture bootstrap entry point initializing logging, High-DPI,
theming, single-instance coordination, and the primary application window.
"""

import sys
import os
import time
import json
import threading
import traceback
import signal
import atexit
from typing import Optional

# Setup import search paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)

# Prevent host GIO modules from loading against bundled GLib in frozen/AppImage environments
# (prevents libgvfs / symbol mismatch undefined symbol: g_variant_builder_init_static and subsequent segfaults)
if getattr(sys, 'frozen', False) or os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):
    os.environ["GIO_MODULE_DIR"] = "/dev/null"
    os.environ.pop("GIO_EXTRA_MODULES", None)

from PyQt6.QtWidgets import QApplication, QStyle
from PyQt6.QtCore import Qt, QTimer, qInstallMessageHandler, QtMsgType

from core.utils import setup_logging, get_config_dir, is_debug_mode, is_verbose_mode
from core.services.ipc_service import (
    DM_CONNECTOR_PORT,
    SignalEmitter,
    IPCEmitter,
    IPCRequestHandler,
    TcpListenerThread,
    IPCListenerThread,
    get_single_instance_key,
    SingleInstanceServer,
    check_single_instance,
)
from core.services.theme_service import (
    ACCENT_COLORS,
    CURRENT_ICON_THEME,
    CURRENT_TRAY_ICON,
    CATEGORY_EXTENSIONS,
    FREEDESKTOP_MAP,
    apply_app_theme,
    apply_titlebar_theme,
    detect_accent,
    ensure_adaptive_icon_theme,
    format_timestamp_relative,
    get_app_icon,
    get_monochrome_app_icon,
    get_category_for_filename,
    get_file_icon,
    get_themed_icon,
    get_themed_tray_icon,
    init_app_font,
    is_monochrome_icon_theme,
    make_faded_icon,
    normalize_accent_name,
    normalize_highlight_text_name,
    normalize_icon_theme_name,
    normalize_theme_name,
    normalize_titlebar_name,
    normalize_tray_icon_name,
    parse_size_to_bytes,
    parse_time_to_sec,
)
from ui.dialogs import (
    AddUrlDialog, OptionsDialog, DownloadProgressDialog, 
    PropertiesDialog, DownloadCompleteDialog, ColumnDialog, DeleteDialog, RenameDialog,
    MediaDownloaderDialog, SchedulerDialog
)
from core.workers import DownloadWorker, Aria2Worker
from core.utils import (
    get_data_dir, get_config_dir, get_unique_filepath, ensure_aria2, 
    load_proxy_config, load_extension_config, get_aria2_proxy_url,
    show_in_folder, resolve_filename, open_file_generic, open_with, choose_portal_save_path,
    is_media_downloader_url, setup_logging, format_bytes, get_clean_env, get_process_memory
)
from core.memory_guard import MemoryGuard

from ui.components import (
    SortableTableWidgetItem,
    EmptyAreaClickFilter,
    SidebarItemDelegate,
    ToolbarHoverFilter,
)
from ui.main_window import MainWindow


def set_linux_process_name(name: str = "bengal-download-manager") -> None:
    """Sets the process comm name in /proc/self/comm (visible in top, ps, and task managers)."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            # PR_SET_NAME = 15 (sets /proc/self/comm, max 15 characters + null byte)
            name_bytes = name[:15].encode("utf-8")
            libc.prctl(15, ctypes.c_char_p(name_bytes), 0, 0, 0)
        except Exception:
            pass
        try:
            import setproctitle
            setproctitle.setproctitle(name)
        except Exception:
            pass


def main():
    """Application entry point and lifecycle manager."""
    # Ensure process identifies as bengal-download-manager in Linux process monitors
    set_linux_process_name("bengal-download-manager")

    # UI scale factor configuration
    try:
        cfg_path = os.path.join(get_config_dir(), "settings.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                settings_data = json.load(f)
                scale_str = settings_data.get("ui_scale", "100%")
                if scale_str and scale_str != "100%":
                    num_str = scale_str.replace("%", "").strip()
                    factor = float(num_str) / 100.0
                    os.environ["QT_SCALE_FACTOR"] = str(factor)
                # Pre-seed GTK_THEME environment for Wayland libdecor and GTK styling
                tb_mode = settings_data.get("title_bar", "Automatic")
                t_mode = settings_data.get("theme", "BDM Auto (Default)")
                if str(tb_mode).strip().lower() in ("dark", "system dark"):
                    is_dark = True
                elif str(tb_mode).strip().lower() in ("light", "system light"):
                    is_dark = False
                elif str(t_mode).strip().lower() in ("bdm dark", "dark", "ubuntu dark", "dracula", "nord"):
                    is_dark = True
                else:
                    from core.services.theme_service import is_system_dark_theme
                    is_dark = is_system_dark_theme()
                os.environ["GTK_THEME"] = "Adwaita:dark" if is_dark else "Adwaita:light"
    except Exception:
        pass

    is_debug = is_debug_mode()
    is_verbose = is_verbose_mode()
    logger = setup_logging(debug=is_debug, verbose=is_verbose)
    if is_debug or is_verbose:
        logger.debug("Command-line arguments: %s", sys.argv)

    def exception_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("=== UNHANDLED EXCEPTION CRASH ===\n%s", tb_str)

    def thread_exception_hook(args):
        tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        logger.critical("=== UNHANDLED THREAD EXCEPTION CRASH [%s] ===\n%s", args.thread.name if args.thread else "unknown", tb_str)

    def qt_message_handler(mode, context, message):
        mode_names = {
            QtMsgType.QtDebugMsg: "DEBUG",
            QtMsgType.QtInfoMsg: "INFO",
            QtMsgType.QtWarningMsg: "WARNING",
            QtMsgType.QtCriticalMsg: "CRITICAL",
            QtMsgType.QtFatalMsg: "FATAL",
        }
        level = mode_names.get(mode, "QT")
        # Ignore benign development-mode portal registration warning when running unpackaged
        if "Failed to register with host portal" in message and "App info not found" in message:
            return
        # Ignore benign HarfBuzz font shaping OpenType missing script coverage notices
        if "OpenType support missing for" in message:
            return

        ctx_str = f" [{context.file}:{context.line}]" if context and context.file else ""
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            logger.critical("[QT %s]%s %s", level, ctx_str, message)
        elif mode == QtMsgType.QtWarningMsg:
            logger.warning("[QT %s]%s %s", level, ctx_str, message)
        elif is_debug:
            if mode == QtMsgType.QtInfoMsg:
                logger.info("[QT %s]%s %s", level, ctx_str, message)
            else:
                logger.debug("[QT %s]%s %s", level, ctx_str, message)

    sys.excepthook = exception_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_exception_hook
    qInstallMessageHandler(qt_message_handler)

    from core.desktop import get_desktop_file_name

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("bengal-download-manager")
    desktop_file_name = get_desktop_file_name()
    app.setApplicationName(desktop_file_name)
    app.setApplicationDisplayName("Bengal Download Manager")
    app.setDesktopFileName(desktop_file_name)
    app.setQuitOnLastWindowClosed(False)

    # Initialize and set global application icon immediately for task managers & window managers
    app_icon = get_app_icon()
    if app_icon.isNull():
        app_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    app.setWindowIcon(app_icon)
    app.setProperty("applicationIcon", app_icon)

    # --- SINGLE INSTANCE ENFORCEMENT ---
    if "--no-single-instance" not in sys.argv:
        if check_single_instance():
            print("Bengal Download Manager is already running. Primary instance brought to focus.")
            sys.exit(0)

    saved_theme = "BDM Auto (Default)"
    saved_accent = "BDM (Default)"
    saved_icon_theme = "BDM Auto (Default)"
    saved_tray_icon = "App Icon (Default)"
    saved_title_bar = "Automatic"
    saved_highlight_text = "Automatic"
    saved_language = "system"
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                s_data = json.load(f)
                saved_theme = normalize_theme_name(s_data.get("theme"))
                saved_accent = normalize_accent_name(s_data.get("accent"))
                saved_icon_theme = normalize_icon_theme_name(s_data.get("icon_theme"))
                saved_tray_icon = normalize_tray_icon_name(s_data.get("tray_icon"))
                saved_title_bar = normalize_titlebar_name(s_data.get("title_bar"))
                saved_highlight_text = normalize_highlight_text_name(s_data.get("highlight_text"))
                saved_language = s_data.get("language", "system")
    except Exception:
        pass

    apply_app_theme(saved_theme, saved_accent, saved_icon_theme, saved_tray_icon, app=app, title_bar_mode=saved_title_bar, highlight_text=saved_highlight_text)
    from core.services.language_service import apply_language
    apply_language(app, saved_language)
    app.setFont(init_app_font())

    # Warm up build info and release verification asynchronously
    try:
        from core.build_info import warmup_build_info_async
        warmup_build_info_async()
    except Exception:
        pass

    window = MainWindow()

    # Start single instance server on primary instance if enabled
    if "--no-single-instance" not in sys.argv:
        single_instance_server = SingleInstanceServer()
        def handle_single_instance_msg(payload):
            cmd = payload.get("command", "show")
            args = payload.get("args", [])
            if "--minimized" not in args:
                window.restore_window()
            for arg in args:
                if isinstance(arg, str) and (arg.startswith("http://") or arg.startswith("https://")):
                    window.process_incoming_url(arg)

        single_instance_server.messageReceived.connect(handle_single_instance_msg)
        single_instance_server.start()
        window.single_instance_server = single_instance_server

    # --- GRACEFUL EXIT & SHUTDOWN HANDLING ---
    from core.shutdown import perform_application_shutdown

    def perform_cleanup():
        """Ensure all background threads, servers, and aria2 daemon are cleanly terminated."""
        perform_application_shutdown(window)

    app.aboutToQuit.connect(perform_cleanup)
    atexit.register(perform_cleanup)

    # Allow clean Ctrl+C / SIGTERM termination within Qt's event loop
    _sigint_count = 0

    def sig_handler(signum, frame):
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count >= 2:
            try:
                logger.info("Signal %s received again. Forcing immediate exit.", signum)
            except Exception:
                pass
            os._exit(130 if signum == signal.SIGINT else 0)

        try:
            logger.info("Signal %s received. Shutting down gracefully...", signum)
        except Exception:
            pass

        def _do_shutdown():
            try:
                if hasattr(window, "quit_app"):
                    window.quit_app()
                else:
                    perform_cleanup()
                    app.quit()
            except Exception:
                perform_cleanup()
                os._exit(0)

        # Dispatch shutdown to the Qt main thread loop
        QTimer.singleShot(0, _do_shutdown)

        # Arm fallback thread to forcibly exit if Qt event loop is blocked
        def _cli_sig_watchdog():
            time.sleep(1.2)
            try:
                perform_cleanup()
            except Exception:
                pass
            os._exit(130 if signum == signal.SIGINT else 0)

        threading.Thread(target=_cli_sig_watchdog, daemon=True, name="SigWatchdog").start()

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass

    # Heartbeat timer to periodically yield control to Python interpreter for signal handling (100ms for responsive Ctrl+C)
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(lambda: None)
    heartbeat_timer.start(100)

    if "--minimized" in sys.argv:
        window.start_minimized = True
        QTimer.singleShot(0, window.hide)
        QTimer.singleShot(0, window.update_tray_action)
    else:
        window.start_minimized = False

    if not getattr(window, "start_minimized", False):
        window.show()

    ret = app.exec()
    try:
        perform_cleanup()
    except Exception:
        pass
    os._exit(ret)


if __name__ == "__main__":
    main()