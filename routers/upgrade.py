import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from config import templates
from paths import DATA_DIR
from routers.backup import _load_config, restore_zip_bytes, save_backup_zip

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parent.parent
# Docker images exclude .git (see .dockerignore) and a PyInstaller desktop bundle never has one
# at all — this self-upgrade mechanism (git fetch/merge + systemd restart) only makes sense for
# a real git checkout. Computed once at import time; drives graceful degradation below rather
# than letting git commands error against a missing .git.
GIT_AVAILABLE = (REPO_ROOT / ".git").is_dir()
UPGRADE_STATE_PATH = Path(DATA_DIR) / "data" / "upgrade_state.json"
BRANCH = "main"


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


def _require_git():
    if not GIT_AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail="Self-upgrade isn't available for this install type — no local git checkout "
                   "found. Update via your platform's normal mechanism instead (a new Docker "
                   "image tag, or a new desktop installer release).",
        )


def _run(cmd: list, timeout: int = 60) -> dict:
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "cmd": " ".join(cmd),
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": " ".join(cmd), "ok": False, "stdout": "", "stderr": "timed out"}
    except FileNotFoundError as e:
        return {"cmd": " ".join(cmd), "ok": False, "stdout": "", "stderr": str(e)}


def _git(*args, timeout: int = 60) -> dict:
    return _run(["git", *args], timeout=timeout)


def _commit_info(rev: str) -> dict | None:
    r = _git("log", "-1", "--format=%h|%cI|%s", rev)
    if not r["ok"] or not r["stdout"]:
        return None
    short_hash, iso_date, subject = r["stdout"].split("|", 2)
    tag = _git("describe", "--tags", "--exact-match", rev)
    return {
        "hash": short_hash,
        "date": iso_date,
        "subject": subject,
        "tag": tag["stdout"] if tag["ok"] else None,
    }


def _is_dirty() -> bool:
    r = _git("status", "--porcelain")
    return bool(r["stdout"])


def _pip_install() -> dict:
    return _run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"], timeout=300)


def _load_upgrade_state() -> dict | None:
    if not UPGRADE_STATE_PATH.exists():
        return None
    try:
        return json.loads(UPGRADE_STATE_PATH.read_text())
    except Exception:
        return None


def _save_upgrade_state(state: dict):
    UPGRADE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPGRADE_STATE_PATH.write_text(json.dumps(state, indent=2))


def _running_under_systemd() -> bool:
    # systemd sets INVOCATION_ID for every unit it starts (inventory.service in prod); a plain
    # `uvicorn ... --reload` launched from a dev shell never has it. This is the load-bearing
    # signal for which restart strategy is safe to use — see _schedule_restart below.
    return bool(os.environ.get("INVOCATION_ID"))


def _schedule_restart() -> str:
    """Trigger a restart appropriate to how the app is actually running, and report which
    strategy was used so the caller/UI can say something accurate.

    - Under systemd (prod): a clean self-exit. inventory.service has Restart=on-failure /
      RestartSec=5, so exiting with a non-zero code is all that's needed — no elevated
      permissions (e.g. calling `systemctl` directly) required from the app itself.
    - Under `--reload` (dev): self-exiting is NOT safe here — uvicorn's reloader supervises a
      *subprocess* and isn't guaranteed to respawn it on an arbitrary exit the way systemd's
      Restart=on-failure does, so it could just leave the dev server dead. Instead, nudge the
      file watcher (git pull already changed tracked .py files, which it would pick up on its
      own shortly anyway) so it reloads the worker gracefully on its own, same as any other
      code change during development.

    Both run on a short delay, off-thread, so the HTTP response for this request finishes
    sending before anything happens.
    """
    if _running_under_systemd():
        def _delayed_exit():
            time.sleep(1.5)
            os._exit(1)
        threading.Thread(target=_delayed_exit, daemon=True).start()
        return "systemd"
    else:
        def _delayed_touch():
            time.sleep(1.5)
            (REPO_ROOT / "main.py").touch()
        threading.Thread(target=_delayed_touch, daemon=True).start()
        return "dev-reload"


# ── Page ─────────────────────────────────────────────────────────────────────

@router.get("/admin/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("admin-upgrade.html", {
        "request": request,
        "user": request.state.user,
        "git_available": GIT_AVAILABLE,
    })


# ── Check for updates ────────────────────────────────────────────────────────

@router.get("/admin/upgrade/check")
def upgrade_check(request: Request):
    _require_admin(request)
    _require_git()

    current = _commit_info("HEAD")
    fetch = _git("fetch", "origin", BRANCH, timeout=30)
    if not fetch["ok"]:
        return {
            "ok": False,
            "error": f"git fetch failed: {fetch['stderr'] or 'no network / no access to origin'}",
            "current": current,
            "dirty": _is_dirty(),
            "rollback": _rollback_summary(),
        }

    latest = _commit_info(f"origin/{BRANCH}")
    behind = _git("log", f"HEAD..origin/{BRANCH}", "--format=%h %s")
    commits_behind = behind["stdout"].splitlines() if behind["ok"] and behind["stdout"] else []

    return {
        "ok": True,
        "current": current,
        "latest": latest,
        "up_to_date": current is not None and latest is not None and current["hash"] == latest["hash"],
        "commits_behind": commits_behind,
        "dirty": _is_dirty(),
        "rollback": _rollback_summary(),
    }


def _rollback_summary() -> dict | None:
    state = _load_upgrade_state()
    if not state:
        return None
    resolves = _git("cat-file", "-e", state["previous_commit"])
    backup_exists = Path(state["backup_file"]).exists() if state.get("backup_file") else False
    return {
        **state,
        "available": resolves["ok"] and backup_exists,
    }


# ── Run upgrade ──────────────────────────────────────────────────────────────

@router.post("/admin/upgrade/run")
def upgrade_run(request: Request):
    _require_admin(request)
    _require_git()
    log = []

    if _is_dirty():
        raise HTTPException(400, "Working tree has local changes on this server — resolve or discard them before upgrading (never auto-discarded).")

    before = _commit_info("HEAD")

    fetch = _git("fetch", "origin", BRANCH, timeout=30)
    log.append(fetch)
    if not fetch["ok"]:
        raise HTTPException(502, f"git fetch failed: {fetch['stderr'] or 'no network / no access to origin'}")

    latest = _commit_info(f"origin/{BRANCH}")
    if latest and before and latest["hash"] == before["hash"]:
        return {"ok": True, "up_to_date": True, "log": log, "current": before}

    # Backup BEFORE touching any code, so a rollback always has something to restore to.
    cfg = _load_config()
    try:
        backup_path = save_backup_zip(cfg)
    except Exception as e:
        raise HTTPException(500, f"Pre-upgrade backup failed, aborting upgrade: {e}")
    log.append({"cmd": "backup", "ok": True, "stdout": str(backup_path), "stderr": ""})

    merge = _git("merge", "--ff-only", f"origin/{BRANCH}", timeout=30)
    log.append(merge)
    if not merge["ok"]:
        raise HTTPException(500, f"git merge --ff-only failed (backup was still taken at {backup_path}): {merge['stderr']}")

    submodule = _run(["git", "submodule", "update", "--init", "--recursive"], timeout=60)
    log.append(submodule)  # best-effort — private submodule may not be configured on this host

    pip = _pip_install()
    log.append(pip)
    if not pip["ok"]:
        raise HTTPException(500, f"pip install failed after code update — code is on the new version but dependencies may be stale. Use Rollback. Details: {pip['stderr']}")

    after = _commit_info("HEAD")
    _save_upgrade_state({
        "previous_commit": before["hash"] if before else None,
        "new_commit": after["hash"] if after else None,
        "backup_file": str(backup_path),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })

    restart_mode = _schedule_restart()
    return {"ok": True, "up_to_date": False, "log": log, "from": before, "to": after, "restarting": True, "restart_mode": restart_mode}


# ── Rollback to the state before the last upgrade ───────────────────────────

@router.post("/admin/upgrade/rollback")
def upgrade_rollback(request: Request):
    _require_admin(request)
    _require_git()
    state = _load_upgrade_state()
    if not state:
        raise HTTPException(400, "No upgrade to roll back — nothing recorded.")

    if _is_dirty():
        raise HTTPException(400, "Working tree has local changes on this server — resolve or discard them before rolling back (never auto-discarded).")

    resolves = _git("cat-file", "-e", state["previous_commit"])
    if not resolves["ok"]:
        raise HTTPException(400, "Previous commit no longer exists locally — cannot roll back code automatically.")

    backup_file = Path(state["backup_file"]) if state.get("backup_file") else None
    if not backup_file or not backup_file.exists():
        raise HTTPException(400, "Pre-upgrade backup file is missing — cannot safely roll back the database.")

    log = []
    reset = _git("reset", "--hard", state["previous_commit"], timeout=30)
    log.append(reset)
    if not reset["ok"]:
        raise HTTPException(500, f"git reset --hard failed: {reset['stderr']}")

    submodule = _run(["git", "submodule", "update", "--init", "--recursive"], timeout=60)
    log.append(submodule)  # best-effort

    pip = _pip_install()
    log.append(pip)
    if not pip["ok"]:
        raise HTTPException(500, f"Code was rolled back but pip install failed: {pip['stderr']}")

    restore_result = restore_zip_bytes(backup_file.read_bytes())
    log.append({"cmd": "restore_zip_bytes", "ok": True, "stdout": json.dumps(restore_result), "stderr": ""})

    UPGRADE_STATE_PATH.unlink(missing_ok=True)

    restart_mode = _schedule_restart()
    return {"ok": True, "log": log, "restored_to": state["previous_commit"], "restarting": True, "restart_mode": restart_mode}
