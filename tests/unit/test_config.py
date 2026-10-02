"""Unit tests for core.config."""

import os
import json
import pytest

from core.config import get_default_categories, load_category_config, save_category_config, _normalize_snap_path


class TestGetDefaultCategories:
    def test_returns_dict(self):
        result = get_default_categories()
        assert isinstance(result, dict)

    def test_contains_general(self):
        assert "General" in get_default_categories()

    def test_contains_standard_categories(self):
        cats = get_default_categories()
        for expected in ["General", "Compressed", "Documents", "Music", "Programs", "Video"]:
            assert expected in cats

    def test_each_category_has_path_and_extensions(self):
        for name, cfg in get_default_categories().items():
            assert "path" in cfg, f"{name} missing path"
            assert "extensions" in cfg, f"{name} missing extensions"


class TestLoadCategoryConfig:
    def test_returns_dict_with_categories(self):
        cfg = load_category_config()
        assert isinstance(cfg, dict)
        assert "categories" in cfg

    def test_defaults_merged_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
        cfg = load_category_config()
        assert "General" in cfg["categories"]
        assert "Compressed" in cfg["categories"]

    def test_temp_dir_key_exists(self):
        cfg = load_category_config()
        assert "temp_dir" in cfg


class TestSaveCategoryConfig:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        data = {"categories": {"General": {"path": "/tmp", "extensions": "zip"}}, "temp_dir": "/tmp/cache"}
        save_category_config(data)
        path = os.path.join(str(tmp_path), "config", "bengal-download-manager", "categories.json")
        if not os.path.exists(path):
            from core.utils import get_config_dir
            path = os.path.join(get_config_dir(), "categories.json")
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["categories"]["General"]["path"] == "/tmp"


class TestNormalizeSnapPath:
    def test_none_passthrough(self):
        assert _normalize_snap_path(None) is None

    def test_empty_passthrough(self):
        assert _normalize_snap_path("") == ""

    def test_non_string_passthrough(self):
        assert _normalize_snap_path(123) == 123

    def test_regular_path_unchanged(self):
        p = "/home/user/Downloads/file.zip"
        assert _normalize_snap_path(p) == p

    def test_snap_user_data_remap(self, monkeypatch):
        monkeypatch.setenv("SNAP_USER_DATA", "/home/u/snap/app/100")
        monkeypatch.setenv("SNAP_REAL_HOME", "/home/u")
        result = _normalize_snap_path("/home/u/snap/app/100/Downloads/file.zip")
        assert result == "/home/u/Downloads/file.zip"

    def test_snap_pattern_remap(self, monkeypatch):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("SNAP_REAL_HOME", raising=False)
        result = _normalize_snap_path("/home/user/snap/bengal/53/Downloads/file.zip")
        assert "/snap/" not in result
