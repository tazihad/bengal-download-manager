#!/usr/bin/env python3
"""
Bengal Download Manager - Main Entry Point
==========================================
Clean Architecture bootstrap entry point initializing logging, High-DPI,
theming, single-instance coordination, and the primary application window.
"""

import sys
import os
import json
import threading
import traceback
from typing import Optional

# Setup import search paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)

from PyQt6.QtWidgets import QApplication, QStyle
from PyQt6.QtCore import Qt, QTimer, qInstallMessageHandler, QtMsgType

from core.utils import setup_logging, get_config_dir
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
    make_faded_icon,
    normalize_accent_name,
    normalize_icon_theme_name,
    normalize_theme_name,
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
    load_proxy_config, load_extension_config, generate_proxychains_config, get_proxychains_bin,
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


def main():
    """Application entry point and lifecycle manager."""
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
    except Exception:
        pass

    is_debug = "--debug" in sys.argv or os.environ.get("DEBUG") == "1"
    logger = setup_logging(debug=is_debug)
    if is_debug:
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
        if is_debug or mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            ctx_str = f" [{context.file}:{context.line}]" if context and context.file else ""
            logger.warning("[QT %s]%s %s", level, ctx_str, message)

    sys.excepthook = exception_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_exception_hook
    qInstallMessageHandler(qt_message_handler)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("bengal-download-manager")
    app.setApplicationName("bengal-download-manager")
    app.setDesktopFileName("io.github.tazihad.bengal-download-manager")
    app.setQuitOnLastWindowClosed(False)

    # --- SINGLE INSTANCE ENFORCEMENT ---
    if "--no-single-instance" not in sys.argv:
        if check_single_instance():
            print("Bengal Download Manager is already running. Primary instance brought to focus.")
            sys.exit(0)

    saved_theme = "BDM Dark (Default)"
    saved_accent = "BDM (Default)"
    saved_icon_theme = "BDM Auto (Default)"
    saved_tray_icon = "App Icon (Default)"
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                s_data = json.load(f)
                saved_theme = normalize_theme_name(s_data.get("theme"))
                saved_accent = normalize_accent_name(s_data.get("accent"))
                saved_icon_theme = normalize_icon_theme_name(s_data.get("icon_theme"))
                saved_tray_icon = normalize_tray_icon_name(s_data.get("tray_icon"))
    except Exception:
        pass

    apply_app_theme(saved_theme, saved_accent, saved_icon_theme, saved_tray_icon, app)
    app.setFont(init_app_font())
    
    # Initialize and set global application icon
    app_icon = get_app_icon()
    if app_icon.isNull():
        app_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
    app.setWindowIcon(app_icon)
    
    window = MainWindow()
    use_qml = "--qml" in sys.argv or "--kirigami" in sys.argv or os.environ.get("USE_KIRIGAMI") == "1"

    # Start single instance server on primary instance if enabled
    if "--no-single-instance" not in sys.argv:
        single_instance_server = SingleInstanceServer()
        def handle_single_instance_msg(payload):
            cmd = payload.get("command", "show")
            args = payload.get("args", [])
            if "--minimized" not in args:
                window.restore_window()
                if use_qml and 'qml_engine' in locals() and qml_engine.rootObjects():
                    for root in qml_engine.rootObjects():
                        if hasattr(root, "show"):
                            root.show()
                        if hasattr(root, "showNormal"):
                            root.showNormal()
                        if hasattr(root, "raise_"):
                            root.raise_()
                        if hasattr(root, "requestActivate"):
                            root.requestActivate()
            for arg in args:
                if isinstance(arg, str) and (arg.startswith("http://") or arg.startswith("https://")):
                    window.process_incoming_url(arg)

        single_instance_server.messageReceived.connect(handle_single_instance_msg)
        single_instance_server.start()
        window.single_instance_server = single_instance_server

    if "--minimized" in sys.argv:
        window.start_minimized = True
        QTimer.singleShot(0, window.hide)
        QTimer.singleShot(0, window.update_tray_action)
    else:
        window.start_minimized = False

    if use_qml:
        try:
            from PyQt6.QtQml import QQmlApplicationEngine
            from PyQt6.QtCore import QUrl
            from core.bridge import DownloadBridge

            qml_engine = QQmlApplicationEngine()
            qml_engine.addImportPath("/usr/lib/x86_64-linux-gnu/qt6/qml")
            bridge = DownloadBridge(main_window=window)
            window.bridge = bridge
            qml_engine.rootContext().setContextProperty("downloadBridge", bridge)

            qml_file = os.path.join(os.path.dirname(__file__), "ui", "qml", "Main.qml")
            qml_engine.load(QUrl.fromLocalFile(qml_file))

            if qml_engine.rootObjects():
                sys.exit(app.exec())
            else:
                print("Failed to initialize QML root object. Falling back to native UI.")
        except Exception as e:
            print(f"Kirigami QML initialization skipped ({e}). Falling back to native UI.")

    if not getattr(window, "start_minimized", False):
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()