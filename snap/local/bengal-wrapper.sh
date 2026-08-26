#!/bin/sh
# Bengal Download Manager - Snap Execution Wrapper
# Sets up architecture-agnostic paths, library fallbacks, and launches Bengal DM.

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)
        TRIPLET="x86_64-linux-gnu"
        ;;
    aarch64|arm64)
        TRIPLET="aarch64-linux-gnu"
        ;;
    *)
        TRIPLET="${ARCH}-linux-gnu"
        ;;
esac

# 1. Environment & Library paths
export SNAP_APP_ROOT="$SNAP/share/bengal-download-manager"
export PYTHONPATH="$SNAP_APP_ROOT/src:$SNAP/lib/python3.12/site-packages:$SNAP/lib/python3.13/site-packages:$SNAP/usr/lib/python3/dist-packages:$PYTHONPATH"
export PATH="$SNAP/bin:$SNAP/usr/bin:$SNAP_APP_ROOT/assets/bin/$ARCH:$SNAP_APP_ROOT/assets/bin:$PATH"
export LD_LIBRARY_PATH="$SNAP/usr/lib/$TRIPLET:$SNAP/usr/lib:$SNAP/lib/$TRIPLET:$SNAP/lib:$LD_LIBRARY_PATH"

# 2. Qt6 / Wayland / Rendering configuration
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland;xcb}"
# QT_PLUGIN_PATH must be set before QApplication() is constructed so that
# platform theme plugins (libqxdgdesktopportal, libqgtk3) are discoverable.
export QT_PLUGIN_PATH="$SNAP/usr/lib/$TRIPLET/qt6/plugins:$SNAP/lib/python3.12/site-packages/PyQt6/Qt6/plugins:$SNAP/lib/python3.13/site-packages/PyQt6/Qt6/plugins${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
export QML2_IMPORT_PATH="$SNAP/usr/lib/$TRIPLET/qt6/qml:$SNAP/lib/python3.12/site-packages/PyQt6/Qt6/qml:$SNAP/lib/python3.13/site-packages/PyQt6/Qt6/qml${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
export XDG_DATA_DIRS="$SNAP/usr/share:$SNAP_APP_ROOT/assets:$XDG_DATA_DIRS"

# 3. GDK Pixbuf — do NOT override GDK_PIXBUF_MODULE_FILE or GDK_PIXBUF_MODULEDIR.
#    The GNOME extension's desktop-launch sets them to the gnome-platform paths,
#    pointing at the correct librsvg-2.so.2 v2.61.1. Overriding here would
#    redirect to the older staged version and cause:
#      undefined symbol: rsvg_handle_get_pixbuf_and_error

# 4. Aria2 bundled fallback detection
if [ -f "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" ]; then
    chmod +x "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" 2>/dev/null || true
fi

# 5. Execute Python application
if [ -x "$SNAP/usr/bin/python3" ]; then
    exec "$SNAP/usr/bin/python3" "$SNAP_APP_ROOT/src/main.py" "$@"
elif [ -x "$SNAP/bin/python3" ]; then
    exec "$SNAP/bin/python3" "$SNAP_APP_ROOT/src/main.py" "$@"
else
    exec python3 "$SNAP_APP_ROOT/src/main.py" "$@"
fi
