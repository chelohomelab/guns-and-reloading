import re
from datetime import datetime, timezone

import pdfplumber
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import database as models
from dependencies import get_db, save_uploaded_document, delete_uploaded_file
from routers.barcode import normalize_caliber

router = APIRouter()


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


# ── Hodgdon "Reloading Data Center" PDF parsing ─────────────────────────────────
# Hodgdon's export renders as a comma-delimited table inside the PDF's text layer, not a
# scanned image or a ruled table — but a naive split(',') is unsafe: thousands-separator
# commas inside numbers ("3,482") and an embedded comma inside the Primer field itself
# ("Winchester LR, Large Rifle") both add extra commas beyond the 15 logical columns. The
# parser below merges thousands-separators first, then matches each line against a single
# regex anchored on literal landmarks already present in the data (closing quotes, %, PSI/
# CUP, optional trailing "C" for a compressed load) — a line either matches the full
# expected shape or gets rejected outright, never silently reassembled by column position.

_THOUSANDS_RE = re.compile(r'(\d),(\d{3})')

_ROW_RE = re.compile(r'''
    ^(?P<bullet>.+?)\s*,
    (?P<dia>\d+(?:\.\d+)?)"\s*,
    (?P<case>[^,]+?)\s*,
    (?P<primer>.+?,.+?)\s*,
    (?P<powder_brand>[^,]+?)\s*,
    (?P<powder_name>[^,]+?)\s*,
    (?P<col>\d+(?:\.\d+)?)"\s*,
    (?P<st_gns>\d+(?:\.\d+)?)?(?P<st_c>C)?\*?\s*,
    (?P<st_vel>\d+)?\s*,
    (?:(?P<st_prs>\d+)\s*(?P<st_unit>PSI|CUP))?\s*,
    (?:(?P<st_dns>\d+(?:\.\d+)?)%|N/A)\s*,
    (?P<mx_gns>\d+(?:\.\d+)?)(?P<mx_c>C)?\*?\s*,
    (?P<mx_vel>\d+)\s*,
    (?:(?P<mx_prs>\d+)\s*(?P<mx_unit>PSI|CUP))?\s*,
    (?:(?P<mx_dns>\d+(?:\.\d+)?)%|N/A)\s*$
''', re.VERBOSE | re.IGNORECASE)

_BULLET_RE = re.compile(r'^(?P<weight>\d+(?:\.\d+)?)\s*GR\.\s*(?P<brand_abbr>[A-Z]+)\s+(?P<model>.+)$', re.IGNORECASE)

# Grown as new calibers surface new abbreviations — see project_midwayusa_import_architecture
# memory for why an unknown abbreviation must degrade gracefully (store raw text, skip
# matching) rather than guess.
_BULLET_BRAND_ABBR = {
    'BAR': 'Barnes', 'SIE': 'Sierra', 'HDY': 'Hornady', 'SPR': 'Speer',
    'NOS': 'Nosler', 'BER': 'Berger', 'SFT': 'Swift',
    'LY': 'Lyman', 'LYM': 'Lyman', 'CEB': 'Cutting Edge Bullets',
}


def _merge_thousands(line: str) -> str:
    prev = None
    while prev != line:
        prev = line
        line = _THOUSANDS_RE.sub(r'\1\2', line)
    return line


def _parse_bullet_field(raw: str) -> dict:
    m = _BULLET_RE.match(raw.strip())
    if not m:
        return {"weight_gr": None, "brand": None, "model": raw.strip()}
    abbr = m.group('brand_abbr').upper()
    return {
        "weight_gr": float(m.group('weight')),
        "brand": _BULLET_BRAND_ABBR.get(abbr, abbr),
        "model": m.group('model').strip(),
    }


def _parse_row(line: str) -> dict | None:
    m = _ROW_RE.match(_merge_thousands(line))
    if not m:
        return None
    d = m.groupdict()
    bullet = _parse_bullet_field(d['bullet'])
    # Some rows (e.g. single-charge "Superformance" reference loads) publish only a max
    # charge — Hodgdon marks the whole starting side blank/"0"/"N/A" rather than a real
    # range. A blank St Gns is the reliable signal "no starting load documented here";
    # when that's the case, treat the entire starting side as unknown (None) rather than
    # trust a leftover "0" in St Vel, which is a placeholder, not a real 0 fps reading.
    has_start = d['st_gns'] is not None
    return {
        "bullet_weight_gr": bullet["weight_gr"],
        "bullet_brand": bullet["brand"],
        "bullet_model": bullet["model"],
        "bullet_dia": d['dia'],
        "case_brand": d['case'].strip(),
        "primer_display": d['primer'].strip(),
        "powder_brand": d['powder_brand'].strip(),
        "powder_name": d['powder_name'].strip(),
        "coal": d['col'],
        "start_charge_gr": float(d['st_gns']) if has_start else None,
        "start_is_compressed": bool(d['st_c']) if has_start else False,
        "start_velocity_fps": int(d['st_vel']) if has_start and d['st_vel'] else None,
        "start_pressure": int(d['st_prs']) if has_start and d['st_prs'] else None,
        "start_pressure_unit": d['st_unit'] if has_start else None,
        "start_density_pct": float(d['st_dns']) if has_start and d['st_dns'] else None,
        "max_charge_gr": float(d['mx_gns']),
        "max_is_compressed": bool(d['mx_c']),
        "max_velocity_fps": int(d['mx_vel']),
        # A few reference loads (cast-bullet/Lyman "LY FN GC" style, and the occasional
        # very-low-charge specialty load) genuinely have no maximum pressure recorded at
        # all — Hodgdon just leaves it blank rather than omitting the row.
        "max_pressure": int(d['mx_prs']) if d['mx_prs'] else None,
        "max_pressure_unit": d['mx_unit'] if d['mx_unit'] else None,
        "max_density_pct": float(d['mx_dns']) if d['mx_dns'] else None,
    }


def _classify_context_line(line: str, state: dict) -> bool:
    """True if `line` was a header/context/glossary line (consumed into `state` or simply
    skipped) rather than a data row. Mutates `state` in place.
    """
    if not line.strip():
        return True
    if line.startswith("Data current as of"):
        if state.get("data_as_of") is None:
            state["data_as_of"] = line.replace("Data current as of", "").strip()
        return True
    if line.startswith("Reloading Data Center"):
        return True
    if line.startswith("Twist:"):
        m = re.match(r'Twist:\s*(\S+)\s*\|\s*Barrel Length:\s*([\d.]+)"\s*\|\s*Trim Length:\s*([\d.]+)"', line)
        if m:
            state["twist"], state["barrel_length"], state["trim_length"] = m.groups()
        return True
    if line.startswith("Your search returned"):
        return True
    if line.startswith("Bullet ,Dia"):
        return True
    if line.strip() == "Dns":
        # The header row itself sometimes wraps ("...,Mx" / "Dns") on narrower layouts
        # (e.g. calibers with a long primer column like "Large Rifle Magnum") — this is
        # just the tail of the header, not data.
        return True
    if line.strip() == "---" or line.strip() == "Glossary":
        state["in_glossary"] = True
        return True
    if state.get("in_glossary"):
        return True
    if "," not in line and state.get("caliber") is None:
        state["caliber"] = line.strip()
        return True
    return False


def parse_hodgdon_pdf(pdf_bytes: bytes) -> dict:
    """Returns {"caliber", "twist", "barrel_length", "trim_length", "data_as_of",
    "rows": [dict, ...], "rejected_lines": [str, ...]}. Never raises on a malformed line —
    a line that doesn't match the expected shape is collected in "rejected_lines" instead
    of being guessed into place.
    """
    import io
    state: dict = {}
    rows: list[dict] = []
    rejected: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    lines = [raw_line.rstrip() for raw_line in text.split("\n")]
    i = 0
    while i < len(lines):
        line = lines[i]
        if _classify_context_line(line, state):
            i += 1
            continue
        row = _parse_row(line)
        if row is None:
            # Some calibers have a long enough Primer column (e.g. "Large Rifle Magnum")
            # that the PDF's row width wraps the last field(s) onto the next physical
            # line — this is purely a rendering artifact, the logical row is still one
            # record. The true continuation is usually the very next line, but if this
            # row happened to fall right at a page break, the next page's own repeating
            # "Data current as of ..." header lands in between — skip over any of those
            # before looking for the continuation. Only keep a merge if the combined
            # text actually satisfies the full row shape (never guess one that doesn't).
            j = i + 1
            while j < len(lines) and lines[j].startswith("Data current as of"):
                j += 1
            if j < len(lines):
                merged_row = _parse_row(f"{line} {lines[j]}")
                if merged_row is not None:
                    rows.append(merged_row)
                    i = j + 1
                    continue
        if row is None:
            rejected.append(line)
        else:
            rows.append(row)
        i += 1
    return {
        "caliber": normalize_caliber(state.get("caliber")) or state.get("caliber"),
        "twist": state.get("twist"),
        "barrel_length": state.get("barrel_length"),
        "trim_length": state.get("trim_length"),
        "data_as_of": state.get("data_as_of"),
        "rows": rows,
        "rejected_lines": rejected,
    }


# ── Serializers ──────────────────────────────────────────────────────────────

def _source_summary(s: "models.ReloadDataSource") -> dict:
    return {
        "id": s.id, "caliber": s.caliber, "twist": s.twist,
        "barrel_length": s.barrel_length, "trim_length": s.trim_length,
        "data_as_of": s.data_as_of, "original_filename": s.original_filename,
        "uploaded_at": s.uploaded_at, "row_count": len(s.loads),
    }


def _normalize_bore_dia(raw: str | None) -> str | None:
    """BulletInventory.caliber stores bore diameter as e.g. ".308" (see
    project_caliber_normalization memory — bore-diameter values are deliberately never run
    through the cartridge-name normalizer). ReloadDataLoad.bullet_dia stores the same value
    as e.g. "0.308" (straight from the PDF's Dia column). Normalize both to the same bare
    fractional form (".308") so they compare equal — without this, two completely different
    calibers that happen to share a bullet weight (e.g. a 130gr .277 bullet and a 130gr .308
    bullet) would silently look like the same bullet.
    """
    if not raw:
        return None
    s = raw.strip()
    m = re.match(r'^0?(\.\d+)$', s)
    return m.group(1) if m else s.lower()


def _normalize_model_token(raw: str | None) -> str | None:
    """Lowercase and strip spaces/hyphens so "ELD-M", "ELD M", and "eld-m" all compare
    equal. Deliberately does NOT attempt anything fuzzier than that — e.g. Hodgdon's
    "HPBT-SMK" abbreviation for a Sierra MatchKing bullet will NOT match a user's inventory
    row labeled "MatchKing", and that's intentional: guessing that those are the same
    bullet is exactly the kind of cross-model guess that caused the in-stock badge to
    wrongly claim a Hornady BTHP was a Hornady ELD-M (same brand/weight/caliber, different
    bullet). A missed real match just shows as "not in stock" — safe. A wrong match claims
    the user owns a specific bullet they don't — not safe.
    """
    if not raw:
        return None
    return re.sub(r'[\s\-]+', '', raw.strip().lower()) or None


def _load_dict(l: "models.ReloadDataLoad", in_stock_powders: set, in_stock_bullets: dict) -> dict:
    powder_key = ((l.powder_brand or "").strip().lower(), (l.powder_name or "").strip().lower())
    base_key = (
        (l.bullet_brand or "").strip().lower(),
        (l.bullet_weight_gr or 0),
        _normalize_bore_dia(l.bullet_dia),
    )
    exact_key = base_key + (_normalize_model_token(l.bullet_model),)
    # Exact brand+weight+caliber+model match → confidently "in stock". If only
    # brand+weight+caliber match but the model text differs (e.g. Hodgdon's "HPBT-SMK" vs.
    # your inventory's "MatchKing"), don't guess either way — surface what you actually
    # own so you can judge for yourself whether it's the same bullet.
    bullet_in_stock = exact_key in in_stock_bullets["exact"]
    bullet_owned_model = None
    if not bullet_in_stock:
        owned = in_stock_bullets["by_base"].get(base_key)
        if owned:
            bullet_owned_model = ", ".join(sorted(owned))
    return {
        "id": l.id, "source_id": l.source_id,
        "bullet_weight_gr": l.bullet_weight_gr, "bullet_brand": l.bullet_brand,
        "bullet_model": l.bullet_model, "bullet_dia": l.bullet_dia,
        "case_brand": l.case_brand, "primer_display": l.primer_display,
        "powder_brand": l.powder_brand, "powder_name": l.powder_name, "coal": l.coal,
        "start_charge_gr": l.start_charge_gr, "start_velocity_fps": l.start_velocity_fps,
        "start_pressure": l.start_pressure, "start_pressure_unit": l.start_pressure_unit,
        "start_density_pct": l.start_density_pct, "start_is_compressed": l.start_is_compressed,
        "max_charge_gr": l.max_charge_gr, "max_velocity_fps": l.max_velocity_fps,
        "max_pressure": l.max_pressure, "max_pressure_unit": l.max_pressure_unit,
        "max_density_pct": l.max_density_pct, "max_is_compressed": l.max_is_compressed,
        "powder_in_stock": powder_key in in_stock_powders,
        "bullet_in_stock": bullet_in_stock,
        "bullet_owned_model": bullet_owned_model,
        "caliber": l.source.caliber if l.source else None,
        "twist": l.source.twist if l.source else None,
        "barrel_length": l.source.barrel_length if l.source else None,
        "trim_length": l.source.trim_length if l.source else None,
        "data_as_of": l.source.data_as_of if l.source else None,
    }


def _in_stock_powder_keys(db: Session) -> set:
    rows = db.query(models.PowderInventory.brand, models.PowderInventory.name).filter(
        func.coalesce(models.PowderInventory.weight_lbs, 0) > 0
    ).all()
    return {((b or "").strip().lower(), (n or "").strip().lower()) for b, n in rows}


def _in_stock_bullet_keys(db: Session) -> dict:
    """Returns {"exact": set of (brand, weight, caliber, model) tuples, "by_base": dict of
    (brand, weight, caliber) -> set of raw owned model display strings}. "exact" drives the
    in-stock badge; "by_base" lets a brand/weight/caliber match with a differing model name
    surface what's actually owned instead of guessing it's the same bullet (see
    _normalize_model_token's docstring — Hodgdon's abbreviated codes like "HPBT-SMK" won't
    equal a user's own label like "MatchKing" even though they're the same real bullet).
    """
    rows = db.query(
        models.BulletInventory.brand, models.BulletInventory.weight_gr, models.BulletInventory.caliber,
        models.BulletInventory.product_line, models.BulletInventory.bullet_type,
    ).filter(
        func.coalesce(models.BulletInventory.qty_sealed, 0) + func.coalesce(models.BulletInventory.qty_open, 0) > 0
    ).all()
    exact = set()
    by_base = {}
    for b, w, c, product_line, bullet_type in rows:
        base = ((b or "").strip().lower(), w or 0, _normalize_bore_dia(c))
        # A bullet's identifying model name might live in either field depending on how the
        # user entered it (see product_line vs bullet_type inconsistency in real inventory
        # data) — accept a match against whichever one is set, never both required.
        for model_field in (product_line, bullet_type):
            model_key = _normalize_model_token(model_field)
            if model_key:
                exact.add(base + (model_key,))
                by_base.setdefault(base, set()).add(model_field.strip())
    return {"exact": exact, "by_base": by_base}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/reload-data/upload")
async def upload_reload_data(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_admin(request)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file")
    content = await file.read()
    if len(content) > 20_000_000:
        raise HTTPException(400, "PDF too large")

    parsed = parse_hodgdon_pdf(content)
    if not parsed["caliber"]:
        raise HTTPException(400, "Couldn't determine caliber from this PDF")
    if not parsed["rows"]:
        raise HTTPException(400, "No loads could be parsed from this PDF")

    # Full replace: delete any existing source(s) for this normalized caliber (cascades to loads).
    existing = db.query(models.ReloadDataSource).filter(
        models.ReloadDataSource.caliber == parsed["caliber"]
    ).all()
    for s in existing:
        db.delete(s)
    db.flush()

    source_file_path = None
    await file.seek(0)
    try:
        source_file_path = await save_uploaded_document(file, "reloaddata")
    except Exception:
        source_file_path = None

    source = models.ReloadDataSource(
        caliber=parsed["caliber"], twist=parsed["twist"],
        barrel_length=parsed["barrel_length"], trim_length=parsed["trim_length"],
        data_as_of=parsed["data_as_of"], original_filename=file.filename,
        source_file_path=source_file_path,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(source)
    db.flush()

    db.add_all([
        models.ReloadDataLoad(source_id=source.id, **row) for row in parsed["rows"]
    ])
    db.commit()

    if parsed["rejected_lines"]:
        print(f"[reload-data] {len(parsed['rejected_lines'])} rejected line(s) for {parsed['caliber']!r}:")
        for l in parsed["rejected_lines"]:
            print(f"[reload-data]   {l!r}")

    return {
        "caliber": parsed["caliber"], "rows_imported": len(parsed["rows"]),
        "rows_rejected": len(parsed["rejected_lines"]), "data_as_of": parsed["data_as_of"],
        "rejected_sample": parsed["rejected_lines"][:10],
    }


@router.get("/reload-data/sources")
def list_reload_data_sources(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    sources = (
        db.query(models.ReloadDataSource)
        .options(joinedload(models.ReloadDataSource.loads))
        .order_by(models.ReloadDataSource.caliber)
        .all()
    )
    return [_source_summary(s) for s in sources]


@router.delete("/reload-data/sources/{source_id}")
def delete_reload_data_source(source_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    source = db.query(models.ReloadDataSource).filter(models.ReloadDataSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "Not found")
    if source.source_file_path:
        delete_uploaded_file(source.source_file_path)
    db.delete(source)
    db.commit()
    return {"ok": True}


@router.get("/reload-data/filters")
def reload_data_filters(db: Session = Depends(get_db)):
    calibers = [r[0] for r in db.query(models.ReloadDataSource.caliber).distinct().order_by(models.ReloadDataSource.caliber).all()]
    bullet_brands = [r[0] for r in db.query(models.ReloadDataLoad.bullet_brand).filter(
        models.ReloadDataLoad.bullet_brand.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.bullet_brand).all()]
    powder_brands = [r[0] for r in db.query(models.ReloadDataLoad.powder_brand).filter(
        models.ReloadDataLoad.powder_brand.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.powder_brand).all()]
    powder_names = [r[0] for r in db.query(models.ReloadDataLoad.powder_name).filter(
        models.ReloadDataLoad.powder_name.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.powder_name).all()]
    return {
        "calibers": calibers, "bullet_brands": bullet_brands,
        "powder_brands": powder_brands, "powder_names": powder_names,
    }


@router.get("/reload-data/loads")
def list_reload_data_loads(
    caliber: str = Query(None), bullet_weight_gr: float = Query(None),
    bullet_brand: str = Query(None), powder_brand: str = Query(None),
    powder_name: str = Query(None), in_stock_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.ReloadDataLoad).join(models.ReloadDataSource).options(joinedload(models.ReloadDataLoad.source))
    if caliber:
        q = q.filter(models.ReloadDataSource.caliber == normalize_caliber(caliber))
    if bullet_weight_gr is not None:
        q = q.filter(models.ReloadDataLoad.bullet_weight_gr == bullet_weight_gr)
    if bullet_brand:
        q = q.filter(models.ReloadDataLoad.bullet_brand == bullet_brand)
    if powder_brand:
        q = q.filter(models.ReloadDataLoad.powder_brand == powder_brand)
    if powder_name:
        q = q.filter(models.ReloadDataLoad.powder_name == powder_name)
    rows = q.order_by(models.ReloadDataLoad.bullet_weight_gr, models.ReloadDataLoad.powder_name).limit(1000).all()

    in_stock_powders = _in_stock_powder_keys(db)
    in_stock_bullets = _in_stock_bullet_keys(db)
    results = [_load_dict(l, in_stock_powders, in_stock_bullets) for l in rows]
    if in_stock_only:
        results = [r for r in results if r["powder_in_stock"] or r["bullet_in_stock"]]
    return results
