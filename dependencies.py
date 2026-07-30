import os
import uuid
import bcrypt as _bcrypt
import database as models
from fastapi import UploadFile
from sqlalchemy.orm import Session
from typing import Optional
from config import UPLOAD_DIR


def get_db():
    session = models.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _hash_pw(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_pw(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())


async def save_uploaded_file(file: UploadFile, prefix: str) -> Optional[str]:
    if not file or not file.filename:
        return None
    content = await file.read()
    ext = ".jpg"
    try:
        from PIL import Image as _Img, ImageOps as _IOps
        import io as _io
        img = _Img.open(_io.BytesIO(content))
        img = _IOps.exif_transpose(img)
        img.thumbnail((1200, 1200), _Img.LANCZOS)
        out = _io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=80, optimize=True)
        content = out.getvalue()
    except Exception:
        ext = os.path.splitext(file.filename)[1]
    filename = f"{prefix}_{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as buf:
        buf.write(content)
    return f"/static/uploads/{filename}"


async def save_uploaded_document(file: UploadFile, prefix: str) -> Optional[str]:
    if not file or not file.filename:
        return None
    content = await file.read()
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if ext.lower() not in allowed:
        ext = ".pdf"
    filename = f"{prefix}_{uuid.uuid4()}{ext.lower()}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as buf:
        buf.write(content)
    return f"/static/uploads/{filename}"


def delete_uploaded_file(url_path: Optional[str]):
    if not url_path or not url_path.startswith("/static/uploads/"):
        return
    fs_path = os.path.join(UPLOAD_DIR, os.path.basename(url_path))
    try:
        os.remove(fs_path)
    except FileNotFoundError:
        pass


def cleanup_item_images(item):
    for attr in ("image_path", "image_path_1", "image_path_2"):
        delete_uploaded_file(getattr(item, attr, None))
