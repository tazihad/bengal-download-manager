#!/bin/bash
# Bengal Download Manager - Snap Execution Wrapper (PyInstaller onedir mode)

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
export SNAP_APP_ROOT="$SNAP/usr/lib/bengal-download-manager"
if [ -n "$SNAP_VERSION" ] && [ -z "$APP_VERSION" ]; then
    export APP_VERSION="$SNAP_VERSION"
fi

# Find Python site-packages from gnome extension / staged python
SITE_PACKAGES=""
QT_PLUGINS=""
QML_IMPORTS=""
for py_site in "$SNAP"/lib/python3.*/site-packages; do
    if [ -d "$py_site" ]; then
        SITE_PACKAGES="${SITE_PACKAGES:+${SITE_PACKAGES}:}$py_site"
        if [ -d "$py_site/PyQt6/Qt6/plugins" ]; then
            QT_PLUGINS="${QT_PLUGINS:+${QT_PLUGINS}:}$py_site/PyQt6/Qt6/plugins"
        fi
        if [ -d "$py_site/PyQt6/Qt6/qml" ]; then
            QML_IMPORTS="${QML_IMPORTS:+${QML_IMPORTS}:}$py_site/PyQt6/Qt6/qml"
        fi
    fi
done

export PATH="$SNAP/bin:$SNAP/usr/bin:$SNAP_APP_ROOT/assets/bin/linux/$ARCH:$SNAP_APP_ROOT/assets/bin/$ARCH:$SNAP_APP_ROOT/assets/bin:$PATH"
export LD_LIBRARY_PATH="$SNAP/usr/lib/$TRIPLET:$SNAP/usr/lib:$SNAP/lib/$TRIPLET:$SNAP/lib:$SNAP_APP_ROOT:$SNAP_APP_ROOT/_internal:$LD_LIBRARY_PATH"

# 2. Qt6 / Wayland / Rendering configuration
if [ "$QT_QPA_PLATFORM" = "wayland-egl" ] || [ -z "$QT_QPA_PLATFORM" ]; then
    export QT_QPA_PLATFORM="wayland;xcb"
fi
export QT_PLUGIN_PATH="$SNAP/usr/lib/$TRIPLET/qt6/plugins${QT_PLUGINS:+:${QT_PLUGINS}}${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
export QML2_IMPORT_PATH="$SNAP/usr/lib/$TRIPLET/qt6/qml${QML_IMPORTS:+:${QML_IMPORTS}}${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
export XDG_DATA_DIRS="$SNAP/usr/share:$SNAP_APP_ROOT/assets:$XDG_DATA_DIRS"

# 3. GDK Pixbuf — do NOT override GDK_PIXBUF_MODULE_FILE or GDK_PIXBUF_MODULEDIR.

# 4. Aria2 bundled fallback detection
if [ -f "$SNAP_APP_ROOT/assets/bin/linux/$ARCH/aria2c" ]; then
    chmod +x "$SNAP_APP_ROOT/assets/bin/linux/$ARCH/aria2c" 2>/dev/null || true
elif [ -f "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" ]; then
    chmod +x "$SNAP_APP_ROOT/assets/bin/$ARCH/aria2c" 2>/dev/null || true
fi

# 5. Execute onedir binary with branded process identity
cd "$SNAP_APP_ROOT"
exec -a "bengal-download-manager" "$SNAP_APP_ROOT/bengal-download-manager" "$@"
