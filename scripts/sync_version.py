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
import os
import re
import subprocess
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_FILE = os.path.join(ROOT_DIR, "VERSION")
SNAPCRAFT_FILE = os.path.join(ROOT_DIR, "snap", "snapcraft.yaml")
METAINFO_FILE = os.path.join(ROOT_DIR, "flatpak", "io.github.tazihad.bengal-download-manager.metainfo.xml")
VERSION_PY_FILE = os.path.join(ROOT_DIR, "src", "core", "version.py")


def read_root_version() -> str:
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
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


def get_highest_git_version() -> str:
    try:
        raw = subprocess.check_output(["git", "tag", "-l"], cwd=ROOT_DIR, text=True).split("\n")
        tags = [t.strip() for t in raw if t.strip()]
        parsed = []
        pattern = re.compile(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([a-zA-Z]+)\.([0-9]+))?$")
        for t in tags:
            m = pattern.match(t)
            if m:
                x, y, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
                is_stable = 1 if not m.group(4) else 0
                n = int(m.group(5)) if m.group(5) else 0
                parsed.append((x, y, z, is_stable, n, t))
        if parsed:
            parsed.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
            highest_tag = parsed[-1][5]
            return highest_tag.lstrip("v")
    except Exception:
        pass
    return ""


def bump_version(ver: str, bump_type: str) -> str:
    # Check if a higher tag already exists in Git
    highest_git = get_highest_git_version()
    if highest_git:
        v_tuple = parse_semver(ver)
        g_tuple = parse_semver(highest_git)
        # Compare (major, minor, patch)
        v_base = (v_tuple[0], v_tuple[1], v_tuple[2])
        g_base = (g_tuple[0], g_tuple[1], g_tuple[2])
        g_is_stable = (g_tuple[3] == "")
        v_is_stable = (v_tuple[3] == "")

        if g_base > v_base:
            ver = highest_git
        elif g_base == v_base and g_is_stable and not v_is_stable:
            # If stable g was already released, we must base on g
            ver = highest_git

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


def update_html_landing_page(ver: str):
    html_files = [
        os.path.join(ROOT_DIR, "index.html"),
        os.path.join(ROOT_DIR, "variant-plasma-desktop.html")
    ]
    clean_ver = ver.split("-")[0] if "-" in ver else ver
    for path in html_files:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Update version strings in release URLs and fallback data
        content = re.sub(r"bengal-download-manager-[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?", f"bengal-download-manager-{clean_ver}", content)
        content = re.sub(r"/releases/download/v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?", f"/releases/download/v{clean_ver}", content)
        content = re.sub(r'version:\s*"v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?', f'version: "v{clean_ver}', content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def sync_all(ver: str):
    print(f"[*] Synchronizing SSOT version: {ver}")
    update_root_version(ver)
    update_snapcraft(ver)
    update_metainfo(ver)
    update_html_landing_page(ver)
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
