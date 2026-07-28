from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import database as models
from dependencies import get_db, save_uploaded_file, save_uploaded_document, cleanup_item_images, delete_uploaded_file
from schemas import PowderPatch, PrimerPatch, BulletComponentPatch, CasingPatch, DeductPayload, LoadDataPatch, LoadDataEntryPayload
from routers.barcode import upsert_upc_cache

router = APIRouter()


# ── Serializers ────────────────────────────────────────────────────────────────

def _powder_dict(p: models.PowderInventory) -> dict:
    return {"id": p.id, "brand": p.brand, "name": p.name,
            "weight_lbs": p.weight_lbs, "price_paid": p.price_paid, "notes": p.notes,
            "image_path": p.image_path, "image_path_2": p.image_path_2,
            "is_muzzleloader": getattr(p, "is_muzzleloader", False) or False,
            "pellet_mode": getattr(p, "pellet_mode", False) or False}

def _primer_dict(p: models.PrimerInventory) -> dict:
    return {"id": p.id, "brand": p.brand, "model": p.model, "primer_type": p.primer_type,
            "quantity": p.quantity, "price_paid": p.price_paid, "notes": p.notes,
            "image_path": p.image_path, "image_path_2": p.image_path_2,
            "is_muzzleloader": getattr(p, "is_muzzleloader", False) or False}

def _bullet_dict(b: models.BulletInventory) -> dict:
    return {"id": b.id, "brand": b.brand, "product_line": b.product_line,
            "caliber": b.caliber, "weight_gr": b.weight_gr, "bullet_type": b.bullet_type,
            "bc_g1": b.bc_g1, "sku": getattr(b, "sku", None),
            "quantity": b.quantity,
            "qty_sealed": getattr(b, "qty_sealed", 0) or 0,
            "qty_open": getattr(b, "qty_open", 0) or 0,
            "price_paid": b.price_paid, "notes": b.notes,
            "image_path": b.image_path, "image_path_2": b.image_path_2,
            "is_muzzleloader": getattr(b, "is_muzzleloader", False) or False,
            "datasheet_path": getattr(b, "datasheet_path", None),
            "load_data_count": len(getattr(b, "load_data_sets", None) or [])}

def _casing_dict(c: models.CasingInventory) -> dict:
    label = "New" if c.times_fired == 0 else f"{c.times_fired}x Fired"
    return {"id": c.id, "brand": c.brand, "caliber": c.caliber,
            "quantity": c.quantity, "times_fired": c.times_fired,
            "condition_label": label, "price_paid": c.price_paid, "notes": c.notes,
            "image_path": c.image_path, "image_path_2": c.image_path_2}

def _get_thresholds(db: Session) -> dict:
    rows = {s.key: float(s.value) for s in db.query(models.Setting).all()}
    return {
        "powder_lbs": rows.get("low_stock_powder_lbs", 0.5),
        "primers":    rows.get("low_stock_primers", 200),
        "bullets":    rows.get("low_stock_bullets", 100),
        "casings":    rows.get("low_stock_casings", 50),
    }


# ── Powders ────────────────────────────────────────────────────────────────────

@router.get("/components/powders/")
def list_powders(muzzleloader: bool = Query(False), db: Session = Depends(get_db)):
    q = db.query(models.PowderInventory)
    if muzzleloader:
        q = q.filter(models.PowderInventory.is_muzzleloader == True)
    return [_powder_dict(p) for p in q.all()]

@router.post("/components/powders/")
async def add_powder(
    brand: str = Form(...), name: str = Form(...),
    weight_lbs: float = Form(0.0), price: float = Form(0.0),
    notes: str = Form(None), upc: str = Form(None),
    is_muzzleloader: bool = Form(False),
    pellet_mode: bool = Form(False),
    image_1: UploadFile = File(None), image_2: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    img1 = await save_uploaded_file(image_1, "component")
    img2 = await save_uploaded_file(image_2, "component")
    if not img1 and upc:
        cached = db.query(models.UpcCache).filter(models.UpcCache.upc == upc).first()
        if cached and cached.image_path:
            img1 = cached.image_path
    p = models.PowderInventory(brand=brand, name=name, weight_lbs=weight_lbs,
                               price_paid=price, notes=notes,
                               image_path=img1, image_path_2=img2, upc=upc,
                               is_muzzleloader=is_muzzleloader,
                               pellet_mode=pellet_mode)
    db.add(p); db.commit(); db.refresh(p)
    upsert_upc_cache(db, upc, product_type="powder", brand=brand, powder_name=name, title=name)
    return _powder_dict(p)

@router.patch("/components/powders/{item_id}")
def patch_powder(item_id: int, payload: PowderPatch, db: Session = Depends(get_db)):
    p = db.query(models.PowderInventory).filter(models.PowderInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    for k, v in payload.dict(exclude_none=True).items(): setattr(p, k, v)
    db.commit(); db.refresh(p)
    return _powder_dict(p)

@router.delete("/components/powders/{item_id}")
def delete_powder(item_id: int, db: Session = Depends(get_db)):
    p = db.query(models.PowderInventory).filter(models.PowderInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    cleanup_item_images(p)
    upc = getattr(p, 'upc', None)
    db.delete(p); db.commit()
    if upc:
        db.query(models.UpcCache).filter(models.UpcCache.upc == upc).delete(); db.commit()
    return {"deleted": item_id}

@router.post("/components/powders/{item_id}/update-photo/")
async def update_powder_photo(item_id: int, slot: int = Form(1), image: UploadFile = File(...), db: Session = Depends(get_db)):
    p = db.query(models.PowderInventory).filter(models.PowderInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    path = await save_uploaded_file(image, "component")
    if slot == 2: p.image_path_2 = path
    else: p.image_path = path
    db.commit()
    return _powder_dict(p)

@router.post("/components/powders/{item_id}/swap-photos/")
def swap_powder_photos(item_id: int, db: Session = Depends(get_db)):
    p = db.query(models.PowderInventory).filter(models.PowderInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    p.image_path, p.image_path_2 = p.image_path_2, p.image_path
    db.commit()
    return _powder_dict(p)


# ── Primers ────────────────────────────────────────────────────────────────────

@router.get("/components/primers/")
def list_primers(muzzleloader: bool = Query(False), db: Session = Depends(get_db)):
    q = db.query(models.PrimerInventory)
    if muzzleloader:
        q = q.filter(models.PrimerInventory.is_muzzleloader == True)
    return [_primer_dict(p) for p in q.all()]

@router.post("/components/primers/")
async def add_primer(
    brand: str = Form(...), model: str = Form(None), primer_type: str = Form(...),
    quantity: int = Form(0), price: float = Form(0.0),
    notes: str = Form(None), upc: str = Form(None),
    is_muzzleloader: bool = Form(False),
    image_1: UploadFile = File(None), image_2: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    img1 = await save_uploaded_file(image_1, "component")
    img2 = await save_uploaded_file(image_2, "component")
    if not img1 and upc:
        cached = db.query(models.UpcCache).filter(models.UpcCache.upc == upc).first()
        if cached and cached.image_path:
            img1 = cached.image_path
    p = models.PrimerInventory(brand=brand, model=model, primer_type=primer_type,
                               quantity=quantity, price_paid=price, notes=notes,
                               image_path=img1, image_path_2=img2, upc=upc,
                               is_muzzleloader=is_muzzleloader)
    db.add(p); db.commit(); db.refresh(p)
    upsert_upc_cache(db, upc, product_type="primer", brand=brand, primer_model=model, primer_type=primer_type)
    return _primer_dict(p)

@router.patch("/components/primers/{item_id}")
def patch_primer(item_id: int, payload: PrimerPatch, db: Session = Depends(get_db)):
    p = db.query(models.PrimerInventory).filter(models.PrimerInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    for k, v in payload.dict(exclude_none=True).items(): setattr(p, k, v)
    db.commit(); db.refresh(p)
    return _primer_dict(p)

@router.delete("/components/primers/{item_id}")
def delete_primer(item_id: int, db: Session = Depends(get_db)):
    p = db.query(models.PrimerInventory).filter(models.PrimerInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    cleanup_item_images(p)
    upc = getattr(p, 'upc', None)
    db.delete(p); db.commit()
    if upc:
        db.query(models.UpcCache).filter(models.UpcCache.upc == upc).delete(); db.commit()
    return {"deleted": item_id}

@router.post("/components/primers/{item_id}/update-photo/")
async def update_primer_photo(item_id: int, slot: int = Form(1), image: UploadFile = File(...), db: Session = Depends(get_db)):
    p = db.query(models.PrimerInventory).filter(models.PrimerInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    path = await save_uploaded_file(image, "component")
    if slot == 2: p.image_path_2 = path
    else: p.image_path = path
    db.commit()
    return _primer_dict(p)

@router.post("/components/primers/{item_id}/swap-photos/")
def swap_primer_photos(item_id: int, db: Session = Depends(get_db)):
    p = db.query(models.PrimerInventory).filter(models.PrimerInventory.id == item_id).first()
    if not p: raise HTTPException(404, "Not found")
    p.image_path, p.image_path_2 = p.image_path_2, p.image_path
    db.commit()
    return _primer_dict(p)


# ── Bullets ────────────────────────────────────────────────────────────────────

@router.get("/components/bullets/")
def list_bullet_components(muzzleloader: bool = Query(False), db: Session = Depends(get_db)):
    q = db.query(models.BulletInventory)
    if muzzleloader:
        q = q.filter(models.BulletInventory.is_muzzleloader == True)
    return [_bullet_dict(b) for b in q.all()]

@router.get("/components/bullets/{item_id}")
def get_bullet_component(item_id: int, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b:
        raise HTTPException(404, "Bullet not found")
    result = _bullet_dict(b)
    result["load_data"] = []
    for ld in (b.load_data_sets or []):
        result["load_data"].append({
            "id": ld.id, "source": ld.source, "caliber": ld.caliber,
            "coal": ld.coal, "primer": ld.primer, "case_type": ld.case_type,
            "case_capacity_gr": ld.case_capacity_gr, "barrel_length": ld.barrel_length,
            "barrel_twist": ld.barrel_twist, "barrel_desc": ld.barrel_desc, "notes": ld.notes,
            "entries": [{
                "id": e.id, "powder_name": e.powder_name,
                "charge_min": e.charge_min, "charge_max": e.charge_max,
                "velocity_min": e.velocity_min, "velocity_max": e.velocity_max,
                "load_density_min": e.load_density_min, "load_density_max": e.load_density_max,
                "is_max_load": e.is_max_load, "is_most_accurate": e.is_most_accurate,
            } for e in ld.entries]
        })
    return result


@router.post("/components/bullets/{item_id}/upload-datasheet/")
async def upload_bullet_datasheet(item_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    if b.datasheet_path:
        delete_uploaded_file(b.datasheet_path)
    path = await save_uploaded_document(file, "loaddata")
    b.datasheet_path = path
    db.commit()
    return _bullet_dict(b)


@router.delete("/components/bullets/{item_id}/datasheet/")
def delete_bullet_datasheet(item_id: int, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    delete_uploaded_file(b.datasheet_path)
    b.datasheet_path = None
    db.commit()
    return _bullet_dict(b)


@router.post("/components/bullets/{item_id}/load-data/")
def add_load_data(item_id: int, payload: LoadDataPatch, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Bullet not found")
    ld = models.LoadData(bullet_id=item_id, **payload.dict(exclude_unset=True))
    db.add(ld)
    db.commit()
    db.refresh(ld)
    return {"id": ld.id, "entries": []}


@router.patch("/components/bullets/{item_id}/load-data/{ld_id}")
def patch_load_data(item_id: int, ld_id: int, payload: LoadDataPatch, db: Session = Depends(get_db)):
    ld = db.query(models.LoadData).filter(models.LoadData.id == ld_id, models.LoadData.bullet_id == item_id).first()
    if not ld: raise HTTPException(404, "Load data not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(ld, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/components/bullets/{item_id}/load-data/{ld_id}")
def delete_load_data(item_id: int, ld_id: int, db: Session = Depends(get_db)):
    ld = db.query(models.LoadData).filter(models.LoadData.id == ld_id, models.LoadData.bullet_id == item_id).first()
    if not ld: raise HTTPException(404, "Not found")
    db.delete(ld)
    db.commit()
    return {"deleted": ld_id}


@router.post("/components/bullets/{item_id}/load-data/{ld_id}/entries/")
def add_load_data_entry(item_id: int, ld_id: int, payload: LoadDataEntryPayload, db: Session = Depends(get_db)):
    ld = db.query(models.LoadData).filter(models.LoadData.id == ld_id, models.LoadData.bullet_id == item_id).first()
    if not ld: raise HTTPException(404, "Load data not found")
    entry = models.LoadDataEntry(load_data_id=ld_id, **payload.dict())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id}


@router.delete("/components/bullets/{item_id}/load-data/{ld_id}/entries/{entry_id}")
def delete_load_data_entry(item_id: int, ld_id: int, entry_id: int, db: Session = Depends(get_db)):
    e = db.query(models.LoadDataEntry).filter(
        models.LoadDataEntry.id == entry_id, models.LoadDataEntry.load_data_id == ld_id
    ).first()
    if not e: raise HTTPException(404, "Entry not found")
    db.delete(e)
    db.commit()
    return {"deleted": entry_id}


@router.post("/components/bullets/")
async def add_bullet_component(
    brand: str = Form(...), caliber: str = Form(...),
    weight_gr: float = Form(...), product_line: str = Form(None),
    bullet_type: str = Form(None), bc_g1: float = Form(None),
    quantity: int = Form(0),
    qty_sealed: int = Form(0), qty_open: int = Form(0),
    price: float = Form(0.0), notes: str = Form(None), upc: str = Form(None),
    sku: str = Form(None),
    is_muzzleloader: bool = Form(False),
    image_1: UploadFile = File(None), image_2: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    img1 = await save_uploaded_file(image_1, "component")
    img2 = await save_uploaded_file(image_2, "component")
    if not img1 and upc:
        cached = db.query(models.UpcCache).filter(models.UpcCache.upc == upc).first()
        if cached and cached.image_path:
            img1 = cached.image_path
    b = models.BulletInventory(brand=brand, product_line=product_line, caliber=caliber,
                               weight_gr=weight_gr, bullet_type=bullet_type,
                               bc_g1=bc_g1, sku=(sku.strip() if sku else None),
                               quantity=quantity, qty_sealed=qty_sealed, qty_open=qty_open,
                               price_paid=price, notes=notes,
                               image_path=img1, image_path_2=img2, upc=upc,
                               is_muzzleloader=is_muzzleloader)
    db.add(b); db.commit(); db.refresh(b)
    upsert_upc_cache(db, upc, product_type="bullet", brand=brand, product_line=product_line,
                     caliber=caliber, weight_gr=weight_gr, bullet_type=bullet_type,
                     bc_g1=bc_g1)
    return _bullet_dict(b)

@router.patch("/components/bullets/{item_id}")
def patch_bullet_component(item_id: int, payload: BulletComponentPatch, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    for k, v in payload.dict(exclude_none=True).items(): setattr(b, k, v)
    db.commit(); db.refresh(b)
    return _bullet_dict(b)

@router.delete("/components/bullets/{item_id}")
def delete_bullet_component(item_id: int, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    cleanup_item_images(b)
    delete_uploaded_file(getattr(b, 'datasheet_path', None))
    upc = getattr(b, 'upc', None)
    db.delete(b); db.commit()
    if upc:
        db.query(models.UpcCache).filter(models.UpcCache.upc == upc).delete(); db.commit()
    return {"deleted": item_id}

@router.post("/components/bullets/{item_id}/update-photo/")
async def update_bullet_photo(item_id: int, slot: int = Form(1), image: UploadFile = File(...), db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    path = await save_uploaded_file(image, "component")
    if slot == 2: b.image_path_2 = path
    else: b.image_path = path
    db.commit()
    return _bullet_dict(b)

@router.post("/components/bullets/{item_id}/swap-photos/")
def swap_bullet_photos(item_id: int, db: Session = Depends(get_db)):
    b = db.query(models.BulletInventory).filter(models.BulletInventory.id == item_id).first()
    if not b: raise HTTPException(404, "Not found")
    b.image_path, b.image_path_2 = b.image_path_2, b.image_path
    db.commit()
    return _bullet_dict(b)


# ── Casings ────────────────────────────────────────────────────────────────────

@router.get("/components/casings/")
def list_casings(db: Session = Depends(get_db)):
    return [_casing_dict(c) for c in db.query(models.CasingInventory).all()]

@router.post("/components/casings/")
async def add_casing(
    brand: str = Form(...), caliber: str = Form(...),
    quantity: int = Form(0), times_fired: int = Form(0),
    price: float = Form(0.0), notes: str = Form(None), upc: str = Form(None),
    image_1: UploadFile = File(None), image_2: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    img1 = await save_uploaded_file(image_1, "component")
    img2 = await save_uploaded_file(image_2, "component")
    if not img1 and upc:
        cached = db.query(models.UpcCache).filter(models.UpcCache.upc == upc).first()
        if cached and cached.image_path:
            img1 = cached.image_path
    c = models.CasingInventory(brand=brand, caliber=caliber, quantity=quantity,
                               times_fired=times_fired, price_paid=price, notes=notes,
                               image_path=img1, image_path_2=img2, upc=upc)
    db.add(c); db.commit(); db.refresh(c)
    upsert_upc_cache(db, upc, product_type="casing", brand=brand, caliber=caliber)
    return _casing_dict(c)

@router.patch("/components/casings/{item_id}")
def patch_casing(item_id: int, payload: CasingPatch, db: Session = Depends(get_db)):
    c = db.query(models.CasingInventory).filter(models.CasingInventory.id == item_id).first()
    if not c: raise HTTPException(404, "Not found")
    for k, v in payload.dict(exclude_none=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)
    return _casing_dict(c)

@router.delete("/components/casings/{item_id}")
def delete_casing(item_id: int, db: Session = Depends(get_db)):
    c = db.query(models.CasingInventory).filter(models.CasingInventory.id == item_id).first()
    if not c: raise HTTPException(404, "Not found")
    cleanup_item_images(c)
    upc = getattr(c, 'upc', None)
    db.delete(c); db.commit()
    if upc:
        db.query(models.UpcCache).filter(models.UpcCache.upc == upc).delete(); db.commit()
    return {"deleted": item_id}

@router.post("/components/casings/{item_id}/update-photo/")
async def update_casing_photo(item_id: int, slot: int = Form(1), image: UploadFile = File(...), db: Session = Depends(get_db)):
    c = db.query(models.CasingInventory).filter(models.CasingInventory.id == item_id).first()
    if not c: raise HTTPException(404, "Not found")
    path = await save_uploaded_file(image, "component")
    if slot == 2: c.image_path_2 = path
    else: c.image_path = path
    db.commit()
    return _casing_dict(c)

@router.post("/components/casings/{item_id}/swap-photos/")
def swap_casing_photos(item_id: int, db: Session = Depends(get_db)):
    c = db.query(models.CasingInventory).filter(models.CasingInventory.id == item_id).first()
    if not c: raise HTTPException(404, "Not found")
    c.image_path, c.image_path_2 = c.image_path_2, c.image_path
    db.commit()
    return _casing_dict(c)


# ── Deduct & Low-Stock ─────────────────────────────────────────────────────────

@router.post("/components/deduct/")
def deduct_components(payload: DeductPayload, db: Session = Depends(get_db)):
    t = _get_thresholds(db)
    warnings = []

    if payload.powder_inv_id and payload.powder_charge_gr and payload.rounds_loaded:
        p = db.query(models.PowderInventory).filter(models.PowderInventory.id == payload.powder_inv_id).first()
        if p:
            p.weight_lbs = max(0.0, (p.weight_lbs or 0) - (payload.powder_charge_gr * payload.rounds_loaded / 7000))
            db.commit()
            if p.weight_lbs < t["powder_lbs"]:
                warnings.append(f"Low powder: {p.brand} {p.name} — {p.weight_lbs:.3f} lbs remaining")

    if payload.primer_inv_id and payload.rounds_loaded:
        p = db.query(models.PrimerInventory).filter(models.PrimerInventory.id == payload.primer_inv_id).first()
        if p:
            p.quantity = max(0, (p.quantity or 0) - payload.rounds_loaded)
            db.commit()
            if p.quantity < t["primers"]:
                warnings.append(f"Low primers: {p.brand} {p.primer_type} — {p.quantity} remaining")

    if payload.bullet_inv_id and payload.rounds_loaded:
        b = db.query(models.BulletInventory).filter(models.BulletInventory.id == payload.bullet_inv_id).first()
        if b:
            b.quantity = max(0, (b.quantity or 0) - payload.rounds_loaded)
            db.commit()
            if b.quantity < t["bullets"]:
                warnings.append(f"Low bullets: {b.brand} {b.caliber} {b.weight_gr}gr — {b.quantity} remaining")

    if payload.casing_inv_id and payload.rounds_loaded:
        c = db.query(models.CasingInventory).filter(models.CasingInventory.id == payload.casing_inv_id).first()
        if c:
            c.quantity = max(0, (c.quantity or 0) - payload.rounds_loaded)
            db.commit()
            if c.quantity < t["casings"]:
                warnings.append(f"Low casings: {c.brand} {c.caliber} — {c.quantity} remaining")

    return {"ok": True, "warnings": warnings}


@router.get("/components/low-stock/")
def get_low_stock(db: Session = Depends(get_db)):
    t = _get_thresholds(db)
    items = []
    for p in db.query(models.PowderInventory).all():
        if (p.weight_lbs or 0) < t["powder_lbs"]:
            items.append({"type": "powder", "label": f"{p.brand} {p.name}", "value": f"{p.weight_lbs:.3f} lbs"})
    for p in db.query(models.PrimerInventory).all():
        if (p.quantity or 0) < t["primers"]:
            items.append({"type": "primer", "label": f"{p.brand} {p.primer_type}", "value": f"{p.quantity}"})
    for b in db.query(models.BulletInventory).all():
        if (b.quantity or 0) < t["bullets"]:
            items.append({"type": "bullet", "label": f"{b.brand} {b.caliber} {b.weight_gr}gr", "value": f"{b.quantity}"})
    for c in db.query(models.CasingInventory).all():
        if (c.quantity or 0) < t["casings"]:
            items.append({"type": "casing", "label": f"{c.brand} {c.caliber}", "value": f"{c.quantity}"})
    return items
