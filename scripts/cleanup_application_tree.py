#!/usr/bin/env python3
"""Remove files from the packaged application that are never loaded at runtime.

Inspired by ``tools/cleanup_application_tree.py`` from nuxeo-drive.  Bengal
Download Manager only imports a small part of the Qt6 stack (QtCore, QtGui,
QtWidgets, QtNetwork, QtSvg and QtDBus), but PyInstaller also gathers the
libraries behind optional plugins and, on some platforms, the GTK/pango stack
that Qt only needs for its GTK platform theme.

The module has two integration points:

``filter_toc(entries)``
    Removes matching entries from PyInstaller's ``Analysis`` TOCs.  This is the
    only way to slim a ``--onefile`` build, where no application directory
    survives the build and everything is packed straight into the executable.
    Import it from a ``.spec`` file::

        from cleanup_application_tree import filter_toc
        a.binaries, _ = filter_toc(a.binaries)
        a.datas, _ = filter_toc(a.datas)

``purge_tree(root)``
    Walks a ``--onedir`` output directory after PyInstaller, deletes the same
    files and reports how much space was reclaimed.

Both helpers work on Windows and macOS too; patterns that do not match simply
remove nothing.

Run standalone on a ``--onedir`` build::

    python scripts/cleanup_application_tree.py dist/bengal-download-manager

Use ``--dry-run`` to list what would be removed without touching the disk.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Iterator, Sequence

# ---------------------------------------------------------------------------
# What we never ship.
#
# Patterns are matched against paths relative to the application root (the
# ``_internal`` directory for PyInstaller 6 onedir builds) *and* against the
# bare file name, so the same list also catches the top-level symlinks that
# PyInstaller creates for Qt libraries in one-file builds.
# ---------------------------------------------------------------------------

# Qt modules Bengal Download Manager does not import.  Most are not collected
# today; keeping the full list protects us when PyInstaller's Qt hooks change.
UNUSED_QT_LIBRARIES: tuple[str, ...] = (
    "libQt6Quick*.so*",
    "libQt6Qml*.so*",
    "libQt6Labs*.so*",
    "libQt6Designer*.so*",
    "libQt6Help*.so*",
    "libQt6Pdf*.so*",
    "libQt6Multimedia*.so*",
    "libQt6Bluetooth*.so*",
    "libQt6Nfc*.so*",
    "libQt6Positioning*.so*",
    "libQt6Location*.so*",
    "libQt6Sensors*.so*",
    "libQt6SerialPort*.so*",
    "libQt6SerialBus*.so*",
    "libQt6Sql*.so*",
    "libQt6Test*.so*",
    "libQt6Web*.so*",
    "libQt6Charts*.so*",
    "libQt6DataVisualization*.so*",
    "libQt6Graphs*.so*",
    "libQt6Scxml*.so*",
    "libQt6Speech*.so*",
    "libQt6TextToSpeech*.so*",
    "libQt6RemoteObjects*.so*",
    "libQt6SpatialAudio*.so*",
    "libQt6ShaderTools*.so*",
    "libQt6Concurrent*.so*",
    "libQt6HttpServer*.so*",
    "libQt63D*.so*",
    "libQt6EglFSDeviceIntegration.so*",
)

# Optional Qt plugins for subsystems Bengal DM does not use: PDF/TIFF image
# decoders, embedded (EGLFS/linuxfb/VNC) and evdev platform plugins, SQL
# drivers, printing, Qt Help, Qt Quick/QML and 3D asset loaders.
UNUSED_QT_PLUGINS: tuple[str, ...] = (
    "**/PyQt6/Qt6/plugins/assetimporters/**",
    "**/PyQt6/Qt6/plugins/egldeviceintegrations/**",
    "**/PyQt6/Qt6/plugins/geometryloaders/**",
    "**/PyQt6/Qt6/plugins/generic/libqevdev*",
    "**/PyQt6/Qt6/plugins/help/**",
    "**/PyQt6/Qt6/plugins/imageformats/libqicns.so",
    "**/PyQt6/Qt6/plugins/imageformats/libqpdf.so",
    "**/PyQt6/Qt6/plugins/imageformats/libqtga.so",
    "**/PyQt6/Qt6/plugins/imageformats/libqtiff.so",
    "**/PyQt6/Qt6/plugins/imageformats/libqwbmp.so",
    "**/PyQt6/Qt6/plugins/mediaservice/**",
    "**/PyQt6/Qt6/plugins/multimedia/**",
    "**/PyQt6/Qt6/plugins/networkinformation/**",
    "**/PyQt6/Qt6/plugins/platforms/libqeglfs.so",
    "**/PyQt6/Qt6/plugins/platforms/libqlinuxfb.so",
    "**/PyQt6/Qt6/plugins/platforms/libqminimalegl.so",
    "**/PyQt6/Qt6/plugins/platforms/libqvkkhrdisplay.so",
    "**/PyQt6/Qt6/plugins/platforms/libqvnc.so",
    "**/PyQt6/Qt6/plugins/position/**",
    "**/PyQt6/Qt6/plugins/printsupport/**",
    "**/PyQt6/Qt6/plugins/renderers/**",
    "**/PyQt6/Qt6/plugins/renderplugins/**",
    "**/PyQt6/Qt6/plugins/sceneparsers/**",
    "**/PyQt6/Qt6/plugins/scxmldatamodel/**",
    "**/PyQt6/Qt6/plugins/sensors/**",
    "**/PyQt6/Qt6/plugins/sqldrivers/**",
    "**/PyQt6/Qt6/plugins/texttospeech/**",
    "**/PyQt6/Qt6/plugins/webview/**",
    # Qt Quick/QML runtime data (never used by this widget application).
    "**/PyQt6/Qt6/qml",
    "**/PyQt6/Qt6/qml/**",
    "**/PyQt6/Qt6/qsci",
    "**/PyQt6/Qt6/qsci/**",
)

# The GTK platform theme is the only consumer of the GTK/pango/cairo stack.
# Bengal DM paints its own theme and ships its own font, so the plugin and its
# private dependencies can go.  Qt keeps using the XCB and Wayland plugins.
UNUSED_GTK_THEME: tuple[str, ...] = (
    "**/PyQt6/Qt6/plugins/platformthemes/libqgtk3.so",
    "libgtk-3.so*",
    "libgdk-3.so*",
    "libgio-2.0.so*",
    "libgobject-2.0.so*",
    "libgmodule-2.0.so*",
    "libcairo.so*",
    "libcairo-gobject.so*",
    "libpango-1.0.so*",
    "libpangocairo-1.0.so*",
    "libpangoft2-1.0.so*",
    "libpixman-1.so*",
    "libatk-1.0.so*",
    "libatk-bridge-2.0.so*",
    "libatspi.so*",
    "libgdk_pixbuf-2.0.so*",
    "libepoxy.so*",
    "libcloudproviders.so*",
    "libthai.so*",
    "libdatrie.so*",
    "libharfbuzz.so*",
    "libgraphite2.so*",
    "libfribidi.so*",
    "libjpeg.so*",
    "libmount.so*",
    "libblkid.so*",
    "libselinux.so*",
    # NOTE: libsystemd.so and libcap.so are deliberately kept; the system
    # libdbus-1 that QtDBus links against needs libsystemd.
    # X11 helpers that only the GTK/cairo stack pulled in.
    "libXcomposite.so*",
    "libXcursor.so*",
    "libXdamage.so*",
    "libXext.so*",
    "libXfixes.so*",
    "libXi.so*",
    "libXinerama.so*",
    "libXrandr.so*",
    "libXrender.so*",
)

# Qt's TLS plugin and the OpenSSL libraries it dlopen()s are only needed by
# QtNetwork's HTTPS stack.  Bengal DM uses QtNetwork exclusively for the local
# JSON control socket; downloads go through Python (statically linked OpenSSL)
# and the statically linked aria2c binary.
UNUSED_QT_TLS: tuple[str, ...] = (
    "**/PyQt6/Qt6/plugins/tls/**",
    "libssl.so*",
    "libcrypto.so*",
)

# Qt catalogs for modules we do not ship.  ``qtbase_*.qm`` translates standard
# dialogs and buttons and is kept for every language the UI supports.
UNUSED_QT_TRANSLATIONS: tuple[str, ...] = (
    "**/PyQt6/Qt6/translations/qt_*.qm",
    "**/PyQt6/Qt6/translations/qt_help_*.qm",
)

PATTERNS: tuple[str, ...] = (
    UNUSED_QT_LIBRARIES
    + UNUSED_QT_PLUGINS
    + UNUSED_GTK_THEME
    + UNUSED_QT_TLS
    + UNUSED_QT_TRANSLATIONS
)

_ELF_MAGIC = b"\x7fELF"
_NEEDED_RE = re.compile(r"Shared library: \[([^\]]+)\]")


def _normalize(path: str) -> str:
    """Return *path* with forward slashes, regardless of the host OS."""
    return path.replace("\\", "/")


def match(path: str) -> str | None:
    """Return the first pattern matching *path*, or ``None``.

    Both the full relative path and the bare file name are tested, so a
    pattern such as ``libQt6Pdf*.so*`` also matches the top-level symlink
    ``libQt6Pdf.so.6`` that PyInstaller creates for one-file builds.
    """
    normalized = _normalize(path)
    basename = normalized.rsplit("/", 1)[-1]
    for pattern in PATTERNS:
        # Drop an optional leading ``**/`` when comparing bare file names or
        # paths that already start at ``PyQt6/...`` (PyInstaller TOC names do).
        bare = pattern[3:] if pattern.startswith("**/") else pattern
        if (
            fnmatch.fnmatchcase(normalized, pattern)
            or fnmatch.fnmatchcase(normalized, bare)
            or fnmatch.fnmatchcase(basename, bare)
        ):
            return pattern
    return None


def should_remove(path: str) -> bool:
    """Return ``True`` when *path* belongs to the purge list."""
    return match(path) is not None


# ---------------------------------------------------------------------------
# PyInstaller spec integration (--onefile and --onedir)
# ---------------------------------------------------------------------------


def filter_toc(
    entries: Iterable[tuple[str, str, str]],
    *,
    label: str = "entries",
    verify: bool = True,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Split a PyInstaller TOC into kept and removed entries.

    ``entries`` is the ``(dest_name, source_path, typecode)`` sequence exposed
    as ``Analysis.binaries`` / ``Analysis.datas``.  The returned lists can be
    assigned back to the ``Analysis`` object before ``EXE``/``COLLECT`` run.

    When *verify* is true, every kept ELF binary is checked for a ``DT_NEEDED``
    reference to a library that was just removed.  Such a reference means the
    purge list is out of date; a warning is printed instead of failing the
    build so that optional ``dlopen()``-only dependencies do not block it.
    """
    kept: list[tuple[str, str, str]] = []
    removed: list[tuple[str, str, str]] = []
    for entry in entries:
        dest, src, _typecode = entry[0], entry[1], entry[2]
        if should_remove(dest) or (src and should_remove(src)):
            removed.append(entry)
        else:
            kept.append(entry)

    if verify and removed:
        _warn_about_dangling_dependencies(kept, removed)

    if removed:
        print(f"[cleanup] {label}: removed {len(removed)} unused entries")
    return kept, removed


def _removed_names(removed: Sequence[tuple[str, str, str]]) -> set[str]:
    names: set[str] = set()
    for dest, src, _typecode in removed:
        names.add(_normalize(dest).rsplit("/", 1)[-1])
        if src:
            names.add(_normalize(src).rsplit("/", 1)[-1])
    return names


def _warn_about_dangling_dependencies(
    kept: Sequence[tuple[str, str, str]], removed: Sequence[tuple[str, str, str]]
) -> None:
    if shutil.which("readelf") is None:
        return
    gone = _removed_names(removed)
    for _dest, src, _typecode in kept:
        if not src or not os.path.isfile(src):
            continue
        for needed in _elf_needed(Path(src)):
            if needed in gone:
                print(
                    f"[cleanup] WARNING: {Path(src).name} still links against "
                    f"{needed}, which is on the purge list",
                    file=sys.stderr,
                )


def _elf_needed(path: Path) -> set[str]:
    """Return the ``DT_NEEDED`` entries of *path* (empty for non-ELF files)."""
    try:
        with path.open("rb") as handle:
            if handle.read(4) != _ELF_MAGIC:
                return set()
    except OSError:
        return set()
    try:
        result = subprocess.run(
            ["readelf", "-d", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(_NEEDED_RE.findall(result.stdout))


# ---------------------------------------------------------------------------
# Post-build directory cleanup (--onedir)
# ---------------------------------------------------------------------------


def application_root(path: Path) -> Path:
    """Return the directory that holds the bundled payload.

    PyInstaller 6 puts onedir payloads in ``_internal``; older layouts keep
    everything next to the executable.
    """
    internal = path / "_internal"
    return internal if internal.is_dir() else path


def find_useless_files(root: Path) -> list[Path]:
    """Return every file or directory below *root* that should be removed."""
    root = root.resolve()
    found: list[Path] = []
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - defensive
            continue
        if should_remove(relative):
            found.append(path)
    return found


def purge_tree(root: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Delete purge-listed files below *root*.

    Returns ``(removed_count, freed_bytes)``.  Directories are removed after
    their contents, and already-deleted children are skipped.
    """
    base = application_root(root)
    targets = sorted(find_useless_files(base), key=lambda p: len(p.parts), reverse=True)
    if not targets:
        return 0, 0

    removed = 0
    freed = 0
    removed_names: set[str] = set()

    for path in targets:
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_dir() and not path.is_symlink():
            freed += _directory_size(path)
            if not dry_run:
                shutil.rmtree(path)
        else:
            try:
                freed += path.lstat().st_size
            except OSError:
                pass
            if not dry_run:
                try:
                    path.unlink()
                except OSError:
                    continue
        removed_names.add(path.name)
        removed += 1
        print(f"[{'plan' if dry_run else 'X'}] Removed {path.relative_to(base).as_posix()}")

    if removed and not dry_run:
        _warn_about_tree_dependencies(base, removed_names)
    return removed, freed


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _warn_about_tree_dependencies(base: Path, removed_names: set[str]) -> None:
    if shutil.which("readelf") is None:
        return
    for path in base.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        for needed in _elf_needed(path):
            if needed in removed_names:
                print(
                    f"[cleanup] WARNING: {path.relative_to(base).as_posix()} still "
                    f"links against {needed}, which was removed",
                    file=sys.stderr,
                )


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"  # pragma: no cover


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove unused Qt/GTK files from a PyInstaller output tree.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        type=Path,
        help="PyInstaller onedir output directory (e.g. dist/bengal-download-manager)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be removed without deleting anything",
    )
    args = parser.parse_args(argv)

    for target in args.targets:
        if not target.is_dir():
            parser.error(f"not a directory: {target}")
        base = application_root(target)
        print(f">>> [{target}] Purging unneeded files")
        removed, freed = purge_tree(target, dry_run=args.dry_run)
        if not removed:
            print(">>> Nothing to remove (already slim).")
            continue
        verb = "would free" if args.dry_run else "freed"
        print(
            f">>> [{target}] Folder purged: {removed} entries, "
            f"{verb} {_human_size(freed)}."
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
