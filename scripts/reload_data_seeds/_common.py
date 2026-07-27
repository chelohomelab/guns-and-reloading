"""Shared insert logic for hand-transcribed reload data (Hornady, and future Lyman/Lee).

These manufacturers' source material is scanned/screenshotted book pages with no reliable text
layer — OCR proved unsafe on the dense charge tables (see project memory), so the data below is
read directly off page images by a person (or Claude, reading carefully) and typed out, the same
way you'd transcribe a table by hand. This module is the shared "insert what was transcribed"
step, reused by each per-cartridge seed script under this directory.

Run any seed script directly (`.venv/bin/python scripts/reload_data_seeds/hornady_65_creedmoor.py`)
against whichever `data/reloading.db` is on that machine — this is how the transcribed data ships
to a separate deployment (e.g. production): `git pull` brings the script itself (just the
transcribed numbers, not the copyrighted source photos), then it's run once on that host.

The raw source PDF (screenshots) is optional here on purpose — `static/reloading_data/` is
gitignored (copyrighted book pages, never committed), so a fresh checkout on another machine
won't have it. If it's not found, the diagram crop and "view source PDF" link are simply skipped;
the actual load data still imports in full either way.
"""
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

import database as models  # noqa: E402
from dependencies import delete_uploaded_file  # noqa: E402
from routers.barcode import normalize_caliber  # noqa: E402

UPLOAD_DIR = "static/uploads"


def _resolve_source_pdf(path: str | None) -> str | None:
    """Prefer the flat, server-side convention (static/reloading_data/<mfr>/<file>) a script
    declares — the completed/ subfolder is a purely local dev-side habit (tracking which source
    scans have already been transcribed, so they're out of the way of ones still in progress) and
    has no meaning on a server that was never given that in-progress/done distinction. Falls back
    to the completed/ variant automatically so a script's declared path doesn't need to change the
    moment its source file gets moved into completed/ in dev.
    """
    if not path or os.path.exists(path):
        return path
    p = Path(path)
    fallback = p.parent / "completed" / p.name
    return str(fallback) if fallback.exists() else path


def _replace_existing_and_create_source(
    db, *, manufacturer, caliber_norm, spec, source_pdf_path, diagram_crop_box,
    diagram_source_page, diagram_resolution, original_filename, data_note=None,
):
    source_pdf_path = _resolve_source_pdf(source_pdf_path)
    existing = db.query(models.ReloadDataSource).filter(
        models.ReloadDataSource.manufacturer == manufacturer,
        models.ReloadDataSource.caliber == caliber_norm,
    ).all()
    for s in existing:
        if s.source_file_path:
            delete_uploaded_file(s.source_file_path)
        if s.case_diagram_path:
            delete_uploaded_file(s.case_diagram_path)
        db.delete(s)
    db.flush()

    case_diagram_path = None
    source_file_path = None
    if source_pdf_path and os.path.exists(source_pdf_path):
        if diagram_crop_box:
            try:
                import pdfplumber
                from PIL import Image
                with pdfplumber.open(source_pdf_path) as pdf:
                    im = pdf.pages[diagram_source_page].to_image(resolution=diagram_resolution).original
                cropped = im.crop(diagram_crop_box)
                diagram_filename = f"reloaddata_diagram_{uuid.uuid4()}.png"
                cropped.save(os.path.join(UPLOAD_DIR, diagram_filename))
                case_diagram_path = f"/static/uploads/{diagram_filename}"
            except Exception as e:
                print(f"[reload-data-seed] diagram crop skipped: {e}")
        source_pdf_filename = f"reloaddata_{uuid.uuid4()}.pdf"
        shutil.copy(source_pdf_path, os.path.join(UPLOAD_DIR, source_pdf_filename))
        source_file_path = f"/static/uploads/{source_pdf_filename}"
    elif source_pdf_path:
        print(f"[reload-data-seed] source PDF not found at {source_pdf_path!r} on this machine — "
              f"importing data without a diagram or 'view source' link.")

    source = models.ReloadDataSource(
        manufacturer=manufacturer, caliber=caliber_norm,
        scope_bullet_weight_gr=None, scope_bullet_model=None,
        twist=spec.get("twist"), barrel_length=spec.get("barrel_length"), trim_length=spec.get("trim_length"),
        max_saami_oal=spec.get("max_saami_oal"), max_case_length=spec.get("max_case_length"),
        rcbs_shell_holder=spec.get("rcbs_shell_holder"), test_firearm=spec.get("test_firearm"),
        data_as_of=None, original_filename=original_filename,
        source_file_path=source_file_path, case_diagram_path=case_diagram_path,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        data_note=data_note,
    )
    db.add(source)
    db.flush()
    return source


def import_hand_transcribed(
    *,
    manufacturer: str,
    caliber: str,
    spec: dict,
    sections: list[dict],
    powder_split_fn,
    source_pdf_path: str | None = None,
    diagram_crop_box: tuple[int, int, int, int] | None = None,
    diagram_source_page: int = 0,
    diagram_resolution: int = 200,
    original_filename: str | None = None,
    data_note: str | None = None,
) -> int:
    """Inserts one ReloadDataSource + its ReloadDataLoad rows from transcribed data.

    `data_note`: flags a real discrepancy in the manufacturer's own published data (not a
    transcription concern) — surfaced prominently in the UI, e.g. so it can be raised with the
    manufacturer later. Leave None for normal imports.

    For manufacturers whose tables are a **velocity matrix** (one row = powder + a single-point
    charge per target-velocity column, e.g. Hornady). For manufacturers that print a real
    starting/maximum RANGE per row instead (e.g. Lyman), use `import_hand_transcribed_range()`.

    `spec` keys: test_firearm, barrel_length, twist, max_saami_oal, max_case_length, trim_length,
    case_brand, primer_display, bullet_dia (all optional strings).

    `sections`: list of dicts with keys `sd` (float or None — None when the book prints a range
    across multiple candidates rather than one attributable value), `candidates` (list of
    (weight, model, item_no, coal, bc_g1, bc_g7) tuples), `velocities` (list of ints, ascending),
    `rows` (list of (raw_powder_name, [charges...]) — charges are left-aligned to `velocities`
    starting at index 0; the last charge in each row is the row's maximum load, matching the
    confirmed real-page convention — see module docstring / project memory).
    """
    caliber_norm = normalize_caliber(caliber)
    db = models.SessionLocal()
    source = _replace_existing_and_create_source(
        db, manufacturer=manufacturer, caliber_norm=caliber_norm, spec=spec,
        source_pdf_path=source_pdf_path, diagram_crop_box=diagram_crop_box,
        diagram_source_page=diagram_source_page, diagram_resolution=diagram_resolution,
        original_filename=original_filename, data_note=data_note,
    )

    load_rows = []
    for section in sections:
        sd = section["sd"]
        for weight, model, item_no, coal, bc_g1, bc_g7 in section["candidates"]:
            for powder_raw, charges in section["rows"]:
                powder_brand, powder_name = powder_split_fn(powder_raw)
                n = len(charges)
                for i, charge in enumerate(charges):
                    velocity = section["velocities"][i]
                    is_max = (i == n - 1)
                    load_rows.append(models.ReloadDataLoad(
                        source_id=source.id,
                        bullet_weight_gr=weight, bullet_brand=manufacturer, bullet_model=model,
                        bullet_code=item_no, bullet_dia=spec.get("bullet_dia"),
                        bullet_bc=bc_g1, bullet_bc_g7=bc_g7, bullet_sd=sd,
                        case_brand=spec.get("case_brand"), primer_display=spec.get("primer_display"),
                        powder_brand=powder_brand, powder_name=powder_name, coal=coal,
                        is_max_load=is_max,
                        start_charge_gr=charge, start_velocity_fps=velocity, start_is_compressed=False,
                        start_pressure=None, start_pressure_unit=None, start_density_pct=None,
                        max_charge_gr=charge, max_velocity_fps=velocity, max_is_compressed=False,
                        max_pressure=None, max_pressure_unit=None, max_density_pct=None,
                    ))
    db.add_all(load_rows)
    db.commit()
    count = len(load_rows)
    db.close()
    return count


def import_hand_transcribed_range(
    *,
    manufacturer: str,
    caliber: str,
    spec: dict,
    sections: list[dict],
    powder_split_fn,
    source_pdf_path: str | None = None,
    diagram_crop_box: tuple[int, int, int, int] | None = None,
    diagram_source_page: int = 0,
    diagram_resolution: int = 200,
    original_filename: str | None = None,
    data_note: str | None = None,
) -> int:
    """Inserts one ReloadDataSource + its ReloadDataLoad rows from transcribed RANGE-style data
    (Lyman-shaped: each row prints an explicit starting AND maximum charge/velocity/pressure, not
    a velocity-matrix fan-out — see `import_hand_transcribed()` for that shape instead).

    `spec` keys: same as `import_hand_transcribed()`.

    `sections`: list of dicts, one per weight-class table, with keys `weight`, `bullet_brand`,
    `model`, `item_no`, `coal`, `bc_g1`, `bc_g7`, `sd` (the actual bullet's own brand — Lyman's book
    mixes bullets from many makers, unlike Hornady's own-brand-only book, so this is NOT assumed to
    equal `manufacturer`), and `rows` (list of row dicts, each with keys: `powder` (raw name,
    already stripped of any "**" reduced-load marker), `start_gr`, `start_fps`, `start_pressure`
    (int or None), `start_pressure_unit` ("PSI"/"CUP" or None), `start_compressed` (bool), `max_gr`,
    `max_fps`, `max_pressure`, `max_pressure_unit`, `max_compressed`, `is_recommended` (bool — bold
    row = potentially most accurate), `is_reduced` (bool — "**" prefix = reduced load)).
    """
    caliber_norm = normalize_caliber(caliber)
    db = models.SessionLocal()
    source = _replace_existing_and_create_source(
        db, manufacturer=manufacturer, caliber_norm=caliber_norm, spec=spec,
        source_pdf_path=source_pdf_path, diagram_crop_box=diagram_crop_box,
        diagram_source_page=diagram_source_page, diagram_resolution=diagram_resolution,
        original_filename=original_filename, data_note=data_note,
    )

    load_rows = []
    for section in sections:
        for row in section["rows"]:
            powder_brand, powder_name = powder_split_fn(row["powder"])
            load_rows.append(models.ReloadDataLoad(
                source_id=source.id,
                bullet_weight_gr=section["weight"], bullet_brand=section["bullet_brand"],
                bullet_model=section["model"], bullet_code=section.get("item_no"),
                bullet_dia=spec.get("bullet_dia"),
                bullet_bc=section.get("bc_g1"), bullet_bc_g7=section.get("bc_g7"), bullet_sd=section.get("sd"),
                case_brand=spec.get("case_brand"), primer_display=spec.get("primer_display"),
                powder_brand=powder_brand, powder_name=powder_name, coal=section.get("coal"),
                is_recommended=row.get("is_recommended", False),
                is_reduced_load=row.get("is_reduced", False),
                start_charge_gr=row["start_gr"], start_velocity_fps=row["start_fps"],
                start_pressure=row.get("start_pressure"), start_pressure_unit=row.get("start_pressure_unit"),
                start_density_pct=None, start_is_compressed=row.get("start_compressed", False),
                max_charge_gr=row["max_gr"], max_velocity_fps=row["max_fps"],
                max_pressure=row.get("max_pressure"), max_pressure_unit=row.get("max_pressure_unit"),
                max_density_pct=None, max_is_compressed=row.get("max_compressed", False),
            ))
    db.add_all(load_rows)
    db.commit()
    count = len(load_rows)
    db.close()
    return count
