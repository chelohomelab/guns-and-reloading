import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

import database as models
from config import UPLOAD_DIR, templates
from dependencies import get_db

router = APIRouter()

DB_PATH = Path("data/reloading.db")
BACKUP_CONFIG_PATH = Path("data/backup_config.json")
DEFAULT_CONFIG = {
    "local_path": "/opt/inventory-and-reloading/backups",
    "keep_count": 7,
    "rclone_remote": "",
    "rclone_path": "inventory-backup",
}


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


def _load_config() -> dict:
    if BACKUP_CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(BACKUP_CONFIG_PATH.read_text())}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def _save_config(cfg: dict):
    BACKUP_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _build_zip(buf: io.BytesIO):
    """Write a backup ZIP into buf containing the DB + uploads."""
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Safe SQLite copy via the backup API
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            src = sqlite3.connect(str(DB_PATH))
            dst = sqlite3.connect(tmp.name)
            src.backup(dst)
            src.close()
            dst.close()
            zf.write(tmp.name, "reloading.db")
        finally:
            os.unlink(tmp.name)

        # Photos
        uploads = Path(UPLOAD_DIR)
        if uploads.exists():
            for f in uploads.rglob("*"):
                if f.is_file():
                    zf.write(f, f"uploads/{f.name}")

        # Metadata
        meta = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "photo_count": sum(1 for _ in uploads.rglob("*") if _.is_file()) if uploads.exists() else 0,
            "app_version": "1.9",
        }
        zf.writestr("backup_meta.json", json.dumps(meta, indent=2))


def _rotate_backups(backup_dir: Path, keep: int):
    files = sorted(backup_dir.glob("reloading_backup_*.zip"), key=lambda f: f.stat().st_mtime)
    for old in files[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)


def restore_zip_bytes(data: bytes) -> dict:
    """Restore the DB + uploads from backup ZIP bytes. Shared by the upload-restore,
    restore-by-server-filename, and upgrade-rollback endpoints so all three agree on
    exactly what "restore" means instead of drifting apart over time."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Invalid ZIP file")

    names = zf.namelist()
    if "reloading.db" not in names:
        raise HTTPException(400, "ZIP does not contain reloading.db — not a valid backup")

    # Restore DB via sqlite3 backup API (safe while service is running)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(zf.read("reloading.db"))
        tmp_path = tmp.name

    try:
        src = sqlite3.connect(tmp_path)
        dst = sqlite3.connect(str(DB_PATH))
        src.backup(dst)
        src.close()
        dst.close()
    finally:
        os.unlink(tmp_path)

    # Restore uploads
    uploads_dir = Path(UPLOAD_DIR)
    restored_photos = 0
    for name in names:
        if name.startswith("uploads/") and not name.endswith("/"):
            dest = uploads_dir / Path(name).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            restored_photos += 1

    meta = {}
    if "backup_meta.json" in names:
        try:
            meta = json.loads(zf.read("backup_meta.json"))
        except Exception:
            pass

    return {"ok": True, "photos_restored": restored_photos, "backup_created_at": meta.get("created_at")}


def save_backup_zip(cfg: dict) -> Path:
    """Build a fresh backup ZIP and save it into the configured local backup folder,
    rotating old ones per keep_count. Shared by the manual Save-to-Server/Push-to-Cloud
    actions and the automatic pre-upgrade backup."""
    backup_dir = Path(cfg["local_path"])
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"reloading_backup_{ts}.zip"
    buf = io.BytesIO()
    _build_zip(buf)
    out.write_bytes(buf.getvalue())
    _rotate_backups(backup_dir, cfg["keep_count"])
    return out


# ── Pages ────────────────────────────────────────────────────────────────────

@router.get("/admin/backup", response_class=HTMLResponse)
async def backup_page(request: Request):
    _require_admin(request)
    cfg = _load_config()
    rclone_ok = shutil.which("rclone") is not None
    return templates.TemplateResponse("admin-backup.html", {
        "request": request,
        "user": request.state.user,
        "config": cfg,
        "rclone_available": rclone_ok,
    })


# ── Download ─────────────────────────────────────────────────────────────────

@router.get("/admin/backup/download")
def backup_download(request: Request):
    _require_admin(request)
    buf = io.BytesIO()
    _build_zip(buf)
    buf.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"reloading_backup_{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Save to local path ────────────────────────────────────────────────────────

@router.post("/admin/backup/save")
def backup_save(request: Request):
    _require_admin(request)
    cfg = _load_config()
    out = save_backup_zip(cfg)
    return {"ok": True, "file": str(out), "size_bytes": out.stat().st_size}


# ── List local backups ────────────────────────────────────────────────────────

@router.get("/admin/backup/list")
def backup_list(request: Request):
    _require_admin(request)
    cfg = _load_config()
    backup_dir = Path(cfg["local_path"])
    if not backup_dir.exists():
        return []
    files = sorted(backup_dir.glob("reloading_backup_*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.utcfromtimestamp(f.stat().st_mtime).isoformat() + "Z",
        }
        for f in files
    ]


# ── Delete local backup ───────────────────────────────────────────────────────

@router.delete("/admin/backup/{filename}")
def backup_delete(filename: str, request: Request):
    _require_admin(request)
    if "/" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    cfg = _load_config()
    target = Path(cfg["local_path"]) / filename
    if not target.exists():
        raise HTTPException(404, "Backup not found")
    target.unlink()
    return {"deleted": filename}


# ── Push to cloud via rclone ──────────────────────────────────────────────────

@router.post("/admin/backup/push-cloud")
def backup_push_cloud(request: Request):
    _require_admin(request)
    if not shutil.which("rclone"):
        raise HTTPException(400, "rclone is not installed")
    cfg = _load_config()
    if not cfg.get("rclone_remote"):
        raise HTTPException(400, "rclone remote not configured")

    # Save a fresh backup locally first
    out = save_backup_zip(cfg)

    remote_dest = f"{cfg['rclone_remote']}:{cfg['rclone_path']}"
    result = subprocess.run(
        ["rclone", "copy", str(out), remote_dest, "--progress"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise HTTPException(500, f"rclone failed: {result.stderr.strip()}")
    return {"ok": True, "file": out.name, "remote": remote_dest}


# ── Restore from ZIP upload ───────────────────────────────────────────────────

@router.post("/admin/backup/restore")
async def backup_restore(request: Request, file: UploadFile = File(...)):
    _require_admin(request)
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Must be a .zip backup file")
    data = await file.read()
    return restore_zip_bytes(data)


# ── Restore from local server file ───────────────────────────────────────────

@router.post("/admin/backup/restore-local")
async def backup_restore_local(request: Request):
    _require_admin(request)
    body = await request.json()
    filename = body.get("filename", "")
    if not filename or "/" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    cfg = _load_config()
    path = Path(cfg["local_path"]) / filename
    if not path.exists():
        raise HTTPException(404, "Backup file not found")
    return restore_zip_bytes(path.read_bytes())


# ── Config update ─────────────────────────────────────────────────────────────

@router.post("/admin/backup/config")
async def backup_config_save(request: Request):
    _require_admin(request)
    body = await request.json()
    cfg = _load_config()
    for key in ("local_path", "keep_count", "rclone_remote", "rclone_path"):
        if key in body:
            cfg[key] = body[key]
    if "keep_count" in cfg:
        cfg["keep_count"] = int(cfg["keep_count"])
    _save_config(cfg)
    return {"ok": True, "config": cfg}
