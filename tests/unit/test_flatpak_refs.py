"""Regression tests for scripts/generate_flatpak_refs.py.

A .flatpakref/.flatpakrepo that declares a CollectionID without a GPGKey makes
flatpak abort with:

    error: Collection ID requires GPG key to be provided

so the generator must never emit one without the other.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_flatpak_refs.py"
TEMPLATES_DIR = REPO_ROOT / "flatpak"
APP_ID = "bd.com.zihad.BengalDownloadManager"
COLLECTION_ID = "bd.com.zihad.Stable"

# Binary (non-armored) stand-in for an exported public key; the generator
# base64-encodes whatever bytes it finds, so no GPG keyring is required here.
FAKE_BINARY_KEY = b"\x99\x01\x0d\x04\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"


def _run(out_dir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out-dir",
            str(out_dir),
            "--app-id",
            APP_ID,
            "--templates-dir",
            str(TEMPLATES_DIR),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _read(out_dir: Path, name: str) -> str:
    return (out_dir / name).read_text(encoding="utf-8")


class TestCollectionIdRequiresGpgKey:
    def test_collection_id_dropped_without_gpg_key(self, tmp_path):
        result = _run(tmp_path, "--collection-id", COLLECTION_ID, "--branch", "stable")
        assert result.returncode == 0, result.stderr

        for name in (
            f"{APP_ID}.flatpakref",
            f"{APP_ID}.flatpakrepo",
            "bengal-download-manager.flatpakref",
            "tazihad.flatpakrepo",
        ):
            content = _read(tmp_path, name)
            assert "CollectionID=" not in content
            assert "GPGKey=" not in content

        # The operator must be told why the collection ID vanished.
        assert "CollectionID" in result.stderr
        assert "GPGKey" in result.stderr

    def test_collection_id_kept_with_binary_key_file(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / f"{APP_ID}.gpg").write_bytes(FAKE_BINARY_KEY)

        result = _run(
            tmp_path / "out",
            "--repo-dir",
            str(repo_dir),
            "--collection-id",
            COLLECTION_ID,
            "--branch",
            "stable",
        )
        assert result.returncode == 0, result.stderr

        for name in (f"{APP_ID}.flatpakref", f"{APP_ID}.flatpakrepo"):
            content = _read(tmp_path / "out", name)
            assert f"CollectionID={COLLECTION_ID}" in content
            assert "GPGKey=" in content
            # The key itself is embedded as base64, never as a file path.
            assert str(repo_dir) not in content

    def test_explicit_gpg_key_flag_is_used_when_keyring_has_key(self, tmp_path):
        """--gpg-key is honoured (exported via gpg); skip when no usable key exists."""
        export = subprocess.run(
            ["gpg", "--export", "BENGAL-FLATPAK-TEST"],
            capture_output=True,
            check=False,
        )
        result = _run(
            tmp_path,
            "--collection-id",
            COLLECTION_ID,
            "--branch",
            "stable",
            "--gpg-key",
            "BENGAL-FLATPAK-TEST",
        )
        assert result.returncode == 0, result.stderr

        content = _read(tmp_path, f"{APP_ID}.flatpakref")
        if export.stdout:
            assert f"CollectionID={COLLECTION_ID}" in content
            assert "GPGKey=" in content
        else:
            # No such key: the flag must degrade to an unsigned, key-less ref.
            assert "CollectionID=" not in content
            assert "GPGKey=" not in content


class TestRefContent:
    def test_ref_points_at_repo_and_stable_branch(self, tmp_path):
        result = _run(tmp_path, "--branch", "stable", "--collection-id", COLLECTION_ID)
        assert result.returncode == 0, result.stderr

        content = _read(tmp_path, "bengal-download-manager.flatpakref")
        assert f"Name={APP_ID}" in content
        assert "Branch=stable" in content
        assert "Url=https://zihad.com.bd/bengal-download-manager/repo/" in content
        assert "SuggestRemoteName=tazihad" in content
        assert "RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo" in content
        assert "IsRuntime=false" in content

    def test_only_versioned_skips_canonical_files(self, tmp_path):
        result = _run(
            tmp_path,
            "--branch",
            "stable",
            "--collection-id",
            COLLECTION_ID,
            "--version",
            "0.3.21",
            "--only-versioned",
        )
        assert result.returncode == 0, result.stderr

        assert (tmp_path / "bengal-download-manager-0.3.21.flatpakref").exists()
        assert not (tmp_path / f"{APP_ID}.flatpakref").exists()
        assert not (tmp_path / "bengal-download-manager.flatpakref").exists()

    def test_prerelease_versioned_ref_is_skipped(self, tmp_path):
        result = _run(
            tmp_path,
            "--branch",
            "stable",
            "--collection-id",
            COLLECTION_ID,
            "--version",
            "0.3.21-alpha.1",
            "--only-versioned",
        )
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "bengal-download-manager-0.3.21-alpha.1.flatpakref").exists()


@pytest.mark.parametrize(
    "expected",
    [f"{APP_ID}.flatpakrepo.in"],
)
def test_missing_template_is_a_hard_error(tmp_path, expected):
    """A missing template must fail loudly instead of silently shipping nothing."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out-dir",
            str(tmp_path),
            "--app-id",
            APP_ID,
            "--templates-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Template not found" in result.stderr
    assert expected in result.stderr
