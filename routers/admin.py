from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import database as models
from config import templates
from dependencies import get_db, _hash_pw, cleanup_item_images
from schemas import AdminUserPatch

router = APIRouter()


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(models.User).order_by(models.User.id).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request, "user": request.state.user, "users": users,
    })


@router.get("/admin/phone-setup", response_class=HTMLResponse)
async def admin_phone_setup_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("admin-phone-setup.html", {
        "request": request, "user": request.state.user,
    })


@router.patch("/admin/users/{user_id}")
def admin_patch_user(user_id: int, payload: AdminUserPatch, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Not found")
    if payload.is_admin  is not None: u.is_admin  = payload.is_admin
    if payload.is_active is not None: u.is_active = payload.is_active
    db.commit()
    return {"id": u.id, "username": u.username, "is_admin": u.is_admin, "is_active": u.is_active}


@router.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    if user_id == request.state.user.id:
        raise HTTPException(400, "Cannot delete your own account")
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Not found")
    db.delete(u)
    db.commit()
    return {"deleted": user_id}


@router.get("/admin/trash-items")
def admin_trash_items(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    firearms = db.query(models.Firearm).filter(models.Firearm.is_deleted == True).all()
    receivers = db.query(models.TCReceiver).filter(models.TCReceiver.is_deleted == True).all()
    barrels = db.query(models.Barrel).filter(
        models.Barrel.tc_platform.isnot(None), models.Barrel.is_deleted == True
    ).all()
    scopes = db.query(models.Scope).filter(models.Scope.is_deleted == True).all()
    return {
        "firearms": [{"id": g.id, "label": f"{g.brand} {g.model}", "frame_type": g.frame_type, "image": g.image_path_1} for g in firearms],
        "tc_receivers": [{"id": r.id, "label": f"{r.platform} Receiver (S/N: {r.serial_number or '—'})", "image": r.image_path} for r in receivers],
        "tc_barrels": [{"id": b.id, "label": f"{b.tc_platform} {b.caliber}", "frame_type": b.barrel_length or "", "image": b.image_path} for b in barrels],
        "scopes": [{"id": s.id, "label": f"{s.brand} {s.model}", "image": s.image_path} for s in scopes],
    }


@router.delete("/admin/trash/firearms/{firearm_id}")
def admin_perma_delete_firearm(firearm_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    gun = db.query(models.Firearm).filter(models.Firearm.id == firearm_id, models.Firearm.is_deleted == True).first()
    if not gun:
        raise HTTPException(404, "Not found in trash")
    for barrel in gun.barrels:
        cleanup_item_images(barrel)
    cleanup_item_images(gun)
    db.delete(gun)
    db.commit()
    return {"deleted": firearm_id}


@router.delete("/admin/trash/tc-receivers/{receiver_id}")
def admin_perma_delete_receiver(receiver_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    r = db.query(models.TCReceiver).filter(models.TCReceiver.id == receiver_id, models.TCReceiver.is_deleted == True).first()
    if not r:
        raise HTTPException(404, "Not found in trash")
    cleanup_item_images(r)
    db.delete(r)
    db.commit()
    return {"deleted": receiver_id}


@router.delete("/admin/trash/scopes/{scope_id}")
def admin_perma_delete_scope(scope_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    s = db.query(models.Scope).filter(models.Scope.id == scope_id, models.Scope.is_deleted == True).first()
    if not s:
        raise HTTPException(404, "Not found in trash")
    cleanup_item_images(s)
    db.delete(s)
    db.commit()
    return {"deleted": scope_id}


@router.delete("/admin/trash/tc-barrels/{barrel_id}")
def admin_perma_delete_tc_barrel(barrel_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    b = db.query(models.Barrel).filter(
        models.Barrel.id == barrel_id,
        models.Barrel.tc_platform.isnot(None),
        models.Barrel.is_deleted == True,
    ).first()
    if not b:
        raise HTTPException(404, "Not found in trash")
    cleanup_item_images(b)
    db.delete(b)
    db.commit()
    return {"deleted": barrel_id}


@router.post("/admin/users/")
async def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(default=None),
    is_admin: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(request)
    if db.query(models.User).filter(models.User.username == username.strip()).first():
        raise HTTPException(400, "Username already exists")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    u = models.User(
        username=username.strip(),
        email=email.strip() if email else None,
        hashed_password=_hash_pw(password),
        is_admin=bool(is_admin),
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "is_admin": u.is_admin}
