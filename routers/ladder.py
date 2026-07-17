from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import database as models
import math_engine
from dependencies import get_db
from schemas import (
    LadderTestPayload, LadderTestPatch, LadderTestStepPayload, LadderTestStepPatch, TestPlatformPayload,
    DeductPayload,
)
from routers.components import deduct_components

router = APIRouter()


def _deduct_for_ladder_rounds(db: Session, t: models.LadderTest, step: models.LadderTestStep, rounds: int) -> list:
    # Reloaders load every round of a ladder at the bench before ever firing a shot, so the
    # components are actually used the moment the rounds are loaded — not later when a chrono
    # reading gets typed in. Deduction therefore happens once, at the point a step's rounds are
    # committed to (ladder creation for the auto-generated range, or add-step for a one-off extra
    # charge) — never when merely editing/recording velocities for rounds already accounted for.
    # Each step's own charge_weight is used for powder, since a ladder burns a different amount
    # at every rung (unlike a flat handload charge).
    if not rounds or rounds <= 0:
        return []
    payload = DeductPayload(
        rounds_loaded=rounds,
        powder_charge_gr=step.charge_weight,
        powder_inv_id=t.powder_inv_id,
        primer_inv_id=t.primer_inv_id,
        bullet_inv_id=t.bullet_id,
        casing_inv_id=t.casing_inv_id,
    )
    result = deduct_components(payload, db)
    return result.get("warnings", [])


def _dedupe_warnings_keep_last(items: list) -> list:
    # Deducting several steps in one creation call can trigger the same "low X" warning
    # repeatedly with a shrinking remaining-count each time — keep only the most current
    # (last) message per component category, in first-seen order.
    order = []
    latest = {}
    for w in items:
        key = w.split(':', 1)[0]
        if key not in latest:
            order.append(key)
        latest[key] = w
    return [latest[k] for k in order]


def _bullet_label(b: "models.BulletInventory | None") -> str:
    if not b:
        return "—"
    return f"{b.brand} {b.weight_gr}gr {b.bullet_type or ''}".replace("  ", " ").strip()


def _platform_label(t: models.LadderTest) -> "str | None":
    if t.platform:
        return t.platform.name
    if t.barrel:
        if t.barrel.tc_platform:
            return f"{t.barrel.tc_platform} {t.barrel.caliber or ''}".strip()
        if t.barrel.firearm:
            return f"{t.barrel.firearm.brand} {t.barrel.firearm.model}".strip()
        return t.barrel.caliber
    return None


def _test_platform_dict(p: models.TestPlatform) -> dict:
    return {
        "id": p.id, "name": p.name, "caliber": p.caliber,
        "barrel_length": p.barrel_length, "barrel_twist": p.barrel_twist, "notes": p.notes,
    }


def _ladder_test_summary(t: models.LadderTest) -> dict:
    charges = [s.charge_weight for s in t.steps]
    return {
        "id": t.id,
        "name": t.name,
        "caliber": t.caliber,
        "bullet_id": t.bullet_id,
        "bullet_label": _bullet_label(t.bullet),
        "powder_name": t.powder_name,
        "step_count": len(t.steps),
        "charge_min": min(charges) if charges else None,
        "charge_max": max(charges) if charges else None,
        "charge_start": t.charge_start,
        "charge_end": t.charge_end,
        "charge_increment": t.charge_increment,
        "rounds_per_step": t.rounds_per_step,
        "barrel_id": t.barrel_id,
        "platform_id": t.platform_id,
        "platform_label": _platform_label(t),
        "has_winner": any(s.is_winner for s in t.steps),
        "date_started": t.date_started,
        "created_at": t.created_at,
    }


def _ladder_step_dict(s: models.LadderTestStep) -> dict:
    return {
        "id": s.id,
        "ladder_test_id": s.ladder_test_id,
        "charge_weight": s.charge_weight,
        "velocities": s.velocities,
        "rounds_fired": s.rounds_fired,
        "avg_velocity": s.avg_velocity,
        "extreme_spread": s.extreme_spread,
        "standard_deviation": s.standard_deviation,
        "is_winner": s.is_winner,
        "date_shot": s.date_shot,
        "notes": s.notes,
    }


def _ladder_test_detail(t: models.LadderTest) -> dict:
    result = _ladder_test_summary(t)
    result["primer"] = t.primer
    result["case_type"] = t.case_type
    result["coal"] = t.coal
    result["notes"] = t.notes
    result["bullet"] = {
        "id": t.bullet.id, "brand": t.bullet.brand, "product_line": t.bullet.product_line,
        "caliber": t.bullet.caliber, "weight_gr": t.bullet.weight_gr,
        "bullet_type": t.bullet.bullet_type, "bc_g1": t.bullet.bc_g1,
    } if t.bullet else None
    result["steps"] = [_ladder_step_dict(s) for s in t.steps]
    return result


@router.get("/ladder-tests/")
def list_ladder_tests(db: Session = Depends(get_db)):
    tests = (
        db.query(models.LadderTest)
        .options(joinedload(models.LadderTest.bullet), joinedload(models.LadderTest.steps),
                 joinedload(models.LadderTest.barrel).joinedload(models.Barrel.firearm),
                 joinedload(models.LadderTest.platform))
        .order_by(models.LadderTest.created_at.desc())
        .all()
    )
    return [_ladder_test_summary(t) for t in tests]


def _generate_charge_weights(start: float, end: float, increment: float) -> list[float]:
    if increment <= 0:
        raise HTTPException(400, "Increment must be greater than 0")
    if end < start:
        raise HTTPException(400, "End charge must be >= start charge")
    charges = []
    c = start
    while c <= end + 1e-6:
        charges.append(round(c, 3))
        c += increment
    if len(charges) > 50:
        raise HTTPException(400, "That range/increment produces more than 50 steps — widen the increment")
    return charges


@router.post("/ladder-tests/")
def create_ladder_test(payload: LadderTestPayload, db: Session = Depends(get_db)):
    bullet = db.query(models.BulletInventory).filter(models.BulletInventory.id == payload.bullet_id).first()
    if not bullet:
        raise HTTPException(404, "Bullet not found")

    # Validate/compute the charge ladder before touching the DB, so a bad range
    # never leaves behind an orphaned test with zero steps.
    charge_weights = []
    if payload.charge_start is not None and payload.charge_end is not None and payload.charge_increment is not None:
        charge_weights = _generate_charge_weights(payload.charge_start, payload.charge_end, payload.charge_increment)
        # Enforced server-side (not just in the form) so a stale client, or a request made any
        # other way, can never silently create a ladder with steps but no rounds_per_step —
        # which would create steps while quietly deducting nothing from inventory.
        if not payload.rounds_per_step or payload.rounds_per_step <= 0:
            raise HTTPException(400, "Rounds per step is required to auto-generate a charge ladder")

    t = models.LadderTest(
        **payload.dict(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(t)
    db.flush()
    new_steps = []
    for cw in charge_weights:
        step = models.LadderTestStep(ladder_test_id=t.id, charge_weight=cw)
        db.add(step)
        new_steps.append(step)
    db.commit()
    db.refresh(t)
    for step in new_steps:
        db.refresh(step)

    # The rounds for every generated step were loaded (and their components used) right now, at
    # creation — not later when velocities get recorded. See _deduct_for_ladder_rounds.
    warnings = []
    for step in new_steps:
        warnings.extend(_deduct_for_ladder_rounds(db, t, step, payload.rounds_per_step or 0))
    warnings = _dedupe_warnings_keep_last(warnings)

    result = _ladder_test_detail(t)
    result["warnings"] = warnings
    return result


@router.get("/ladder-tests/{test_id}")
def get_ladder_test(test_id: int, db: Session = Depends(get_db)):
    t = (
        db.query(models.LadderTest)
        .options(joinedload(models.LadderTest.bullet), joinedload(models.LadderTest.steps),
                 joinedload(models.LadderTest.barrel).joinedload(models.Barrel.firearm),
                 joinedload(models.LadderTest.platform))
        .filter(models.LadderTest.id == test_id)
        .first()
    )
    if not t:
        raise HTTPException(404, "Ladder test not found")
    return _ladder_test_detail(t)


@router.patch("/ladder-tests/{test_id}")
def patch_ladder_test(test_id: int, payload: LadderTestPatch, db: Session = Depends(get_db)):
    t = db.query(models.LadderTest).filter(models.LadderTest.id == test_id).first()
    if not t:
        raise HTTPException(404, "Ladder test not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return _ladder_test_detail(t)


@router.delete("/ladder-tests/{test_id}")
def delete_ladder_test(test_id: int, db: Session = Depends(get_db)):
    t = db.query(models.LadderTest).filter(models.LadderTest.id == test_id).first()
    if not t:
        raise HTTPException(404, "Ladder test not found")
    db.delete(t)
    db.commit()
    return {"deleted": test_id}


@router.post("/ladder-tests/{test_id}/steps/")
def add_ladder_step(test_id: int, payload: LadderTestStepPayload, db: Session = Depends(get_db)):
    t = db.query(models.LadderTest).filter(models.LadderTest.id == test_id).first()
    if not t:
        raise HTTPException(404, "Ladder test not found")
    vel_list = [v for v in (payload.velocities_csv or '').split(',') if v.strip()]
    rounds_fired = payload.rounds_fired if payload.rounds_fired is not None else len(vel_list)
    # calculate_shot_metrics always returns numeric 0.0s, never None — only compute when there's
    # actually velocity data, otherwise a legitimate 0.0 ES/SD (e.g. a single-shot reading) would
    # get lost. Falling back to `metrics["es"] or None` was the bug: `0.0 or None` is None in
    # Python, so a real (correct) zero ES/SD silently displayed as blank instead of "0.0".
    metrics = math_engine.calculate_shot_metrics(payload.velocities_csv) if vel_list else None
    step = models.LadderTestStep(
        ladder_test_id=test_id,
        charge_weight=payload.charge_weight,
        velocities=payload.velocities_csv,
        rounds_fired=rounds_fired,
        avg_velocity=metrics["avg"] if metrics else None,
        extreme_spread=metrics["es"] if metrics else None,
        standard_deviation=metrics["sd"] if metrics else None,
        date_shot=payload.date_shot,
        notes=payload.notes,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    # A manually-added extra charge step is loaded and fired in one go (charge + velocities
    # submitted together), so its full rounds_fired is newly-used rounds — deduct now.
    warnings = _deduct_for_ladder_rounds(db, t, step, step.rounds_fired or 0)
    result = _ladder_step_dict(step)
    result["warnings"] = warnings
    return result


@router.patch("/ladder-tests/{test_id}/steps/{step_id}")
def patch_ladder_step(test_id: int, step_id: int, payload: LadderTestStepPatch, db: Session = Depends(get_db)):
    step = db.query(models.LadderTestStep).filter(
        models.LadderTestStep.id == step_id, models.LadderTestStep.ladder_test_id == test_id
    ).first()
    if not step:
        raise HTTPException(404, "Step not found")
    data = payload.dict(exclude_unset=True)
    if "velocities_csv" in data:
        velocities_csv = data.pop("velocities_csv")
        step.velocities = velocities_csv
        vel_list = [v for v in (velocities_csv or '').split(',') if v.strip()]
        metrics = math_engine.calculate_shot_metrics(velocities_csv) if vel_list else None
        step.avg_velocity = metrics["avg"] if metrics else None
        step.extreme_spread = metrics["es"] if metrics else None
        step.standard_deviation = metrics["sd"] if metrics else None
        if "rounds_fired" not in data:
            step.rounds_fired = len(vel_list)
    for k, v in data.items():
        setattr(step, k, v)
    db.commit()
    db.refresh(step)
    # No deduction here: this step's rounds were already loaded (and components deducted) either
    # in bulk at ladder-test creation or when the step itself was added — recording/editing
    # velocities here is just chrono data entry for rounds already accounted for.
    return _ladder_step_dict(step)


@router.delete("/ladder-tests/{test_id}/steps/{step_id}")
def delete_ladder_step(test_id: int, step_id: int, db: Session = Depends(get_db)):
    step = db.query(models.LadderTestStep).filter(
        models.LadderTestStep.id == step_id, models.LadderTestStep.ladder_test_id == test_id
    ).first()
    if not step:
        raise HTTPException(404, "Step not found")
    db.delete(step)
    db.commit()
    return {"deleted": step_id}


@router.post("/ladder-tests/{test_id}/steps/{step_id}/toggle-winner")
def toggle_ladder_winner(test_id: int, step_id: int, db: Session = Depends(get_db)):
    t = (
        db.query(models.LadderTest)
        .options(joinedload(models.LadderTest.bullet), joinedload(models.LadderTest.steps),
                 joinedload(models.LadderTest.barrel).joinedload(models.Barrel.firearm),
                 joinedload(models.LadderTest.platform))
        .filter(models.LadderTest.id == test_id)
        .first()
    )
    if not t:
        raise HTTPException(404, "Ladder test not found")
    target = next((s for s in t.steps if s.id == step_id), None)
    if not target:
        raise HTTPException(404, "Step not found")
    # A ladder can show more than one flat "node" worth following up on, so marking a step
    # toggles that step only — it doesn't clear other steps' flags.
    target.is_winner = not target.is_winner
    db.commit()
    db.refresh(t)
    return _ladder_test_detail(t)


@router.get("/test-platforms/")
def list_test_platforms(db: Session = Depends(get_db)):
    platforms = db.query(models.TestPlatform).order_by(models.TestPlatform.name).all()
    return [_test_platform_dict(p) for p in platforms]


@router.post("/test-platforms/")
def create_test_platform(payload: TestPlatformPayload, db: Session = Depends(get_db)):
    p = models.TestPlatform(**payload.dict(), created_at=datetime.now(timezone.utc).isoformat())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _test_platform_dict(p)
