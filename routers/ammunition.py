import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import database as models
from config import UPLOAD_DIR
from dependencies import get_db, save_uploaded_file, cleanup_item_images
from schemas import AmmoPatchPayload, UseRoundsPayload
from routers.barcode import upsert_upc_cache


def _deduct_ammo_rounds(ammo, rounds: int):
    if rounds <= 0:
        return
    remaining = rounds
    open_rds = ammo.qty_open or 0
    take = min(remaining, open_rds)
    ammo.qty_open = open_rds - take
    remaining -= take
    if remaining > 0:
        rpb = ammo.rounds_per_box or 20
        sealed = ammo.qty_sealed or 0
        while remaining > 0 and sealed > 0:
            sealed -= 1
            take = min(remaining, rpb)
            ammo.qty_open = rpb - take
            remaining -= take
        ammo.qty_sealed = sealed

router = APIRouter()


def _ammo_dict(a: models.Ammo) -> dict:
    return {
        "id": a.id,
        "is_handload": a.is_handload,
        "brand": a.brand,
        "caliber": getattr(a, "caliber", None),
        "line_or_powder": a.line_or_powder,
        "bullet_weight": a.bullet_weight,
        "bullet_type": a.bullet_type,
        "bullet_bc": getattr(a, "bullet_bc", None),
        "charge_weight": a.charge_weight,
        "coal": a.coal,
        "qty_sealed": getattr(a, "qty_sealed", 0) or 0,
        "qty_open": getattr(a, "qty_open", 0) or 0,
        "price_paid": getattr(a, "price_paid", 0.0) or 0.0,
        "rounds_per_box": getattr(a, "rounds_per_box", 20) or 20,
        "image_path": a.image_path,
        "image_path_2": getattr(a, "image_path_2", None),
        "ammo_category": getattr(a, "ammo_category", None),
        "shell_size": getattr(a, "shell_size", None),
        "shot_size": getattr(a, "shot_size", None),
        "upc": getattr(a, "upc", None),
        "factory_velocity_fps": getattr(a, "factory_velocity_fps", None),
        "muzzle_energy_ftlb": getattr(a, "muzzle_energy_ftlb", None),
        "lead_free": getattr(a, "lead_free", None),
        "case_type": getattr(a, "case_type", None),
        "reloadable": getattr(a, "reloadable", None),
    }


@router.post("/ammo/")
async def add_ammo(
    brand: str = Form(None),
    recipe_name: str = Form(None),
    bullet_type: str = Form(None),
    bullet_id: str = Form(None),
    bullet_weight: float = Form(None),
    is_handload: bool = Form(False),
    ammo_model: str = Form(None),
    powder_id: str = Form(None),
    powder_charge: float = Form(None),
    coal: float = Form(None),
    caliber: str = Form(None),
    bullet_bc: float = Form(None),
    qty_sealed: int = Form(0),
    qty_open: int = Form(0),
    price_paid: float = Form(0.0),
    rounds_per_box: int = Form(20),
    upc: str = Form(None),
    ammo_category: str = Form(None),
    shell_size: str = Form(None),
    shot_size: str = Form(None),
    factory_velocity_fps: float = Form(None),
    muzzle_energy_ftlb: float = Form(None),
    case_type: str = Form(None),
    lead_free: str = Form(None),
    reloadable: str = Form(None),
    image: UploadFile = File(None),
    image_2: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    lead_free_val = {"yes": True, "no": False}.get(lead_free)
    reloadable_val = {"yes": True, "no": False}.get(reloadable)
    img_path = await save_uploaded_file(image, "ammo")
    img2 = await save_uploaded_file(image_2, "ammo")
    if not img_path and upc:
        cached = db.query(models.UpcCache).filter(models.UpcCache.upc == upc).first()
        if cached and cached.image_path:
            img_path = cached.image_path
    a = models.Ammo(
        brand=recipe_name or brand or "Unknown",
        caliber=caliber,
        bullet_type=bullet_id or bullet_type or "Unknown",
        bullet_weight=bullet_weight,
        bullet_bc=bullet_bc,
        is_handload=is_handload,
        line_or_powder=ammo_model or powder_id,
        charge_weight=powder_charge,
        coal=coal,
        qty_sealed=qty_sealed,
        qty_open=qty_open,
        price_paid=price_paid,
        rounds_per_box=rounds_per_box,
        image_path=img_path,
        image_path_2=img2,
        ammo_category=ammo_category,
        shell_size=shell_size,
        shot_size=shot_size,
        upc=upc,
        factory_velocity_fps=factory_velocity_fps,
        muzzle_energy_ftlb=muzzle_energy_ftlb,
        case_type=case_type,
        lead_free=lead_free_val,
        reloadable=reloadable_val,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    if not a.is_handload:
        upsert_upc_cache(db, upc, product_type="ammo",
                         brand=brand, product_line=ammo_model, caliber=caliber,
                         weight_gr=bullet_weight, bullet_type=bullet_id or bullet_type,
                         bc_g1=bullet_bc, rounds_per_box=rounds_per_box,
                         factory_velocity_fps=factory_velocity_fps,
                         muzzle_energy_ftlb=muzzle_energy_ftlb,
                         case_type=case_type, lead_free=lead_free_val, reloadable=reloadable_val)
    if qty_sealed > 0 or qty_open > 0:
        price_val = price_paid if (price_paid and price_paid > 0) else None
        _upsert_purchase_log(db, a.id, date.today().isoformat(), qty_sealed, qty_open, price_val)
        db.commit()
    return _ammo_dict(a)


@router.post("/ammo/{ammo_id}/use-rounds/")
def use_ammo_rounds(ammo_id: int, payload: UseRoundsPayload, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    _deduct_ammo_rounds(a, payload.rounds)
    db.commit()
    db.refresh(a)
    return _ammo_dict(a)


@router.post("/ammo/{ammo_id}/update-photo/")
async def update_ammo_photo(ammo_id: int, slot: int = Form(1), image: UploadFile = File(...), db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a: raise HTTPException(404, "Not found")
    path = await save_uploaded_file(image, "ammo")
    if slot == 2: a.image_path_2 = path
    else: a.image_path = path
    db.commit()
    return _ammo_dict(a)

@router.post("/ammo/{ammo_id}/rotate-photo/")
async def rotate_ammo_photo(ammo_id: int, slot: int = Form(1), db: Session = Depends(get_db)):
    import uuid as _uuid
    from PIL import Image as PILImage, ImageOps as PILOps
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a: raise HTTPException(404, "Not found")
    old_path = a.image_path if slot != 2 else a.image_path_2
    if not old_path: raise HTTPException(400, "No photo in this slot")
    old_full = os.path.join(UPLOAD_DIR, os.path.basename(old_path))
    if not os.path.isfile(old_full):
        raise HTTPException(400, "Photo file not found on disk")
    ext = os.path.splitext(old_full)[1] or '.jpg'
    new_filename = f"ammo_{_uuid.uuid4()}{ext}"
    new_full = os.path.join(UPLOAD_DIR, new_filename)
    new_path = f"/static/uploads/{new_filename}"
    img = PILImage.open(old_full)
    img = PILOps.exif_transpose(img)
    rotated = img.rotate(-90, expand=True)
    img.close()
    rotated.save(new_full)
    if slot == 2:
        a.image_path_2 = new_path
    else:
        a.image_path = new_path
    db.commit()
    db.refresh(a)
    try: os.remove(old_full)
    except Exception: pass
    return _ammo_dict(a)

@router.post("/ammo/{ammo_id}/swap-photos/")
def swap_ammo_photos(ammo_id: int, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a: raise HTTPException(404, "Not found")
    tmp = a.image_path
    a.image_path = a.image_path_2
    a.image_path_2 = tmp
    db.commit()
    return _ammo_dict(a)


@router.delete("/ammo/{ammo_id}/photos/{slot}")
def delete_ammo_photo(ammo_id: int, slot: int, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a: raise HTTPException(404, "Not found")
    from dependencies import delete_uploaded_file
    if slot == 2:
        delete_uploaded_file(a.image_path_2)
        a.image_path_2 = None
    else:
        delete_uploaded_file(a.image_path)
        a.image_path = a.image_path_2
        a.image_path_2 = None
    db.commit()
    return _ammo_dict(a)


@router.get("/ammo/by-upc")
def get_ammo_by_upc(upc: str, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(
        models.Ammo.upc == upc,
        models.Ammo.is_handload == False
    ).first()
    if not a:
        return {"found": False}
    result = _ammo_dict(a)
    result["found"] = True
    return result


@router.get("/ammo/")
def list_ammo(db: Session = Depends(get_db)):
    return [_ammo_dict(a) for a in db.query(models.Ammo).all()]


@router.get("/ammo/{ammo_id}")
def get_ammo(ammo_id: int, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    usage = db.query(models.ShotString).filter(models.ShotString.ammo_id == ammo_id).count()
    result = _ammo_dict(a)
    result["usage_count"] = usage
    return result


@router.patch("/ammo/{ammo_id}")
def patch_ammo(ammo_id: int, payload: AmmoPatchPayload, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    update = payload.dict(exclude_unset=True)
    for field, value in update.items():
        setattr(a, field, value)
    if "price_paid" in update and update["price_paid"] and update["price_paid"] > 0:
        db.query(models.AmmoPurchaseLog).filter(
            models.AmmoPurchaseLog.ammo_id == ammo_id,
            models.AmmoPurchaseLog.price_per_box == None,
        ).update({"price_per_box": update["price_paid"]})
    db.commit()
    db.refresh(a)
    return _ammo_dict(a)


def _upsert_purchase_log(db, ammo_id: int, entry_date: str,
                         boxes: int, loose: int, price_val) -> "models.AmmoPurchaseLog":
    """Merge into an existing log row with the same date+price, or create a new one."""
    q = db.query(models.AmmoPurchaseLog).filter(
        models.AmmoPurchaseLog.ammo_id == ammo_id,
        models.AmmoPurchaseLog.date == entry_date,
    )
    q = q.filter(models.AmmoPurchaseLog.price_per_box == None) \
        if price_val is None else \
        q.filter(models.AmmoPurchaseLog.price_per_box == price_val)
    existing = q.first()
    if existing:
        existing.qty_sealed = (existing.qty_sealed or 0) + boxes
        existing.qty_open = (existing.qty_open or 0) + loose
        return existing
    entry = models.AmmoPurchaseLog(
        ammo_id=ammo_id, date=entry_date,
        qty_sealed=boxes, qty_open=loose, price_per_box=price_val,
    )
    db.add(entry)
    return entry


@router.post("/ammo/{ammo_id}/add-stock")
def add_stock(ammo_id: int, payload: dict, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")

    boxes = int(payload.get("qty_sealed", 0))
    loose = int(payload.get("qty_open", 0))
    price = payload.get("price_per_box")
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None

    if boxes == 0 and loose == 0:
        raise HTTPException(status_code=400, detail="No quantity provided")

    a.qty_sealed = (a.qty_sealed or 0) + boxes
    a.qty_open = (a.qty_open or 0) + loose
    if price is not None and price > 0:
        a.price_paid = price

    _upsert_purchase_log(db, ammo_id, date.today().isoformat(), boxes, loose,
                         price if (price and price > 0) else None)
    db.commit()
    db.refresh(a)
    return _ammo_dict(a)


@router.patch("/ammo/{ammo_id}/purchase-log/{entry_id}")
def patch_purchase_log_entry(ammo_id: int, entry_id: int, payload: dict, db: Session = Depends(get_db)):
    entry = db.query(models.AmmoPurchaseLog).filter(
        models.AmmoPurchaseLog.id == entry_id,
        models.AmmoPurchaseLog.ammo_id == ammo_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry not found")
    raw = payload.get("price_per_box")
    if raw == "" or raw is None:
        entry.price_per_box = None
    else:
        try:
            entry.price_per_box = float(raw)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid price")
    db.commit()
    return {"id": entry.id, "date": entry.date, "qty_sealed": entry.qty_sealed,
            "qty_open": entry.qty_open, "price_per_box": entry.price_per_box}


@router.delete("/ammo/{ammo_id}/purchase-log/{entry_id}")
def delete_purchase_log_entry(ammo_id: int, entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.AmmoPurchaseLog).filter(
        models.AmmoPurchaseLog.id == entry_id,
        models.AmmoPurchaseLog.ammo_id == ammo_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry not found")
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


@router.post("/ammo/{ammo_id}/purchase-log")
def add_purchase_log_entry(ammo_id: int, payload: dict, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    entry_date = payload.get("date") or date.today().isoformat()
    boxes = int(payload.get("qty_sealed", 0))
    loose = int(payload.get("qty_open", 0))
    raw_price = payload.get("price_per_box")
    price = float(raw_price) if raw_price else None
    price_val = price if (price and price > 0) else None
    entry = _upsert_purchase_log(db, ammo_id, entry_date, boxes, loose, price_val)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "date": entry.date, "qty_sealed": entry.qty_sealed,
            "qty_open": entry.qty_open, "price_per_box": entry.price_per_box}


@router.get("/ammo/{ammo_id}/purchase-log")
def get_purchase_log(ammo_id: int, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    entries = (
        db.query(models.AmmoPurchaseLog)
        .filter(models.AmmoPurchaseLog.ammo_id == ammo_id)
        .order_by(models.AmmoPurchaseLog.date.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "date": e.date,
            "qty_sealed": e.qty_sealed,
            "qty_open": e.qty_open,
            "price_per_box": e.price_per_box,
        }
        for e in entries
    ]


@router.delete("/ammo/{ammo_id}")
def delete_ammo(ammo_id: int, db: Session = Depends(get_db)):
    a = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Ammo not found")
    usage = db.query(models.ShotString).filter(models.ShotString.ammo_id == ammo_id).count()
    if usage > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {usage} range session(s) reference this load. Delete those sessions first.",
        )
    cleanup_item_images(a)
    upc = getattr(a, 'upc', None)
    db.delete(a)
    db.commit()
    if upc:
        db.query(models.UpcCache).filter(models.UpcCache.upc == upc).delete()
        db.commit()
    return {"deleted": ammo_id}
