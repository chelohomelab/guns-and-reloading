from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

import database as models
from dependencies import get_db

router = APIRouter()

GAME_TYPES = ["Deer", "Black Bear", "Elk", "Turkey", "Upland Birds", "Small Game", "Migratory Birds", "Trapping"]


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


@router.post("/hunting/states")
def add_hunting_state(
    name: str = Form(...),
    abbreviation: str = Form(None),
    db: Session = Depends(get_db),
):
    max_order = db.query(models.HuntingState).count()
    state = models.HuntingState(name=name.strip(), abbreviation=(abbreviation or "").strip() or None, display_order=max_order)
    db.add(state)
    db.commit()
    db.refresh(state)
    return _state_dict(state)


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
