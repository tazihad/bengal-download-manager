import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock
import core.version as version_module


class TestVersionResolution(unittest.TestCase):
    """Tests for core.version resolution across environments and packaging targets."""

    def test_app_version_env_takes_precedence(self):
        with patch.dict(os.environ, {"APP_VERSION": "1.2.3", "SNAP_VERSION": "4.5.6"}, clear=True):
            ver = version_module._get_version()
            self.assertEqual(ver, "1.2.3")

    def test_bengal_dm_version_env(self):
        with patch.dict(os.environ, {"BENGAL_DM_VERSION": "2.0.1"}, clear=True):
            ver = version_module._get_version()
            self.assertEqual(ver, "2.0.1")

    def test_snap_version_env(self):
        with patch.dict(os.environ, {"SNAP_VERSION": "0.3.0"}, clear=True):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.3.0")

    def test_git_describe_exact_tag(self):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "v0.4.12\n"

        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run", return_value=mock_res):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.4.12")

    def test_git_describe_clean_tag(self):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "0.5.0\n"

        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run", return_value=mock_res):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.5.0")

    def test_root_version_file_reading(self):
        mock_res = MagicMock()
        mock_res.returncode = 128  # not an exact tag
        mock_res.stdout = ""

        with patch.dict(os.environ, {}, clear=True), patch("os.path.exists", return_value=True), patch("builtins.open", unittest.mock.mock_open(read_data="0.2.25\n")), patch("subprocess.run", return_value=mock_res):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.2.25")

    def test_fallback_when_git_fails(self):
        with patch.dict(os.environ, {}, clear=True), patch("os.path.exists", return_value=False), patch("subprocess.run", side_effect=Exception("No git")):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.2.20")

    def test_sync_version_bump_logic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_version", "scripts/sync_version.py")
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        with patch.object(sync_mod, "get_highest_git_version", return_value="0.2.20"):
            self.assertEqual(sync_mod.bump_version("0.2.20", "patch"), "0.2.21")
            self.assertEqual(sync_mod.bump_version("0.2.20", "minor"), "0.3.0")
            self.assertEqual(sync_mod.bump_version("0.2.20", "major"), "1.0.0")
            self.assertEqual(sync_mod.bump_version("0.2.20", "alpha"), "0.2.21-alpha.1")

        with patch.object(sync_mod, "get_highest_git_version", return_value="0.2.21-alpha.1"):
            self.assertEqual(sync_mod.bump_version("0.2.21-alpha.1", "alpha"), "0.2.21-alpha.2")
            self.assertEqual(sync_mod.bump_version("0.2.21-alpha.1", "patch"), "0.2.21")

    def test_sync_version_bump_advances_past_higher_git_tag(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_version", "scripts/sync_version.py")
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        with patch.object(sync_mod, "get_highest_git_version", return_value="0.2.21"):
            # Even if local VERSION was 0.2.19, bumping alpha advances past v0.2.21 to 0.2.22-alpha.1
            self.assertEqual(sync_mod.bump_version("0.2.19", "alpha"), "0.2.22-alpha.1")

    def test_sanitize_extension_version(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_version", "scripts/sync_version.py")
        sync_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_mod)

        self.assertEqual(sync_mod.sanitize_extension_version("0.2.20"), "0.2.20")
        self.assertEqual(sync_mod.sanitize_extension_version("0.2.20-alpha.1"), "0.2.20.1")
        self.assertEqual(sync_mod.sanitize_extension_version("0.2.20-alpha.12"), "0.2.20.12")
