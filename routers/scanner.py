import html
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

import database as _models
from dependencies import get_db, save_uploaded_file, cleanup_item_images

router = APIRouter(prefix="/scanner", tags=["scanner"])


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


def _entry_dict(e: "_models.ScannerEntry") -> dict:
    data = {}
    if e.data_json:
        try:
            data = json.loads(e.data_json)
        except Exception:
            pass
    return {
        "id": e.id,
        "category": e.category,
        "upc": e.upc,
        "title": e.title,
        "brand": e.brand,
        "caliber": e.caliber,
        "notes": e.notes,
        "image_path_1": e.image_path_1,
        "image_path_2": e.image_path_2,
        "image_path_3": e.image_path_3,
        "data": data,
        "created_at": e.created_at,
        "is_reviewed": e.is_reviewed,
        "source_url": e.source_url,
    }


_AMMO_REQUIRED = {
    "bullet_weight": "Bullet Weight",
    "bc_g1": "BC (G1)",
    "factory_velocity_fps": "Velocity",
    "muzzle_energy_ftlb": "Muzzle Energy",
}


def _missing_fields(entry: "_models.ScannerEntry") -> list:
    """Return human-readable labels of required fields still missing for this
    entry's category — powers both the completeness check and the "what's missing"
    hint shown on incomplete review cards, so the two can never drift apart.
    """
    missing = []
    if not entry.brand:
        missing.append("Brand")
    cat = entry.category
    data = {}
    if entry.data_json:
        try:
            data = json.loads(entry.data_json)
        except Exception:
            pass
    if cat == "ammo":
        if not entry.caliber:
            missing.append("Caliber")
        for field, label in _AMMO_REQUIRED.items():
            if data.get(field) is None:
                missing.append(label)
    elif cat in ("firearm", "optic"):
        if not data.get("model"):
            missing.append("Model")
    elif cat == "tc_barrel":
        if not entry.caliber:
            missing.append("Caliber")
        if not data.get("platform"):
            missing.append("Platform")
    # component: brand alone is enough, nothing else required
    return missing


def _is_complete(entry: "_models.ScannerEntry") -> bool:
    return len(_missing_fields(entry)) == 0


@router.get("/entries")
def list_entries(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    entries = db.query(_models.ScannerEntry).order_by(_models.ScannerEntry.id.desc()).all()
    result = []
    for e in entries:
        d = _entry_dict(e)
        missing = _missing_fields(e)
        d["is_complete"] = len(missing) == 0
        d["missing_fields"] = missing
        result.append(d)
    return result


@router.post("/entries")
async def create_entry(
    request: Request,
    category: str = Form(default=""),
    upc: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    brand: Optional[str] = Form(default=None),
    caliber: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    data_json: Optional[str] = Form(default=None),
    photo: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(request)
    image_path = await save_uploaded_file(photo, "scan") if photo else None
    entry = _models.ScannerEntry(
        category=category or "ammo",
        upc=upc or None,
        title=title or None,
        brand=brand or None,
        caliber=caliber or None,
        notes=notes or None,
        data_json=data_json or None,
        image_path_1=image_path,
        created_at=datetime.now(timezone.utc).date().isoformat(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    d = _entry_dict(entry)
    d["is_complete"] = _is_complete(entry)
    return d


@router.patch("/entries/{entry_id}")
async def update_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    body = await request.json()
    for field in ("category", "upc", "title", "brand", "caliber", "notes", "data_json", "is_reviewed"):
        if field in body:
            setattr(entry, field, body[field])
    db.commit()
    d = _entry_dict(entry)
    d["is_complete"] = _is_complete(entry)
    return d


@router.post("/entries/{entry_id}/add-photo")
async def add_photo(
    entry_id: int,
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    path = await save_uploaded_file(photo, "scan")
    if not path:
        raise HTTPException(400, "Upload failed")
    if not entry.image_path_1:
        entry.image_path_1 = path
    elif not entry.image_path_2:
        entry.image_path_2 = path
    elif not entry.image_path_3:
        entry.image_path_3 = path
    else:
        raise HTTPException(400, "Max 3 photos per entry")
    db.commit()
    return {"image_path_1": entry.image_path_1, "image_path_2": entry.image_path_2, "image_path_3": entry.image_path_3}


@router.delete("/entries/{entry_id}/photos/{slot}")
def delete_photo(
    entry_id: int,
    slot: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    if slot == 1:
        entry.image_path_1 = None
    elif slot == 2:
        entry.image_path_2 = None
    elif slot == 3:
        entry.image_path_3 = None
    db.commit()
    return {"ok": True}


@router.delete("/entries/reviewed")
def delete_reviewed_entries(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    count = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.is_reviewed == True).delete()
    db.commit()
    return {"deleted": count}


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    cleanup_item_images(entry)
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


def merge_ammo_fields(existing: "_models.Ammo", brand, caliber, data: dict, image_path_1=None, image_path_2=None) -> bool:
    """Fill in only fields missing on an existing Ammo row from freshly captured data —
    never overwrite a value the row already has. Shared by both the Scanner "Accept"
    conversion path and the bookmarklet's direct-capture-into-inventory shortcut.
    Returns True if anything actually changed.
    """
    merge_fields = {
        "brand": brand,
        "caliber": caliber,
        "line_or_powder": data.get("product_line"),
        "bullet_weight": float(data.get("bullet_weight", 0) or 0) or None,
        "bullet_type": data.get("bullet_type"),
        "bullet_bc": float(data.get("bc_g1", 0) or 0) or None,
        "rounds_per_box": int(data.get("rounds_per_box", 0) or 0) or None,
        "image_path": image_path_1,
        "image_path_2": image_path_2,
        "factory_velocity_fps": float(data.get("factory_velocity_fps", 0) or 0) or None,
        "muzzle_energy_ftlb": float(data.get("muzzle_energy_ftlb", 0) or 0) or None,
        "case_type": data.get("case_type"),
    }
    changed = False
    for field, val in merge_fields.items():
        if val and not getattr(existing, field):
            setattr(existing, field, val)
            changed = True
    # Booleans need an explicit None check — False is a real value, not "missing"
    for field in ("lead_free", "reloadable"):
        val = data.get(field)
        if val is not None and getattr(existing, field) is None:
            setattr(existing, field, val)
            changed = True
    return changed


@router.post("/entries/{entry_id}/convert")
def convert_entry_to_inventory(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    if not _is_complete(entry):
        raise HTTPException(400, "Entry is incomplete — fill required fields first")

    data = {}
    if entry.data_json:
        try:
            data = json.loads(entry.data_json)
        except Exception:
            pass

    result_type = None
    result_id = None
    cat = entry.category

    if cat == "firearm":
        frame = data.get("frame_type", "Rifle")
        f = _models.Firearm(
            brand=entry.brand or "Unknown",
            model=data.get("model", "Unknown"),
            frame_type=frame,
            price_paid=float(data.get("price_paid", 0) or 0),
            serial_number=data.get("serial_number"),
            image_path_1=entry.image_path_1,
            image_path_2=entry.image_path_2,
        )
        db.add(f)
        db.flush()
        barrel = _models.Barrel(
            firearm_id=f.id,
            caliber=entry.caliber or "Unknown",
            name="Primary",
            twist_rate=data.get("twist_rate"),
        )
        db.add(barrel)
        db.commit()
        db.refresh(f)
        result_type = "firearm"
        result_id = f.id

    elif cat == "optic":
        s = _models.Scope(
            brand=entry.brand or "Unknown",
            model=data.get("model", "Unknown"),
            magnification=data.get("magnification"),
            units=data.get("units", "MOA"),
            price_paid=float(data.get("price_paid", 0) or 0),
            image_path=entry.image_path_1,
            image_path_2=entry.image_path_2,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        result_type = "scope"
        result_id = s.id

    elif cat == "ammo" and entry.source_url:
        # Came from the MidwayUSA bookmarklet import — the point of that whole feature
        # is to stop depending on the incomplete external UPC lookup API, so "Accept"
        # here means "trust this enough to seed the local UPC cache" (the same cache
        # /barcode/lookup checks first), not "I own this, put it in inventory now."
        if not entry.upc:
            raise HTTPException(400, "Can't cache — this capture has no UPC")
        from routers.barcode import upsert_upc_cache
        upsert_upc_cache(
            db, entry.upc,
            title=entry.title,
            product_type="ammo",
            brand=entry.brand,
            product_line=data.get("product_line"),
            caliber=entry.caliber,
            weight_gr=data.get("bullet_weight"),
            bullet_type=data.get("bullet_type"),
            bc_g1=data.get("bc_g1"),
            rounds_per_box=data.get("rounds_per_box"),
            primer_type=data.get("primer_type"),
            primer_model=data.get("primer_model"),
            image_path=entry.image_path_1,
            factory_velocity_fps=data.get("factory_velocity_fps"),
            muzzle_energy_ftlb=data.get("muzzle_energy_ftlb"),
            lead_free=data.get("lead_free"),
            case_type=data.get("case_type"),
            reloadable=data.get("reloadable"),
        )
        result_type = "upc_cache"
        result_id = None

    elif cat == "ammo":
        existing = None
        if entry.upc:
            existing = db.query(_models.Ammo).filter(_models.Ammo.upc == entry.upc).first()

        if existing:
            # Same UPC already in inventory — fill in only what's missing, never
            # overwrite a value the user already has recorded.
            merge_ammo_fields(existing, entry.brand, entry.caliber, data, entry.image_path_1, entry.image_path_2)
            db.commit()
            db.refresh(existing)
            result_type = "ammo"
            result_id = existing.id
        else:
            a = _models.Ammo(
                brand=entry.brand or "Unknown",
                caliber=entry.caliber,
                line_or_powder=data.get("product_line"),
                bullet_weight=float(data.get("bullet_weight", 0) or 0) or None,
                bullet_type=data.get("bullet_type"),
                bullet_bc=float(data.get("bc_g1", 0) or 0) or None,
                qty_sealed=int(data.get("qty_sealed", 0) or 0),
                qty_open=int(data.get("qty_open", 0) or 0),
                rounds_per_box=int(data.get("rounds_per_box", 20) or 20),
                price_paid=float(data.get("price_paid", 0) or 0),
                upc=entry.upc,
                image_path=entry.image_path_1,
                image_path_2=entry.image_path_2,
                factory_velocity_fps=float(data.get("factory_velocity_fps", 0) or 0) or None,
                muzzle_energy_ftlb=float(data.get("muzzle_energy_ftlb", 0) or 0) or None,
                lead_free=data.get("lead_free"),
                case_type=data.get("case_type"),
                reloadable=data.get("reloadable"),
            )
            db.add(a)
            db.commit()
            db.refresh(a)
            result_type = "ammo"
            result_id = a.id

    elif cat == "tc_barrel":
        b = _models.Barrel(
            caliber=entry.caliber or "Unknown",
            tc_platform=data.get("platform", "Encore"),
            barrel_length=data.get("barrel_length"),
            twist_rate=data.get("twist_rate"),
            price_paid=float(data.get("price_paid", 0) or 0),
            image_path=entry.image_path_1,
        )
        db.add(b)
        db.commit()
        db.refresh(b)
        result_type = "tc_barrel"
        result_id = b.id

    elif cat == "component":
        result_type = "component"

    else:
        raise HTTPException(400, f"Unknown category: {cat}")

    entry.is_reviewed = True
    db.commit()
    db.delete(entry)
    db.commit()

    return {"type": result_type, "id": result_id}


@router.post("/entries/{entry_id}/autofill")
def autofill_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Look up the entry's UPC and return proposed field changes without applying them."""
    _require_admin(request)
    entry = db.query(_models.ScannerEntry).filter(_models.ScannerEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Not found")
    if not entry.upc:
        raise HTTPException(400, "No UPC on this entry")

    # Reuse the cache-first lookup from barcode.py
    import re, urllib.request, urllib.parse, json as _json
    from routers.barcode import (
        _parse_brand, _parse_caliber, _parse_weight, _parse_bullet_type,
        _parse_product_line, _parse_rounds, _parse_primer_type, _parse_primer_model,
        _parse_powder_name, _lookup_bc, _cache_to_response, _download_upc_image,
        upsert_upc_cache,
    )

    upc = entry.upc
    cached = db.query(_models.UpcCache).filter(_models.UpcCache.upc == upc).first()
    if cached:
        info = _cache_to_response(cached)
    else:
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={urllib.parse.quote(upc)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "homelab-inventory/1.7"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                api_data = _json.loads(resp.read().decode())
        except Exception as e:
            raise HTTPException(502, f"UPC lookup failed: {e}")
        items = api_data.get("items", [])
        if not items:
            raise HTTPException(404, "UPC not found in external database")
        item = items[0]
        title = item.get("title") or item.get("description") or ""
        raw_brand = html.unescape(item.get("brand") or "")
        api_images = item.get("images") or []
        image_path = None
        for img_url in api_images:
            if img_url:
                image_path = _download_upc_image(upc, img_url)
                if image_path:
                    break
        brand = _parse_brand(raw_brand, title)
        weight_gr = _parse_weight(title)
        caliber = _parse_caliber(title)
        bullet_type = _parse_bullet_type(title)
        product_line = _parse_product_line(title)
        rounds_per_box = _parse_rounds(title)
        primer_type = _parse_primer_type(title)
        powder_brand, powder_name = _parse_powder_name(title)
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        info = {
            "upc": upc, "title": title, "brand": powder_brand or brand,
            "product_line": product_line, "powder_name": powder_name,
            "caliber": caliber, "weight_gr": weight_gr, "bullet_type": bullet_type,
            "rounds_per_box": rounds_per_box, "bc_g1": bc_data.get("bc_g1"),
            "primer_type": primer_type,
            "primer_model": _parse_primer_model(title), "image_path": image_path,
        }
        # Persist to cache so future lookups (and the main barcode endpoint) are instant
        upsert_upc_cache(db, upc,
                         title=title, product_type=None,
                         brand=powder_brand or brand, product_line=product_line,
                         powder_name=powder_name, caliber=caliber,
                         weight_gr=weight_gr, bullet_type=bullet_type,
                         rounds_per_box=rounds_per_box,
                         bc_g1=bc_data.get("bc_g1"),
                         primer_type=primer_type,
                         primer_model=_parse_primer_model(title),
                         image_path=image_path)

    # Map to proposed entry fields
    proposed_base = {}
    proposed_data = {}

    if info.get("title") and not entry.title:
        proposed_base["title"] = info["title"]
    if info.get("brand") and not entry.brand:
        proposed_base["brand"] = info["brand"]
    if info.get("caliber") and not entry.caliber:
        proposed_base["caliber"] = info["caliber"]

    existing_data = {}
    if entry.data_json:
        try:
            existing_data = _json.loads(entry.data_json)
        except Exception:
            pass

    for key in ("product_line", "weight_gr", "bullet_type", "rounds_per_box",
                "bc_g1", "primer_type", "primer_model", "powder_name"):
        val = info.get(key)
        if val is not None and not existing_data.get(key):
            proposed_data[key] = val

    if info.get("image_path") and not entry.image_path_1:
        proposed_base["image_path_1"] = info["image_path"]

    return {
        "proposed_base": proposed_base,
        "proposed_data": proposed_data,
        "source": info.get("source", "api"),
    }
