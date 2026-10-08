#!/usr/bin/env python3
"""
generate_flatpak_refs.py
Generates Flathub-standard .flatpakrepo and .flatpakref files with embedded base64 GPG keys,
with channel/branch isolation (stable vs alpha/beta) and clean versioned asset naming.
"""

import argparse
import base64
import os
import re
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


def detect_branch(version_str: str, branch_arg: str = "") -> str:
    """Determine the channel branch (stable, alpha, beta, rc)."""
    if branch_arg:
        return branch_arg
    v_lower = version_str.lower()
    if "alpha" in v_lower:
        return "alpha"
    if "beta" in v_lower:
        return "beta"
    if "rc" in v_lower:
        return "rc"
    if "dev" in v_lower:
        return "dev"
    return "stable"


def main():
    parser = argparse.ArgumentParser(description="Generate Flathub-standard Flatpak repo and ref files.")
    parser.add_argument("--repo-dir", default="repo", help="Path to OSTree repository directory")
    parser.add_argument("--out-dir", default=".", help="Output directory for generated files")
    parser.add_argument("--app-id", default="bd.com.zihad.BengalDownloadManager", help="Flatpak Application ID")
    parser.add_argument("--pages-url", default="https://tazihad.github.io/bengal-download-manager", help="Base Pages URL")
    parser.add_argument("--gpg-key", default="", help="GPG Key ID")
    parser.add_argument("--gpg-file", default="", help="Path to exported GPG public key file")
    parser.add_argument("--version", default="", help="Release version for versioned assets")
    parser.add_argument("--branch", default="", help="Channel branch (stable, alpha, beta, rc)")
    parser.add_argument("--collection-id", default="", help="OSTree Collection ID (defaults to bd.com.zihad.<Branch>)")
    parser.add_argument("--only-versioned", action="store_true", help="Only generate versioned asset files")
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

    # Determine channel branch for track isolation
    branch = detect_branch(args.version, args.branch)
    collection_id = args.collection_id or f"bd.com.zihad.{branch.capitalize()}"
    collection_entry = f"CollectionID={collection_id}" if collection_id else ""

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
            .replace("@BRANCH@", branch)
            .replace("@GPG_KEY_ENTRY@", gpg_entry)
            .replace("@COLLECTION_ID_ENTRY@", collection_entry)
        )

    rendered_repo = substitute(repo_template)
    rendered_ref = substitute(ref_template)

    # Clean up empty lines from empty entries
    rendered_repo = "\n".join(line for line in rendered_repo.splitlines() if line.strip()) + "\n"
    rendered_ref = "\n".join(line for line in rendered_ref.splitlines() if line.strip()) + "\n"

    version = args.version.lstrip("v")

    if not args.only_versioned:
        target_repo_file = out_dir / f"{args.app_id}.flatpakrepo"
        target_ref_file = out_dir / f"{args.app_id}.flatpakref"
        web_repo_file = out_dir / "tazihad.flatpakrepo"
        web_ref_file = out_dir / "bengal-download-manager.flatpakref"

        target_repo_file.write_text(rendered_repo, encoding="utf-8")
        target_ref_file.write_text(rendered_ref, encoding="utf-8")
        web_repo_file.write_text(rendered_repo, encoding="utf-8")
        web_ref_file.write_text(rendered_ref, encoding="utf-8")

        print(f"✓ Generated canonical {target_repo_file} (Branch: {branch})")
        print(f"✓ Generated canonical {target_ref_file} (Branch: {branch})")
        print(f"✓ Generated web repo: {web_repo_file}")
        print(f"✓ Generated web ref: {web_ref_file}")

    # Generate versioned release assets matching other release binaries
    if version:
        v_ref = out_dir / f"bengal-download-manager-{version}.flatpakref"
        v_ref.write_text(rendered_ref, encoding="utf-8")
        print(f"✓ Generated versioned asset: {v_ref}")

    # Mirror canonical files into repo_dir if different from out_dir
    if repo_dir.exists() and repo_dir != out_dir and not args.only_versioned:
        (repo_dir / f"{args.app_id}.flatpakrepo").write_text(rendered_repo, encoding="utf-8")
        (repo_dir / f"{args.app_id}.flatpakref").write_text(rendered_ref, encoding="utf-8")
        (repo_dir / "tazihad.flatpakrepo").write_text(rendered_repo, encoding="utf-8")
        (repo_dir / "bengal-download-manager.flatpakref").write_text(rendered_ref, encoding="utf-8")
        print(f"✓ Mirrored into {repo_dir}")


if __name__ == "__main__":
    main()
