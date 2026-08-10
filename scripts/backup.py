#!/usr/bin/env python3
"""Standalone backup script — safe to run while the service is live."""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
from paths import DATA_DIR  # noqa: E402
from version import __version__  # noqa: E402

DB_PATH = Path(DATA_DIR) / "data" / "reloading.db"
UPLOADS_DIR = Path(DATA_DIR) / "static" / "uploads"
CONFIG_PATH = Path(DATA_DIR) / "data" / "backup_config.json"

DEFAULT_CONFIG = {
    "local_path": str(Path(DATA_DIR) / "backups"),
    "keep_count": 7,
    "rclone_remote": "",
    "rclone_path": "inventory-backup",
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def build_zip(out_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Safe SQLite copy via backup API
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            src = sqlite3.connect(str(DB_PATH))
            dst = sqlite3.connect(tmp_path)
            src.backup(dst)
            src.close()
            dst.close()
            zf.write(tmp_path, "reloading.db")
        finally:
            os.unlink(tmp_path)

        # Photos
        if UPLOADS_DIR.exists():
            for f in UPLOADS_DIR.rglob("*"):
                if f.is_file():
                    zf.write(f, f"uploads/{f.name}")

        # Metadata
        photo_count = sum(1 for f in UPLOADS_DIR.rglob("*") if f.is_file()) if UPLOADS_DIR.exists() else 0
        meta = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "photo_count": photo_count,
            "app_version": __version__,
        }
        zf.writestr("backup_meta.json", json.dumps(meta, indent=2))

    out_path.write_bytes(buf.getvalue())


def rotate(backup_dir: Path, keep: int):
    files = sorted(backup_dir.glob("reloading_backup_*.zip"), key=lambda f: f.stat().st_mtime)
    for old in files[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
        print(f"[backup] Removed old backup: {old.name}")


def main():
    cfg = load_config()
    backup_dir = Path(cfg["local_path"])
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"reloading_backup_{ts}.zip"

    print(f"[backup] Starting backup → {out}")
    build_zip(out)
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"[backup] Created: {out.name} ({size_mb:.1f} MB)")

    rotate(backup_dir, cfg["keep_count"])
    print(f"[backup] Retention: keeping last {cfg['keep_count']} backups")

    rclone_remote = cfg.get("rclone_remote", "").strip()
    if rclone_remote:
        rclone_bin = subprocess.run(["which", "rclone"], capture_output=True, text=True).stdout.strip()
        if rclone_bin:
            dest = f"{rclone_remote}:{cfg['rclone_path']}"
            print(f"[backup] Pushing to {dest} …")
            result = subprocess.run(["rclone", "copy", str(out), dest], capture_output=True, text=True)
            if result.returncode == 0:
                print("[backup] Cloud push complete.")
            else:
                print(f"[backup] WARNING: rclone failed: {result.stderr.strip()}", file=sys.stderr)
        else:
            print("[backup] WARNING: rclone_remote set but rclone not found.", file=sys.stderr)

    print("[backup] Done.")


if __name__ == "__main__":
    main()
