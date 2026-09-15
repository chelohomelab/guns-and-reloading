import subprocess
import sys

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import database as models
from config import templates
from dependencies import get_db
from paths import BASE_DIR

router = APIRouter()

GAME_TYPES = ["Deer", "Black Bear", "Elk", "Turkey", "Upland Birds", "Small Game", "Migratory Birds", "Trapping"]

# One hand-transcribed seed script per state under scripts/hunting_data_seeds/ — each wipes and
# re-inserts just that state's rows, so it's safe to re-run (e.g. after a season's data is fixed).
SEED_STATES = {
    "nj": "New Jersey",
    "pa": "Pennsylvania",
    "ny": "New York",
    "va": "Virginia",
    "de": "Delaware",
    "md": "Maryland",
}


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


def _state_dict(s: models.HuntingState) -> dict:
    return {"id": s.id, "name": s.name, "abbreviation": s.abbreviation, "display_order": s.display_order}


def _season_dict(e: models.HuntingSeasonEntry) -> dict:
    return {
        "id": e.id,
        "season_year_label": e.season_year_label,
        "game_type": e.game_type,
        "species": e.species,
        "season_label": e.season_label,
        "weapon": e.weapon,
        "zone_or_area": e.zone_or_area,
        "start_date": e.start_date,
        "end_date": e.end_date,
        "weekday_filter": e.weekday_filter,
        "bag_limit": e.bag_limit,
        "notes": e.notes,
    }


def _note_dict(n: models.HuntingRegulationNote) -> dict:
    return {"id": n.id, "game_type": n.game_type, "title": n.title, "body": n.body}


@router.get("/hunting/states")
def list_hunting_states(db: Session = Depends(get_db)):
    states = db.query(models.HuntingState).order_by(models.HuntingState.display_order, models.HuntingState.name).all()
    return [_state_dict(s) for s in states]



@router.delete("/hunting/states/{state_id}")
def delete_hunting_state(state_id: int, db: Session = Depends(get_db)):
    state = db.query(models.HuntingState).filter(models.HuntingState.id == state_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    db.delete(state)
    db.commit()
    return {"ok": True}


@router.get("/hunting/states/{state_id}/seasons")
def list_hunting_seasons(state_id: int, game_type: str = None, db: Session = Depends(get_db)):
    q = db.query(models.HuntingSeasonEntry).filter(models.HuntingSeasonEntry.state_id == state_id)
    if game_type:
        q = q.filter(models.HuntingSeasonEntry.game_type == game_type)
    entries = q.order_by(models.HuntingSeasonEntry.display_order, models.HuntingSeasonEntry.start_date).all()
    return [_season_dict(e) for e in entries]


@router.get("/hunting/states/{state_id}/regulations")
def list_hunting_regulations(state_id: int, game_type: str = None, db: Session = Depends(get_db)):
    q = db.query(models.HuntingRegulationNote).filter(models.HuntingRegulationNote.state_id == state_id)
    if game_type:
        q = q.filter(models.HuntingRegulationNote.game_type == game_type)
    else:
        q = q.filter(models.HuntingRegulationNote.game_type.is_(None))
    notes = q.order_by(models.HuntingRegulationNote.display_order).all()
    return [_note_dict(n) for n in notes]


@router.get("/hunting/states/{state_id}/game-types")
def list_hunting_game_types(state_id: int, db: Session = Depends(get_db)):
    rows = db.query(models.HuntingSeasonEntry.game_type).filter(models.HuntingSeasonEntry.state_id == state_id).distinct().all()
    present = {r[0] for r in rows}
    return [g for g in GAME_TYPES if g in present]


# ── Admin: seed hand-transcribed state data ─────────────────────────────────

@router.get("/admin/hunting", response_class=HTMLResponse)
async def admin_hunting_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("admin_hunting.html", {
        "request": request,
        "user": request.state.user,
        "seed_states": SEED_STATES,
    })


@router.post("/admin/hunting/seed/{slug}")
def admin_hunting_seed(slug: str, request: Request):
    _require_admin(request)
    state_name = SEED_STATES.get(slug)
    if not state_name:
        raise HTTPException(status_code=404, detail=f"Unknown state slug: {slug}")

    script_path = BASE_DIR / "scripts" / "hunting_data_seeds" / f"{slug}_hunting.py"
    if not script_path.is_file():
        raise HTTPException(status_code=404, detail=f"Seed script not found: {script_path.name}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Seeding {state_name} timed out after 60s")

    return {
        "ok": result.returncode == 0,
        "state": state_name,
        "slug": slug,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
