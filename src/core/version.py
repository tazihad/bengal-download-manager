import os
import re
import subprocess
import sys

def _get_version():
    if os.environ.get("APP_VERSION"):
        return os.environ.get("APP_VERSION")
    if os.environ.get("BENGAL_DM_VERSION"):
        return os.environ.get("BENGAL_DM_VERSION")
    if os.environ.get("SNAP_VERSION"):
        return os.environ.get("SNAP_VERSION")

    # 1. Check PyInstaller bundled asset (sys._MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled_ver = os.path.join(meipass, "VERSION")
        if os.path.exists(bundled_ver):
            try:
                with open(bundled_ver, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return v
            except Exception:
                pass

    # 2. Check installed Flatpak / system AppStream metainfo
    metainfo_paths = [
        "/app/share/metainfo/bd.com.zihad.BengalDownloadManager.metainfo.xml",
        "/app/share/bengal-download-manager/VERSION",
        "/usr/share/metainfo/bd.com.zihad.BengalDownloadManager.metainfo.xml",
        "/usr/share/bengal-download-manager/VERSION",
    ]
    for mpath in metainfo_paths:
        if os.path.exists(mpath):
            try:
                if mpath.endswith(".xml"):
                    with open(mpath, "r", encoding="utf-8") as f:
                        m = re.search(r'<release\s+[^>]*version=["\']([^"\']+)["\']', f.read())
                        if m and m.group(1):
                            return m.group(1).lstrip("v")
                else:
                    with open(mpath, "r", encoding="utf-8") as f:
                        v = f.read().strip()
                        if v:
                            return v
            except Exception:
                pass

    # 3. Check repository / unbundled root VERSION file
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        version_file = os.path.join(root_dir, "VERSION")
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass

    # 4. Check git tags if running inside git clone
    try:
        git_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        # Exact tag (e.g. checked out release tag v0.3.0)
        res = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=git_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1
        )
        if res.returncode == 0 and res.stdout.strip():
            ver = res.stdout.strip()
            return ver[1:] if ver.startswith("v") else ver
    except Exception:
        pass

    # 5. If on development/main branch with untagged commits, calculate upcoming release version
    try:
        git_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        from core.utils import determine_next_release_tag
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1
        )
        branch = branch_res.stdout.strip() if branch_res.returncode == 0 else "main"
        ref = f"refs/heads/{branch}" if branch else "refs/heads/main"
        _, ver = determine_next_release_tag(ref=ref)
        if ver:
            return ver
    except Exception:
        pass

    # 6. Fallback to git describe tag
    try:
        git_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        res = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=git_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1
        )
        if res.returncode == 0 and res.stdout.strip():
            ver = res.stdout.strip()
            if ver.startswith("v"):
                ver = ver[1:]
            if "-" in ver:
                ver = ver.split("-")[0]
            return ver
    except Exception:
        pass

    return "0.3.3-alpha.1"

VERSION = _get_version()

try:
    from core.build_info import get_package_type, get_verified_source_info
except ImportError:
    pass
