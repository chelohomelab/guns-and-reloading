import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

import database as models
import math_engine
from dependencies import get_db, save_uploaded_file

router = APIRouter()


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


@router.post("/performance-log/")
async def log_group(
    barrel_id: int = Form(...),
    ammo_id: int = Form(...),
    date: str = Form(...),
    velocities_csv: str = Form(None),
    rounds_fired: int = Form(None),
    group_size: float = Form(None),  # legacy fallback, used only when shots_json isn't sent
    shots_json: str = Form(None),  # JSON [{"x":px,"y":py,"velocity":fps|null}, ...]
    poa_x: float = Form(None),
    poa_y: float = Form(None),
    pixels_per_inch: float = Form(None),
    image_width: int = Form(None),
    image_height: int = Form(None),
    distance_yards: float = Form(None),
    target_image: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    barrel = db.query(models.Barrel).filter(models.Barrel.id == barrel_id).first()
    ammo   = db.query(models.Ammo).filter(models.Ammo.id == ammo_id).first()
    if not barrel or not ammo:
        raise HTTPException(status_code=404, detail="Barrel or Ammo profile selection invalid")

    img_path = await save_uploaded_file(target_image, "target")
    metrics  = math_engine.calculate_shot_metrics(velocities_csv)

    vel_list = [v for v in (velocities_csv or '').split(',') if v.strip()]
    actual_rounds = rounds_fired if rounds_fired is not None else len(vel_list)

    shots = []
    if shots_json:
        try:
            shots = json.loads(shots_json)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="shots_json is not valid JSON")

    poa = {"x": poa_x, "y": poa_y} if poa_x is not None and poa_y is not None else None
    geom = math_engine.calculate_group_geometry(shots, poa, pixels_per_inch, distance_yards) \
        if shots and pixels_per_inch else None

    log = models.ShotString(
        barrel_id=barrel_id,
        ammo_id=ammo_id,
        date_shot=date,
        velocities=velocities_csv,
        rounds_fired=actual_rounds,
        avg_velocity=metrics["avg"],
        extreme_spread=metrics["es"],
        standard_deviation=metrics["sd"],
        target_image_path=img_path,
        group_size_inches=geom["extreme_spread_in"] if geom else group_size,
        group_size_moa=geom["moa"] if geom else None,
        group_size_mrad=geom["mrad"] if geom else None,
        group_width_inches=geom["width_in"] if geom else None,
        group_height_inches=geom["height_in"] if geom else None,
        elevation_offset_inches=geom["elevation_offset_in"] if geom else None,
        windage_offset_inches=geom["windage_offset_in"] if geom else None,
        elevation_offset_moa=geom["elevation_offset_moa"] if geom else None,
        windage_offset_moa=geom["windage_offset_moa"] if geom else None,
        shots_json=shots_json,
        poa_x=poa_x,
        poa_y=poa_y,
        pixels_per_inch=pixels_per_inch,
        image_width=image_width,
        image_height=image_height,
        distance_yards=distance_yards,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    if actual_rounds > 0:
        _deduct_ammo_rounds(ammo, actual_rounds)
        db.commit()

    return log


@router.get("/performance-log/{log_id}")
def get_performance_log_detail(log_id: int, db: Session = Depends(get_db)):
    log = db.query(models.ShotString).filter(models.ShotString.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {
        "id": log.id, "barrel_id": log.barrel_id, "ammo_id": log.ammo_id, "date": log.date_shot,
        "velocities": log.velocities, "rounds_fired": log.rounds_fired,
        "avg_velocity": log.avg_velocity, "extreme_spread": log.extreme_spread,
        "standard_deviation": log.standard_deviation, "target_image_path": log.target_image_path,
        "group_size_inches": log.group_size_inches, "group_size_moa": log.group_size_moa,
        "group_size_mrad": log.group_size_mrad,
        "group_width_inches": log.group_width_inches, "group_height_inches": log.group_height_inches,
        "elevation_offset_inches": log.elevation_offset_inches,
        "windage_offset_inches": log.windage_offset_inches,
        "elevation_offset_moa": log.elevation_offset_moa, "windage_offset_moa": log.windage_offset_moa,
        "shots_json": log.shots_json, "poa_x": log.poa_x, "poa_y": log.poa_y,
        "pixels_per_inch": log.pixels_per_inch,
        "image_width": log.image_width, "image_height": log.image_height,
        "distance_yards": log.distance_yards,
    }


@router.delete("/performance-log/{log_id}")
def delete_performance_log(log_id: int, db: Session = Depends(get_db)):
    log = db.query(models.ShotString).filter(models.ShotString.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    db.delete(log)
    db.commit()
    return {"deleted": log_id}


@router.get("/performance-log/ammo/{ammo_id}")
def get_logs_for_ammo(ammo_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(models.ShotString)
        .options(joinedload(models.ShotString.barrel).joinedload(models.Barrel.firearm))
        .filter(models.ShotString.ammo_id == ammo_id)
        .order_by(models.ShotString.date_shot.desc())
        .all()
    )
    result = []
    for s in logs:
        firearm = s.barrel.firearm if s.barrel else None
        vel_list = [float(v) for v in s.velocities.split(",") if v.strip()] if s.velocities else []
        result.append({
            "id": s.id,
            "date": s.date_shot,
            "firearm_name": f"{firearm.brand} {firearm.model}" if firearm else "Unknown",
            "firearm_id": firearm.id if firearm else None,
            "caliber": s.barrel.caliber if s.barrel else "—",
            "shots": s.rounds_fired or len(vel_list),
            "avg_velocity": s.avg_velocity,
            "group_size_inches": s.group_size_inches,
            "group_size_moa": s.group_size_moa, "group_size_mrad": s.group_size_mrad,
            "group_width_inches": s.group_width_inches, "group_height_inches": s.group_height_inches,
            "distance_yards": s.distance_yards,
            "elevation_offset_inches": s.elevation_offset_inches,
            "windage_offset_inches": s.windage_offset_inches,
            "elevation_offset_moa": s.elevation_offset_moa, "windage_offset_moa": s.windage_offset_moa,
            "target_image_path": s.target_image_path,
        })
    return result


@router.get("/performance-log/tc-barrel/{barrel_id}")
def get_logs_for_tc_barrel(barrel_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(models.ShotString)
        .options(joinedload(models.ShotString.ammo), joinedload(models.ShotString.barrel))
        .filter(models.ShotString.barrel_id == barrel_id)
        .order_by(models.ShotString.date_shot.desc())
        .all()
    )
    result = []
    for s in logs:
        vel_list = [float(v) for v in s.velocities.split(",") if v.strip()] if s.velocities else []
        result.append({
            "id": s.id,
            "date": s.date_shot,
            "barrel_name": (s.barrel.name or s.barrel.caliber) if s.barrel else "—",
            "caliber": s.barrel.caliber if s.barrel else "—",
            "load_name": f"{s.ammo.brand} {s.ammo.line_or_powder or ''} {s.ammo.bullet_weight}gr".strip(),
            "bullet_bc": getattr(s.ammo, "bullet_bc", None),
            "shots": s.rounds_fired or len(vel_list),
            "avg_velocity": s.avg_velocity,
            "extreme_spread": s.extreme_spread,
            "standard_deviation": s.standard_deviation,
            "group_size_inches": s.group_size_inches,
            "group_size_moa": s.group_size_moa, "group_size_mrad": s.group_size_mrad,
            "group_width_inches": s.group_width_inches, "group_height_inches": s.group_height_inches,
            "distance_yards": s.distance_yards,
            "elevation_offset_inches": s.elevation_offset_inches,
            "windage_offset_inches": s.windage_offset_inches,
            "elevation_offset_moa": s.elevation_offset_moa, "windage_offset_moa": s.windage_offset_moa,
            "target_image_path": s.target_image_path,
        })
    return result


@router.get("/performance-log/firearm/{firearm_id}")
def get_logs_for_firearm(firearm_id: int, db: Session = Depends(get_db)):
    barrels = db.query(models.Barrel).filter(models.Barrel.firearm_id == firearm_id).all()
    barrel_ids = [b.id for b in barrels]
    if not barrel_ids:
        return []
    logs = (
        db.query(models.ShotString)
        .options(joinedload(models.ShotString.ammo), joinedload(models.ShotString.barrel))
        .filter(models.ShotString.barrel_id.in_(barrel_ids))
        .order_by(models.ShotString.date_shot.desc())
        .all()
    )
    result = []
    for s in logs:
        vel_list = [float(v) for v in s.velocities.split(",") if v.strip()] if s.velocities else []
        result.append({
            "id": s.id,
            "date": s.date_shot,
            "barrel_name": s.barrel.name or s.barrel.caliber,
            "caliber": s.barrel.caliber,
            "load_name": f"{s.ammo.brand} {s.ammo.line_or_powder or ''} {s.ammo.bullet_weight}gr".strip(),
            "bullet_bc": getattr(s.ammo, "bullet_bc", None),
            "shots": s.rounds_fired or len(vel_list),
            "avg_velocity": s.avg_velocity,
            "extreme_spread": s.extreme_spread,
            "standard_deviation": s.standard_deviation,
            "group_size_inches": s.group_size_inches,
            "group_size_moa": s.group_size_moa, "group_size_mrad": s.group_size_mrad,
            "group_width_inches": s.group_width_inches, "group_height_inches": s.group_height_inches,
            "distance_yards": s.distance_yards,
            "elevation_offset_inches": s.elevation_offset_inches,
            "windage_offset_inches": s.windage_offset_inches,
            "elevation_offset_moa": s.elevation_offset_moa, "windage_offset_moa": s.windage_offset_moa,
            "target_image_path": s.target_image_path,
        })
    return result
