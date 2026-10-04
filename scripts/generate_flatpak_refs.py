#!/usr/bin/env python3
"""
generate_flatpak_refs.py
Generates Flathub-standard .flatpakrepo and .flatpakref files with embedded base64 GPG keys,
including versioned aliases matching other release assets.
"""

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path


def get_gpg_base64(gpg_key: str = None, gpg_file: str = None) -> str:
    """Extract and base64-encode a GPG public key."""
    if gpg_file and os.path.exists(gpg_file):
        with open(gpg_file, "rb") as f:
            raw_bytes = f.read()
            return base64.b64encode(raw_bytes).decode("ascii")

    if gpg_key:
        try:
            # Export raw binary public key from GPG keyring
            res = subprocess.run(
                ["gpg", "--export", gpg_key],
                capture_output=True,
                check=True
            )
            if res.stdout:
                return base64.b64encode(res.stdout).decode("ascii")
        except Exception as e:
            print(f"Warning: Could not export GPG key {gpg_key}: {e}", file=sys.stderr)

    return ""


def main():
    parser = argparse.ArgumentParser(description="Generate Flathub-standard Flatpak repo and ref files.")
    parser.add_argument("--repo-dir", default="repo", help="Path to OSTree repository directory")
    parser.add_argument("--out-dir", default=".", help="Output directory for generated files")
    parser.add_argument("--app-id", default="bd.com.zihad.BengalDownloadManager", help="Flatpak Application ID")
    parser.add_argument("--pages-url", default="https://tazihad.github.io/bengal-download-manager", help="Base Pages URL")
    parser.add_argument("--gpg-key", default="", help="GPG Key ID")
    parser.add_argument("--gpg-file", default="", help="Path to exported GPG public key file")
    parser.add_argument("--version", default="", help="Release version for versioned assets")
    parser.add_argument("--templates-dir", default="flatpak", help="Path to directory containing .in templates")

    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    templates_dir = Path(args.templates_dir).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)

    pages_url = args.pages_url.rstrip("/")
    repo_url = f"{pages_url}/repo/"
    homepage_url = f"{pages_url}/"
    icon_url = f"{pages_url}/assets/icons/256x256.png"

    # Look for GPG key file if not explicitly specified
    gpg_file = args.gpg_file
    if not gpg_file:
        candidate_gpg = repo_dir / f"{args.app_id}.gpg"
        candidate_legacy = repo_dir / "bengal.gpg"
        if candidate_gpg.exists():
            gpg_file = str(candidate_gpg)
        elif candidate_legacy.exists():
            gpg_file = str(candidate_legacy)

    gpg_b64 = get_gpg_base64(args.gpg_key, gpg_file)
    gpg_entry = f"GPGKey={gpg_b64}" if gpg_b64 else ""

    repo_template_path = templates_dir / f"{args.app_id}.flatpakrepo.in"
    ref_template_path = templates_dir / f"{args.app_id}.flatpakref.in"

    if not repo_template_path.exists():
        print(f"Error: Template not found at {repo_template_path}", file=sys.stderr)
        sys.exit(1)
    if not ref_template_path.exists():
        print(f"Error: Template not found at {ref_template_path}", file=sys.stderr)
        sys.exit(1)

    repo_template = repo_template_path.read_text(encoding="utf-8")
    ref_template = ref_template_path.read_text(encoding="utf-8")

    def substitute(content: str) -> str:
        return (
            content.replace("@REPO_URL@", repo_url)
            .replace("@HOMEPAGE_URL@", homepage_url)
            .replace("@ICON_URL@", icon_url)
            .replace("@GPG_KEY_ENTRY@", gpg_entry)
        )

    rendered_repo = substitute(repo_template)
    rendered_ref = substitute(ref_template)

    # Clean up empty lines from empty GPG_KEY_ENTRY
    rendered_repo = "\n".join(line for line in rendered_repo.splitlines() if line.strip()) + "\n"
    rendered_ref = "\n".join(line for line in rendered_ref.splitlines() if line.strip()) + "\n"

    target_repo_file = out_dir / f"{args.app_id}.flatpakrepo"
    target_ref_file = out_dir / f"{args.app_id}.flatpakref"

    target_repo_file.write_text(rendered_repo, encoding="utf-8")
    target_ref_file.write_text(rendered_ref, encoding="utf-8")

    print(f"✓ Generated {target_repo_file}")
    print(f"✓ Generated {target_ref_file}")

    # Also generate versioned assets if version is provided
    version = args.version.lstrip("v")
    if version:
        v_repo_bdm = out_dir / f"bengal-download-manager-{version}.flatpakrepo"
        v_ref_bdm = out_dir / f"bengal-download-manager-{version}.flatpakref"
        v_repo_id = out_dir / f"{args.app_id}-{version}.flatpakrepo"
        v_ref_id = out_dir / f"{args.app_id}-{version}.flatpakref"

        v_repo_bdm.write_text(rendered_repo, encoding="utf-8")
        v_ref_bdm.write_text(rendered_ref, encoding="utf-8")
        v_repo_id.write_text(rendered_repo, encoding="utf-8")
        v_ref_id.write_text(rendered_ref, encoding="utf-8")

        print(f"✓ Generated versioned asset: {v_repo_bdm}")
        print(f"✓ Generated versioned asset: {v_ref_bdm}")

    # Also place a copy directly inside repo-dir if different from out_dir
    if repo_dir.exists() and repo_dir != out_dir:
        (repo_dir / f"{args.app_id}.flatpakrepo").write_text(rendered_repo, encoding="utf-8")
        (repo_dir / f"{args.app_id}.flatpakref").write_text(rendered_ref, encoding="utf-8")
        print(f"✓ Mirrored into {repo_dir}")


if __name__ == "__main__":
    main()
