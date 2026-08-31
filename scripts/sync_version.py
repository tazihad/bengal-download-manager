#!/usr/bin/env python3
"""
Single Source of Truth (SSOT) Version Synchronizer for Bengal Download Manager.
Authoritative source: Root `VERSION` file.

Usage:
  python3 scripts/sync_version.py --check
  python3 scripts/sync_version.py --set 0.2.20
  python3 scripts/sync_version.py --bump patch [--tag] [--commit]
  python3 scripts/sync_version.py --bump minor
  python3 scripts/sync_version.py --bump major
  python3 scripts/sync_version.py --bump alpha
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_FILE = os.path.join(ROOT_DIR, "VERSION")
SNAPCRAFT_FILE = os.path.join(ROOT_DIR, "snap", "snapcraft.yaml")
METAINFO_FILE = os.path.join(ROOT_DIR, "flatpak", "io.github.tazihad.bengal-download-manager.metainfo.xml")
VERSION_PY_FILE = os.path.join(ROOT_DIR, "src", "core", "version.py")
EXTENSION_MANIFEST_FILE = os.path.join(ROOT_DIR, "extension", "manifest.json")


def read_root_version() -> str:
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "0.2.20"


def sanitize_extension_version(ver: str) -> str:
    """Extension manifest requires 1-4 dot-separated integers (e.g. 0.2.20 or 0.2.20.1)."""
    # If ver is like 0.2.20-alpha.1 -> 0.2.20.1
    m = re.match(r"^([0-9]+(?:\.[0-9]+){1,3})(?:-[a-zA-Z]+\.?([0-9]+))?", ver)
    if m:
        base = m.group(1)
        suffix_num = m.group(2)
        if suffix_num:
            parts = base.split(".")
            if len(parts) < 4:
                return f"{base}.{suffix_num}"
        return base
    return "0.2.20"


def parse_semver(ver: str) -> tuple[int, int, int, str, int]:
    m = re.match(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([a-zA-Z]+)\.([0-9]+))?$", ver)
    if not m:
        return 0, 2, 20, "", 0
    major = int(m.group(1))
    minor = int(m.group(2))
    patch_num = int(m.group(3))
    prerelease = m.group(4) or ""
    pre_num = int(m.group(5)) if m.group(5) else 0
    return major, minor, patch_num, prerelease, pre_num


def bump_version(ver: str, bump_type: str) -> str:
    major, minor, patch_num, prerelease, pre_num = parse_semver(ver)
    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        if prerelease:
            return f"{major}.{minor}.{patch_num}"
        return f"{major}.{minor}.{patch_num + 1}"
    elif bump_type == "alpha":
        if prerelease == "alpha":
            return f"{major}.{minor}.{patch_num}-alpha.{pre_num + 1}"
        return f"{major}.{minor}.{patch_num + 1}-alpha.1"
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")


def update_root_version(ver: str):
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(f"{ver}\n")


def update_snapcraft(ver: str):
    if not os.path.exists(SNAPCRAFT_FILE):
        return
    with open(SNAPCRAFT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"version:\s*['\"][^'\"]+['\"]", f"version: '{ver}'", content)
    with open(SNAPCRAFT_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def update_metainfo(ver: str):
    if not os.path.exists(METAINFO_FILE):
        return
    today = datetime.date.today().isoformat()
    clean_ver = ver.split("-")[0] if "-" in ver else ver
    with open(METAINFO_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    new_release = f"<releases>\n    <release version=\"{clean_ver}\" date=\"{today}\"/>\n  </releases>"
    content = re.sub(r"<releases>.*?</releases>", new_release, content, flags=re.DOTALL)
    with open(METAINFO_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def update_extension_manifest(ver: str):
    if not os.path.exists(EXTENSION_MANIFEST_FILE):
        return
    ext_ver = sanitize_extension_version(ver)
    with open(EXTENSION_MANIFEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = ext_ver
    with open(EXTENSION_MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def sync_all(ver: str):
    print(f"[*] Synchronizing SSOT version: {ver}")
    update_root_version(ver)
    update_snapcraft(ver)
    update_metainfo(ver)
    update_extension_manifest(ver)
    print("[✓] All manifests synchronized successfully.")


def check_consistency() -> bool:
    root_ver = read_root_version()
    errors = []

    # 1. Snapcraft check
    if os.path.exists(SNAPCRAFT_FILE):
        with open(SNAPCRAFT_FILE, "r", encoding="utf-8") as f:
            m = re.search(r"version:\s*['\"]([^'\"]+)['\"]", f.read())
            if not m or m.group(1) != root_ver:
                found = m.group(1) if m else "None"
                errors.append(f"snapcraft.yaml version ({found}) != VERSION ({root_ver})")

    # 2. Metainfo check
    if os.path.exists(METAINFO_FILE):
        clean_root = root_ver.split("-")[0]
        with open(METAINFO_FILE, "r", encoding="utf-8") as f:
            m = re.search(r'<release\s+version="([^"]+)"', f.read())
            if not m or m.group(1) != clean_root:
                found = m.group(1) if m else "None"
                errors.append(f"metainfo.xml version ({found}) != base VERSION ({clean_root})")

    # 3. Extension check
    if os.path.exists(EXTENSION_MANIFEST_FILE):
        ext_ver = sanitize_extension_version(root_ver)
        with open(EXTENSION_MANIFEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("version") != ext_ver:
                errors.append(f"extension manifest version ({data.get('version')}) != ({ext_ver})")

    if errors:
        print("[!] Version consistency check FAILED:")
        for err in errors:
            print(f"  - {err}")
        return False
    print(f"[✓] All manifests match canonical VERSION: {root_ver}")
    return True


def create_git_tag_and_commit(ver: str):
    tag = f"v{ver}"
    print(f"[*] Creating Git commit and tag: {tag}")
    files_to_stage = [
        VERSION_FILE,
        SNAPCRAFT_FILE,
        METAINFO_FILE,
        EXTENSION_MANIFEST_FILE,
    ]
    staged = [f for f in files_to_stage if os.path.exists(f)]
    subprocess.run(["git", "add"] + staged, check=True, cwd=ROOT_DIR)
    subprocess.run(["git", "commit", "-m", f"chore(release): bump version to {ver}"], check=True, cwd=ROOT_DIR)
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], check=True, cwd=ROOT_DIR)
    print(f"[✓] Created commit and tag {tag}")
    print(f"To push: git push origin HEAD --tags")


def main():
    parser = argparse.ArgumentParser(description="Single Source of Truth Version Synchronizer")
    parser.add_argument("--check", action="store_true", help="Check manifest consistency against VERSION")
    parser.add_argument("--set", type=str, metavar="VER", help="Set specific version string across all manifests")
    parser.add_argument("--bump", choices=["patch", "minor", "major", "alpha"], help="Bump semantic version")
    parser.add_argument("--tag", action="store_true", help="Create Git tag after bump/set")
    parser.add_argument("--commit", action="store_true", help="Create Git commit after bump/set")

    args = parser.parse_args()

    if args.check:
        success = check_consistency()
        sys.exit(0 if success else 1)

    new_ver = None
    if args.set:
        new_ver = args.set.strip().lstrip("v")
    elif args.bump:
        curr_ver = read_root_version()
        new_ver = bump_version(curr_ver, args.bump)

    if new_ver:
        sync_all(new_ver)
        if args.commit or args.tag:
            create_git_tag_and_commit(new_ver)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
