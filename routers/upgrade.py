import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from config import templates
from paths import BASE_DIR, DATA_DIR, IS_DESKTOP
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

# Desktop builds have no git checkout to fetch/merge, so they get a much simpler "check the
# latest GitHub Release and hand back a download link" flow instead — see _desktop_check_update.
DESKTOP_REPO_SLUG = "chelohomelab/guns-and-reloading"


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


def _version_at(rev: str) -> str | None:
    """The VERSION file's contents at a given revision — the human-facing "1.24" style number,
    as opposed to _commit_info's git hash/tag. Used to drive the simplified upgrade UI, which
    talks in version numbers rather than commit hashes."""
    r = _git("show", f"{rev}:VERSION")
    return r["stdout"].strip() if r["ok"] and r["stdout"].strip() else None


def _repo_web_url() -> str | None:
    """Browsable https URL for the origin remote, so the UI can link out to GitHub for users
    who want the full commit/release history instead of the simplified in-app view. Derived
    from the actual remote (not hardcoded) so this keeps working for a fork."""
    if not GIT_AVAILABLE:
        return None
    r = _run(["git", "remote", "get-url", "origin"], timeout=10)
    if not r["ok"] or not r["stdout"]:
        return None
    url = r["stdout"].strip()
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):]
    if url.endswith(".git"):
        url = url[:-4]
    return url


REPO_WEB_URL = _repo_web_url()


def _read_local_version() -> str | None:
    """The frozen desktop build's own VERSION file (bundled by desktop/inventory.spec into
    BASE_DIR, i.e. PyInstaller's _MEIPASS) — the git-checkout equivalent is _version_at("HEAD")."""
    version_file = BASE_DIR / "VERSION"
    if not version_file.exists():
        return None
    return version_file.read_text().strip() or None


def _tag_to_version(tag: str) -> str:
    """"v1.24.0" -> "1.24", matching the VERSION file's "major.minor" convention that this
    project's release tags follow. Falls back to the raw tag (minus a leading "v") if a release
    ever ships a non-zero patch number, rather than silently mangling it."""
    v = tag[1:] if tag.startswith("v") else tag
    parts = v.split(".")
    if len(parts) == 3 and parts[2] == "0":
        return f"{parts[0]}.{parts[1]}"
    return v


def _desktop_check_update() -> dict:
    """GitHub's latest-Release equivalent of upgrade_check's git-fetch flow. No in-app run/
    rollback for desktop — the "upgrade" is just downloading and running a new installer, which
    is safe to do over an existing install (Inno Setup's fixed AppId upgrades in place)."""
    current_version = _read_local_version()
    api_url = f"https://api.github.com/repos/{DESKTOP_REPO_SLUG}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "guns-and-reloading-desktop", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"Could not check for updates: {e}", "current_version": current_version}

    latest_version = _tag_to_version(data["tag_name"]) if data.get("tag_name") else None

    # Only offer a direct one-click download if this OS's installer is actually attached to the
    # release yet — build-desktop.yml doesn't auto-attach to Releases today, so early on this
    # will usually fall through to the release page link instead, which is still correct.
    download_url = None
    ext = {"Windows": ".exe", "Darwin": ".dmg", "Linux": ".appimage"}.get(platform.system())
    if ext:
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(ext):
                download_url = asset.get("browser_download_url")
                break

    return {
        "ok": True,
        "current_version": current_version,
        "latest_version": latest_version,
        "up_to_date": bool(latest_version) and latest_version == current_version,
        "download_url": download_url,
        "release_url": data.get("html_url"),
    }


def _is_dirty() -> bool:
    r = _git("status", "--porcelain")
    return bool(r["stdout"])


def _dirty_files() -> list:
    # Raw subprocess call, not _run()/_git() — those .strip() the combined stdout blob, which
    # eats the leading status-column space off just the first porcelain line and throws off its
    # fixed-width "XY <path>" slicing.
    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return [line[3:] for line in r.stdout.splitlines() if line]


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
        "is_desktop": IS_DESKTOP,
        "repo_url": REPO_WEB_URL,
    })


# ── Check for updates ────────────────────────────────────────────────────────

@router.get("/admin/upgrade/check")
def upgrade_check(request: Request):
    _require_admin(request)
    if not GIT_AVAILABLE:
        if IS_DESKTOP:
            return _desktop_check_update()
        _require_git()  # raises the standard "not available for this install type" 400

    current = _commit_info("HEAD")
    current_version = _version_at("HEAD")
    fetch = _git("fetch", "origin", BRANCH, timeout=30)
    if not fetch["ok"]:
        return {
            "ok": False,
            "error": f"git fetch failed: {fetch['stderr'] or 'no network / no access to origin'}",
            "current": current,
            "current_version": current_version,
            "dirty": _is_dirty(),
            "dirty_files": _dirty_files(),
            "rollback": _rollback_summary(),
            "repo_url": REPO_WEB_URL,
        }

    latest = _commit_info(f"origin/{BRANCH}")
    latest_version = _version_at(f"origin/{BRANCH}")
    behind = _git("log", f"HEAD..origin/{BRANCH}", "--format=%h %s")
    commits_behind = behind["stdout"].splitlines() if behind["ok"] and behind["stdout"] else []

    return {
        "ok": True,
        "current": current,
        "current_version": current_version,
        "latest": latest,
        "latest_version": latest_version,
        "up_to_date": current is not None and latest is not None and current["hash"] == latest["hash"],
        "commits_behind": commits_behind,
        "dirty": _is_dirty(),
        "dirty_files": _dirty_files(),
        "rollback": _rollback_summary(),
        "repo_url": REPO_WEB_URL,
    }


def _rollback_summary() -> dict | None:
    state = _load_upgrade_state()
    if not state:
        return None
    resolves = _git("cat-file", "-e", state["previous_commit"])
    backup_exists = Path(state["backup_file"]).exists() if state.get("backup_file") else False
    return {
        **state,
        "previous_version": _version_at(state["previous_commit"]) if resolves["ok"] else None,
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
