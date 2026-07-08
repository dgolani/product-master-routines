"""Git-backed state, shared by every use case.

The cloud routine runs from an ephemeral fresh clone, so state must live in the repo.
The routine's egress proxy BLOCKS the GitHub REST Contents API (PUT -> 403) but ALLOWS
`git push`. So we read state from the working tree (the fresh clone already reflects the
latest committed state) and write it back with git add/commit/push to `main`.

Lifted from the proven ounass_slots.py persistence layer. No GITHUB_TOKEN needed — push
uses the routine's own git credentials. Outside a git checkout (local dev) writes no-op.
"""
import json
import subprocess
from datetime import datetime


def _git(args):
    try:
        return subprocess.run(["git"] + args, capture_output=True, text=True, timeout=60)
    except Exception:
        class _R:
            returncode = 1
            stdout = ""
            stderr = ""
        return _R()


def _in_git_repo():
    r = _git(["rev-parse", "--is-inside-work-tree"])
    return r.returncode == 0 and r.stdout.strip() == "true"


def read_json(path):
    """Read a JSON state file from the working tree. {} if absent/unreadable."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def write_json(path, obj, message):
    """Persist a JSON state file via git commit + push to main (REST writes are proxy-blocked;
    git push is allowed). No-ops safely outside a git checkout. Returns True on success/no-op."""
    if not _in_git_repo():
        return False
    try:
        with open(path, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception:
        return False
    if not _git(["config", "user.email"]).stdout.strip():
        _git(["config", "user.email", "product-routines@ounass.local"])
        _git(["config", "user.name", "product-master-routines"])
    _git(["add", path])
    if _git(["diff", "--cached", "--quiet"]).returncode == 0:
        return True  # nothing changed
    if _git(["commit", "-m", message]).returncode != 0:
        return False
    # Always land state on main: the routine works on its own branch, but the next run's
    # fresh clone reads main — so push straight to main.
    if _git(["push", "origin", "HEAD:main"]).returncode == 0:
        return True
    _git(["fetch", "origin", "main"])
    if _git(["rebase", "FETCH_HEAD"]).returncode != 0:
        _git(["rebase", "--abort"])
        return False
    return _git(["push", "origin", "HEAD:main"]).returncode == 0


def state_exists(path):
    """True if the state file is present (used to detect a cold-start first run)."""
    try:
        with open(path):
            return True
    except OSError:
        return False


def load_sent(path):
    """Return the set of already-alerted keys from a {"sent": [...]} state file."""
    return set(read_json(path).get("sent", []))


def save_sent(path, keys, message):
    """Persist the set of alerted keys (sorted for a stable diff) via git."""
    obj = {"updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
           "sent": sorted(keys)}
    return write_json(path, obj, message)
