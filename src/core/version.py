import os
import subprocess

def _get_version():
    if os.environ.get("APP_VERSION"):
        return os.environ.get("APP_VERSION")
    if os.environ.get("BENGAL_DM_VERSION"):
        return os.environ.get("BENGAL_DM_VERSION")
    if os.environ.get("SNAP_VERSION"):
        return os.environ.get("SNAP_VERSION")
    try:
        git_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        # 1. If HEAD is on an exact tag (e.g. checked out release tag v0.2.19)
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

        # 2. If on development/main branch with untagged commits, calculate upcoming release version
        try:
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

        # 3. Fallback to git describe tag
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
    return "0.2.20"

VERSION = _get_version()
