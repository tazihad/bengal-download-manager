"""Unit tests for stale PyInstaller temp-directory cleanup."""

import os
import sys
import time

import pytest

from core.temp_cleanup import cleanup_stale_pyinstaller_dirs

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="PyInstaller temp cleanup only runs on Linux",
)

_OLD = time.time() - 2 * 60 * 60


def _make_bundle(root, name="_MEIabc123", version="0.3.22", mtime=_OLD):
    bundle = root / name
    assets = bundle / "assets"
    assets.mkdir(parents=True)
    (bundle / "VERSION").write_text(version + "\n", encoding="utf-8")
    (bundle / "base_library.zip").write_bytes(b"")
    (assets / "logo.svg").write_text("<svg/>", encoding="utf-8")
    os.utime(bundle, (mtime, mtime))
    return bundle


def test_removes_stale_bundle(tmp_path):
    bundle = _make_bundle(tmp_path)

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == [bundle]
    assert not bundle.exists()


def test_keeps_current_bundle(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert bundle.exists()


def test_keeps_directory_without_bundle_markers(tmp_path):
    foreign = tmp_path / "_MEIforeign12"
    foreign.mkdir()
    (foreign / "base_library.zip").write_bytes(b"")
    os.utime(foreign, (_OLD, _OLD))

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert foreign.exists()


def test_keeps_bundle_with_invalid_version(tmp_path):
    bundle = _make_bundle(tmp_path, name="_MEIbadver123", version="not-a-version")

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert bundle.exists()


def test_keeps_non_mei_directory(tmp_path):
    other = tmp_path / "not-a-pyinstaller-dir"
    other.mkdir()
    (other / "VERSION").write_text("0.3.22\n", encoding="utf-8")
    (other / "base_library.zip").write_bytes(b"")
    (other / "assets").mkdir()
    (other / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert other.exists()


def test_keeps_recent_bundle(tmp_path):
    bundle = _make_bundle(tmp_path, name="_MEIrecent123", mtime=time.time())

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert bundle.exists()


def test_keeps_bundle_used_by_running_process(tmp_path):
    bundle = _make_bundle(tmp_path)

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: True)

    assert removed == []
    assert bundle.exists()


def test_ignores_symlinked_bundle(tmp_path):
    target = _make_bundle(tmp_path, name="real-bundle")
    link = tmp_path / "_MEIlinked123"
    link.symlink_to(target, target_is_directory=True)

    removed = cleanup_stale_pyinstaller_dirs(tmp_path, in_use=lambda _path: False)

    assert removed == []
    assert link.is_symlink()
    assert target.exists()


def test_missing_temp_root_is_ignored(tmp_path):
    removed = cleanup_stale_pyinstaller_dirs(tmp_path / "missing")

    assert removed == []
