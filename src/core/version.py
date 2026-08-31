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
    return "0.2.13"

VERSION = _get_version()
