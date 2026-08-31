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

    def test_git_describe_parsing_with_prefix_and_suffix(self):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "v0.4.12-10-gabcdef\n"

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

    def test_fallback_when_git_fails(self):
        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run", side_effect=Exception("No git")):
            ver = version_module._get_version()
            self.assertEqual(ver, "0.2.13")
