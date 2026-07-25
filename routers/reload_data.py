import io
import os
import re
import uuid
from datetime import datetime, timezone

import pdfplumber
import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import database as models
from config import templates, UPLOAD_DIR
from dependencies import get_db, save_uploaded_document, delete_uploaded_file
from routers.barcode import normalize_caliber

router = APIRouter()


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


@router.get("/admin/reload-data", response_class=HTMLResponse)
async def admin_reload_data_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("admin_reload_data.html", {"request": request, "user": request.state.user})


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


# ── Multi-manufacturer dispatch ─────────────────────────────────────────────
# Each manufacturer's PDF is a genuinely different layout (confirmed against real files, not
# guessed): Hodgdon is a comma-delimited table; Nosler/Speer/Sierra/Barnes each have their own
# shape (see parse_nosler_pdf/parse_speer_pdf/parse_sierra_pdf/parse_barnes_pdf below). Detection
# is via literal anchor text unique to each manufacturer's PDF — never a fuzzy guess. Barnes has
# no such anchor (the word "Barnes" never appears in the text layer — brand identity is logo-only)
# so it can't be auto-detected; the upload UI's manufacturer dropdown exists specifically for that.

_MANUFACTURER_ANCHORS = [
    ("Hodgdon", ("Reloading Data Center",)),
    ("Nosler", ("Nosler, Inc.",)),
    ("Speer", ("Speer Part", "speer-ammo.com")),
    ("Sierra", ("SIERRA RELOADING MANUAL", "Sierra Reloading Manual")),
]

# Powder brands that show up as a plain leading word in non-Hodgdon manufacturers' propellant
# columns (e.g. Speer's "Alliant AR-Comp", "Hodgdon BL-C(2)") — used to split brand from name
# where the source doesn't already provide them as separate columns like Hodgdon does. An
# unrecognized leading word just leaves brand unset (name keeps the full original text) rather
# than guessing — that row's powder simply won't be eligible for the in-stock badge, which is
# the safe failure mode already established for this feature.
_POWDER_BRANDS = ("Accurate", "Alliant", "Hodgdon", "IMR", "Ramshot", "Vihtavuori", "Winchester")


def _split_powder_brand(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    for brand in _POWDER_BRANDS:
        if raw.lower().startswith(brand.lower() + " "):
            return brand, raw[len(brand):].strip()
    return None, raw


def _rasterize_bbox(page, x0: float, top: float, x1: float, bottom: float, pad: float = 8, resolution: int = 200, rotate: int = 0) -> bytes:
    x0 = max(x0 - pad, 0)
    top = max(top - pad, 0)
    x1 = min(x1 + pad, page.width)
    bottom = min(bottom + pad, page.height)
    cropped = page.crop((x0, top, x1, bottom))
    im = cropped.to_image(resolution=resolution)
    pil_im = im.original
    if rotate:
        pil_im = pil_im.rotate(rotate, expand=True)
    buf = io.BytesIO()
    pil_im.save(buf, format="PNG")
    return buf.getvalue()


def _diagram_from_image(page, pick: str = "first", crop_left_frac: float = 0.0) -> bytes | None:
    """Raster-image based diagram extraction. Nosler pages have exactly one clean image, but it's
    a single flattened graphic with a black "NOSLER" logo panel filling the left half and the
    actual case diagram in the right half (confirmed via pixel-column brightness scan on real
    files: columns 0-~49% average near-black, columns ~50%+ jump to a light gray/white
    background — an exact 50/50 split, consistent across every sample file's identical
    950x333px raster output) — crop_left_frac drops that logo half so only the diagram shows.
    Speer pages have 5 images (diagram + 3 repeated bullet photos + a logo), so pick the largest
    one positioned in the page's top half instead of just "the first image".
    """
    images = page.images
    if not images:
        return None
    if pick == "first":
        im = images[0]
    else:  # "largest_top"
        candidates = [i for i in images if i["top"] < page.height * 0.5] or images
        im = max(candidates, key=lambda i: (i["x1"] - i["x0"]) * (i["bottom"] - i["top"]))
    x0 = im["x0"] + (im["x1"] - im["x0"]) * crop_left_frac
    return _rasterize_bbox(page, x0, im["top"], im["x1"], im["bottom"])


def _diagram_from_curves(page, x0_frac: float = 0.4, rotate: int = 0) -> bytes | None:
    """Vector-drawn diagram extraction (Sierra/Hornady): these manufacturers draw the case
    dimension diagram as vector line art, not an embedded raster image — page.images is empty.
    Rasterize the bounding box of curves positioned right of x0_frac * page width instead.
    Sierra draws its diagram in portrait orientation (tall/narrow) — rotate=90 (or -90) turns
    it landscape so it doesn't dominate the detail page's vertical space next to the loads.
    """
    curves = [c for c in page.curves if c["x0"] > page.width * x0_frac]
    if not curves:
        return None
    x0 = min(c["x0"] for c in curves)
    x1 = max(c["x1"] for c in curves)
    top = min(c["top"] for c in curves)
    bottom = max(c["bottom"] for c in curves)
    return _rasterize_bbox(page, x0, top, x1, bottom, rotate=rotate)


def _save_case_diagram(png_bytes: bytes | None) -> str | None:
    if not png_bytes:
        return None
    filename = f"reloaddata_diagram_{uuid.uuid4()}.png"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(png_bytes)
    return f"/static/uploads/{filename}"


def parse_reload_pdf(pdf_bytes: bytes, manufacturer_hint: str | None = None, filename: str | None = None) -> dict:
    """Dispatches to the right manufacturer-specific parser. If manufacturer_hint is given
    (the upload dropdown override), skip detection entirely. Every parser returns the same
    dict shape parse_hodgdon_pdf does, plus "manufacturer", "scope_bullet_weight_gr",
    "scope_bullet_model", and "case_diagram_bytes" (raw PNG bytes or None). `filename` is only
    used by the Barnes parser (its own PDF text layer has no reliable way to tell the real
    cartridge title apart from a mirrored sidebar-tab watermark for suffix-less wildcat
    calibers like "338-06" — see parse_barnes_pdf's docstring).
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    manufacturer = manufacturer_hint
    if not manufacturer:
        for name, anchors in _MANUFACTURER_ANCHORS:
            if any(a in text for a in anchors):
                manufacturer = name
                break
    if not manufacturer:
        raise HTTPException(400, "Couldn't identify which manufacturer this PDF is from — pick one from the dropdown")

    parsers = {
        "Hodgdon": parse_hodgdon_pdf,
        "Nosler": parse_nosler_pdf,
        "Speer": parse_speer_pdf,
        "Sierra": parse_sierra_pdf,
        "Barnes": parse_barnes_pdf,
    }
    parser = parsers.get(manufacturer)
    if parser is None:
        raise HTTPException(400, f"Unsupported manufacturer: {manufacturer}")

    result = parser(pdf_bytes, filename) if manufacturer == "Barnes" else parser(pdf_bytes)
    result.setdefault("manufacturer", manufacturer)
    result.setdefault("scope_bullet_weight_gr", None)
    result.setdefault("scope_bullet_model", None)
    result.setdefault("case_diagram_bytes", None)
    return result


# ── Speer PDF parsing ────────────────────────────────────────────────────────
# One PDF = one caliber + one specific named bullet (title-named, e.g. "with 130 gr Spitzer SP
# Hot-Cor"). The bullet-family table under the title lists every same-weight bullet Speer sells
# (for BC/SD reference), not separate tested loads — only the title-named bullet's charge data
# follows. That family table's text wraps across lines in a way that jumbles bullet names with
# numeric spec rows (a 2-column layout, same class of artifact as Barnes), so rather than parse
# it, weight/model/caliber are taken from the clean title text and the family table is skipped
# wholesale (never guessed at) between its header and "START CHARGE". Data rows are a plain
# propellant/case/primer/start/max table but anchored from the RIGHT: propellant names have
# variable word count (parens, dashes, embedded numbers) while case is always exactly one token
# and primer is always exactly "brand number" (confirmed against every real Speer file on disk).

_SPEER_TITLE_RE = re.compile(r'^(?P<caliber>.+?)\s+with\s+(?P<weight>\d+(?:\.\d+)?)\s*gr\.?\s+(?P<model>.+)$', re.IGNORECASE)

_SPEER_ROW_RE = re.compile(r'''
    ^(?P<propellant>.+?)\s+
    (?P<case>\S+)\s+
    (?P<primer_brand>\S+)\s+(?P<primer_num>\S+)\s+
    (?P<st_gr>\d+(?:\.\d+)?)\s+
    (?P<st_vel>\d+)\s+
    (?P<mx_gr>\d+(?:\.\d+)?)\s*(?P<mx_c>C)?\s+
    (?P<mx_vel>\d+)\s*$
''', re.VERBOSE)


def _parse_speer_row(line: str) -> dict | None:
    m = _SPEER_ROW_RE.match(line.strip())
    if not m:
        return None
    d = m.groupdict()
    powder_brand, powder_name = _split_powder_brand(d["propellant"])
    return {
        "powder_brand": powder_brand,
        "powder_name": powder_name,
        "case_brand": d["case"].strip(),
        "primer_display": f"{d['primer_brand']} {d['primer_num']}".strip(),
        "coal": None,
        "start_charge_gr": float(d["st_gr"]),
        "start_is_compressed": False,
        "start_velocity_fps": int(d["st_vel"]),
        "start_pressure": None, "start_pressure_unit": None, "start_density_pct": None,
        "max_charge_gr": float(d["mx_gr"]),
        "max_is_compressed": bool(d["mx_c"]),
        "max_velocity_fps": int(d["mx_vel"]),
        "max_pressure": None, "max_pressure_unit": None, "max_density_pct": None,
    }


def _speer_candidate_bullets(page) -> list[tuple[float, str, str, str, str, str]]:
    """The candidate-bullets spec table (Speer Part No./Weight/COAL Tested/Ballistic
    Coefficient/Sectional Density) is genuinely position-dependent, not linear-text-safe: each
    bullet's name wraps across 2 physical lines around a narrow name column, with the data row's
    numbers sandwiched on a line *between* them (confirmed via real word positions — e.g. "130 gr
    Grand" / "1465 130 3.240" .332 .242" / "Slam® SP"). Gap-based clustering (threshold 15pt)
    reliably groups each candidate's 2-3 lines while still splitting at the ~42-44pt gap between
    candidates — confirmed against every real file, including ones with only 1 candidate (no
    wrapping) and ones with 3. Scoped strictly between the "Speer Part..." header and "START
    CHARGE" markers so a same-page propellant charge table's numeric columns are never mistaken
    for a 4th candidate — the header labels don't reliably appear in extract_text()'s exact
    reading order otherwise.
    """
    words = sorted(page.extract_words(), key=lambda w: w["top"])
    clusters: list[list] = []
    for w in words:
        if clusters and w["top"] - clusters[-1][-1]["top"] <= 15:
            clusters[-1].append(w)
        else:
            clusters.append([w])

    header_idx = next((i for i, c in enumerate(clusters) if any(w["text"] == "Speer" for w in c) and any(w["text"] == "Part" for w in c)), None)
    charge_idx = next((i for i, c in enumerate(clusters) if any(w["text"] == "START" for w in c)), None)
    if header_idx is None or charge_idx is None:
        return []

    bullets = []
    for cluster in clusters[header_idx + 1:charge_idx]:
        data_words = sorted([w for w in cluster if w["x0"] >= 232], key=lambda w: w["x0"])
        if len(data_words) < 5:
            continue
        part_no, weight_txt, coal, bc, sd = (w["text"] for w in data_words[:5])
        if not re.match(r'^\d+$', part_no):
            continue
        try:
            weight = float(weight_txt)
        except ValueError:
            continue
        name_words = sorted([w for w in cluster if w["x0"] < 220], key=lambda w: (w["top"], w["x0"]))
        # A trailing "-" on a word (e.g. "Hot-") is a line-wrap hyphenation, not a real word
        # boundary — join it directly onto the next word ("Cor®") instead of inserting a space,
        # or "Hot-Cor®" comes out as "Hot- Cor®".
        name_parts: list[str] = []
        for w in name_words:
            if name_parts and name_parts[-1].endswith("-"):
                name_parts[-1] += w["text"]
            else:
                name_parts.append(w["text"])
        name = " ".join(name_parts)
        name = re.sub(r'^\d+\s*gr\.?\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[®™]', '', name).strip()
        if name:
            bullets.append((weight, name, part_no, coal.rstrip('"'), bc, sd))
    return bullets


def parse_speer_pdf(pdf_bytes: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        diagram_bytes = _diagram_from_image(pdf.pages[0], pick="largest_top")
        bullets = _speer_candidate_bullets(pdf.pages[0])

    lines = [l.rstrip() for l in text.split("\n")]

    # Title spans 1-2 physical lines, always ending right before "Max Case Length:".
    title_lines = []
    for l in lines:
        if l.startswith("Max Case Length:"):
            break
        if l.strip():
            title_lines.append(l.strip())
    title = " ".join(title_lines)
    m = _SPEER_TITLE_RE.match(title)
    caliber = normalize_caliber(m.group("caliber")) if m else None
    scope_weight = float(m.group("weight")) if m else None
    scope_model = m.group("model").strip() if m else None

    # Fall back to a single candidate built from the title if the position-based table
    # extraction found nothing (e.g. an unexpected layout) — keeps the parser degrading to its
    # previous single-bullet behavior instead of losing all rows for the file.
    if not bullets and scope_weight is not None and scope_model:
        bullets = [(scope_weight, scope_model, None, None, None, None)]

    rows: list[dict] = []
    rejected: list[str] = []
    barrel_length = trim_length = max_case_length = max_saami_oal = rcbs_shell_holder = test_firearm = None
    in_bullet_table = False
    in_data = False
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("Max Case Length:"):
            max_case_length = s.replace("Max Case Length:", "").strip()
            continue
        if s.startswith("Max Cart. OAL:"):
            max_saami_oal = s.replace("Max Cart. OAL:", "").strip().rstrip('"')
            continue
        if s.startswith("RCBS Shell Holder:"):
            rcbs_shell_holder = s.replace("RCBS Shell Holder:", "").strip()
            continue
        if s.startswith("Test Firearm:"):
            test_firearm = s.replace("Test Firearm:", "").strip()
            continue
        if s.startswith("Trim-to Length:"):
            trim_length = s.replace("Trim-to Length:", "").strip()
            continue
        if s.startswith("Barrel Length:"):
            barrel_length = s.replace("Barrel Length:", "").strip()
            continue
        if s.startswith("Speer Part") or s.startswith("No. grains"):
            in_bullet_table = True
            continue
        if s.startswith("START CHARGE"):
            in_bullet_table = False
            in_data = True
            continue
        if s.startswith("Propellant Cartridge"):
            continue
        if s == "C = Compressed Load" or s.startswith("speer-ammo.com"):
            continue
        if title_lines and s == title_lines[0]:
            continue
        if in_bullet_table or not in_data:
            continue
        base_row = _parse_speer_row(s)
        if base_row is None:
            rejected.append(l)
            continue
        for weight, model, part_no, coal, bc, sd in bullets:
            row = dict(base_row)
            row["bullet_weight_gr"] = weight
            row["bullet_brand"] = "Speer"
            row["bullet_model"] = model
            row["bullet_code"] = part_no
            row["bullet_bc"] = float(bc) if bc else None
            row["bullet_sd"] = float(sd) if sd else None
            row["coal"] = coal
            row["bullet_dia"] = None  # not given directly in Speer's text — filled via caliber lookup at import time
            rows.append(row)

    return {
        "caliber": caliber, "twist": None, "barrel_length": barrel_length, "trim_length": trim_length,
        "max_saami_oal": max_saami_oal, "max_case_length": max_case_length,
        "rcbs_shell_holder": rcbs_shell_holder, "test_firearm": test_firearm,
        "data_as_of": None, "rows": rows, "rejected_lines": rejected,
        "manufacturer": "Speer", "scope_bullet_weight_gr": scope_weight, "scope_bullet_model": scope_model,
        "case_diagram_bytes": diagram_bytes,
    }


# ── Barnes PDF parsing ───────────────────────────────────────────────────────
# One PDF = one caliber, covering every bullet weight Barnes publishes for it. The page is a
# genuine two-column layout (bullet specs on the left, the propellant table on the right) that
# extract_text()'s linear reading order jumbles line-by-line — reconstructed here via extract_words()
# split by x0 position, then clustered into rows by top position (confirmed against every real
# file: left column words all have x0 <= ~40% of page width, right column words all have
# x0 > that). No case diagram in these files at all (confirmed — cover page has no dimensioned
# drawing), so case_diagram_bytes is always None here.
#
# A weight-class "block" of bullet SKUs (e.g. "110-grain TSX FB / TAC-X FB" immediately followed
# by "110-grain TTSX FB / TAC-TX FB", with only ONE propellant table between/around them) all
# share that ONE table's charge data — confirmed against real files: multiple bullet-name labels
# with no table in between them really do share the next table, rather than the alignment being
# off. Block boundaries are found by partitioning left-column labels using each table's header
# top position as a cutoff (a label belongs to the last table whose header starts at or before
# it) — this is a real, confirmed structural pattern, not a coordinate-guessing heuristic.
#
# Bullet model/weight is inherently ambiguous here in a way brand+weight+caliber isn't (Barnes'
# own data conflates flat-base/boat-tail/lead-free variants of the same weight under one table),
# so this is exactly the kind of case the "show what you actually own instead of a guessed
# in-stock claim" fallback (see _normalize_model_token) exists for — an imprecise model match
# here just falls into that safe informational bucket rather than ever producing a false badge.
#
# Powder brand is often abbreviated or omitted entirely (bare "H335"/"Varget"/"TAC"/"Big Game"
# instead of "Hodgdon H335"/"Ramshot TAC") — _BARNES_POWDER_MAP below was built by cross-checking
# every bare name seen in real Barnes files against this app's own already-imported Hodgdon data
# (which does label brand explicitly), not guessed from general knowledge.

_BARNES_POWDER_MAP = {
    "BENCHMARK": "Hodgdon", "BL-C(2)": "Hodgdon", "CFE 223": "Hodgdon", "H322": "Hodgdon",
    "H335": "Hodgdon", "H380": "Hodgdon", "H414": "Hodgdon", "H4350": "Hodgdon",
    "H4895": "Hodgdon", "HYBRID 100V": "Hodgdon", "VARGET": "Hodgdon", "AR-COMP": "Hodgdon",
    "SUPERFORMANCE": "Hodgdon", "LEVEREVOLUTION": "Hodgdon",
    "BIG GAME": "Ramshot", "HUNTER": "Ramshot", "TAC": "Ramshot", "X-TERMINATOR": "Ramshot",
}

_BARNES_ROW_RE = re.compile(r'^\*?(?P<name>.+?)\s+(?P<min_gr>\d+(?:\.\d+)?)\s+(?P<min_vel>\d+)\s+(?P<max_gr>\d+(?:\.\d+)?)\s*(?P<mx_c>[Cc])?\s+(?P<max_vel>\d+)$')
_BARNES_NUMS_ONLY_RE = re.compile(r'^(?P<min_gr>\d+(?:\.\d+)?)\s+(?P<min_vel>\d+)\s+(?P<max_gr>\d+(?:\.\d+)?)\s*(?P<mx_c>[Cc])?\s+(?P<max_vel>\d+)$')
_BARNES_LABEL_RE = re.compile(r'^(?P<weight>\d+(?:\.\d+)?)-grain\s+(?P<model>.+)$', re.IGNORECASE)


def _merge_wrapped_barnes_rows(table_rows: list[str]) -> list[str]:
    """Long propellant names (e.g. "Alliant Power Pro 2000-MR") sometimes wrap across three
    lines within the narrow right column, with the numbers landing on their own line in
    between the name's start and its continuation (confirmed against real files) — e.g.
    "Powerpro" / "39.8 2305 44.2C 2525" / "2000MR". Detected by finding a numbers-only line
    (no name at all) and pulling in the immediately preceding/following fragments, if those
    don't themselves look like complete rows.
    """
    merged: list[str] = []
    i = 0
    while i < len(table_rows):
        text = table_rows[i].strip()
        if _BARNES_ROW_RE.match(text) or not _BARNES_NUMS_ONLY_RE.match(text):
            merged.append(table_rows[i])
            i += 1
            continue
        prev_frag = None
        if merged and not _BARNES_ROW_RE.match(merged[-1].strip()) and not _BARNES_NUMS_ONLY_RE.match(merged[-1].strip()):
            prev_frag = merged.pop()
        next_frag = None
        if i + 1 < len(table_rows):
            nxt = table_rows[i + 1].strip()
            if not _BARNES_ROW_RE.match(nxt) and not _BARNES_NUMS_ONLY_RE.match(nxt):
                next_frag = table_rows[i + 1]
        name = " ".join(p for p in (prev_frag, next_frag) if p)
        merged.append(f"{name} {table_rows[i]}".strip())
        i += 2 if next_frag else 1
    return merged


def _split_barnes_powder(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    if raw.upper().startswith("IMR "):
        return "IMR", raw[4:].strip()
    m = re.match(r'^A-(\d.*)$', raw)
    if m:
        return "Accurate", f"A{m.group(1)}"
    m = re.match(r'^RL\s*(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "Alliant", f"Reloder {m.group(1)}"
    if raw.upper().startswith("WIN "):
        return "Winchester", raw[4:].strip()
    if raw.upper().startswith("WINCHESTER "):
        return "Winchester", raw[11:].strip()
    if re.sub(r'\s+', '', raw).upper().startswith("POWERPRO"):
        return "Alliant", raw
    mapped = _BARNES_POWDER_MAP.get(raw.upper())
    if mapped:
        return mapped, raw
    return None, raw


def _barnes_col_rows(page, side: str) -> list[tuple[float, str]]:
    """Reconstructs one side of the two-column layout into (top, text) rows.

    A fixed x0 threshold doesn't reliably separate the columns: short right-column powder names
    (e.g. "H4895") can start further left (x0≈152) than long left-column label text wraps (e.g.
    the trailing "BT" of "TTSX BT / TAC-TX BT", x0≈154) — confirmed against real files, the two
    columns' x-ranges genuinely overlap. So instead: cluster ALL words by top-proximity first
    (words on the same visual line can differ by under a point — e.g. the trailing "C"
    compressed-load flag consistently renders ~0.4pt higher than the rest of its row — clustering
    by gap-to-previous-word avoids a fixed rounding grid splitting those apart), then, only if a
    cluster's own words span a real gutter gap (>12pt between adjacent words — much wider than
    the 2-5pt normal word spacing within one column), split it into a left and right half at that
    gap. A cluster with no such internal gap is classified whole, by matching its text against
    known right-column shapes (a full or numbers-only data row, or a column header) — content,
    not position, is what actually distinguishes the columns here.
    """
    words = page.extract_words()
    # The rotated sidebar-tab watermark (mirrored cartridge name/part-number, e.g.
    # "retsehcniW"/"803" or "60-833") alternates which edge of the page it sits on from page to
    # page, confirmed at x0≈7.4 on a 378pt-wide page — well left of where real left-column label
    # text starts (confirmed x0≈40+) but NOT so close to the edge that a 1%-of-width cutoff would
    # catch it (0.01 * 378 ≈ 3.8, which is less than 7.4) — 5% sits safely between the two.
    words = [w for w in words if 0.05 * page.width < w["x0"] < 0.92 * page.width]
    words.sort(key=lambda w: w["top"])
    clusters: list[list] = []
    for w in words:
        if clusters and w["top"] - clusters[-1][0]["top"] <= 2.5:
            clusters[-1].append(w)
        else:
            clusters.append([w])

    def _looks_right(text: str) -> bool:
        m = _BARNES_ROW_RE.match(text) or _BARNES_NUMS_ONLY_RE.match(text)
        if m and "name" in m.groupdict() and re.search(r'\d+-grain', m.group("name"), re.IGNORECASE):
            # The row regex's non-greedy name will happily swallow a whole "N-grain ..." label
            # glued onto the front of a data row on the same visual line (a genuine column-bleed
            # case, not a clean single-column match) — don't treat that as a clean right-side row.
            return False
        return bool(m or text.startswith(("Minimum", "Maximum", "Powder", "Charge Velocity", "(grains)")))

    def _looks_left(text: str) -> bool:
        return bool(
            _BARNES_LABEL_RE.match(text)
            or text.startswith(("Sectional Density", "Ballistic Coefficient", "C.O.A.L", "Suggested Bullet Use"))
        )

    def _find_content_split(ws_sorted: list) -> int | None:
        """For a cluster that doesn't cleanly classify as a whole (label text glued directly
        onto a data row, e.g. "155-grain Match Burner AR-Comp 39.4 2609 43.8C 2870" — the gap
        between them can be as small as ~18pt, indistinguishable by gap size alone from a
        legitimate wide gap *within* one column's own header text), search every word boundary
        for a split where the left half is a clean label and the right half is a clean data row.
        """
        for i in range(1, len(ws_sorted)):
            left_text = " ".join(w["text"] for w in ws_sorted[:i])
            right_text = " ".join(w["text"] for w in ws_sorted[i:])
            if _BARNES_LABEL_RE.match(left_text) and (_BARNES_ROW_RE.match(right_text) or _BARNES_NUMS_ONLY_RE.match(right_text)):
                return i
        return None

    out = []
    for ws in clusters:
        ws_sorted = sorted(ws, key=lambda w: w["x0"])
        whole_text = " ".join(w["text"] for w in ws_sorted)
        gap_idx = _find_content_split(ws_sorted) if not (_looks_right(whole_text) or _looks_left(whole_text)) else None
        if gap_idx is None:
            # Fall back to the widest internal gap — genuine column-gutter gaps (left label
            # bleeding into a right-column row) are far wider than the biggest gap seen *within*
            # a legitimate single-column header line (e.g. "Minimum"/"Maximum" ~29pt) — 35 sits
            # safely between the two, confirmed against every real file.
            biggest_gap = 35
            for i in range(1, len(ws_sorted)):
                gap = ws_sorted[i]["x0"] - ws_sorted[i - 1]["x1"]
                if gap > biggest_gap:
                    biggest_gap = gap
                    gap_idx = i
        parts = [ws_sorted[:gap_idx], ws_sorted[gap_idx:]] if gap_idx else [ws_sorted]
        for part in parts:
            text = " ".join(w["text"] for w in part)
            top = min(w["top"] for w in part)
            if _looks_right(text):
                is_right = True
            elif _looks_left(text):
                is_right = False
            else:
                is_right = part[0]["x0"] > page.width * 0.42
            if is_right == (side == "right"):
                out.append((top, text))
    return out


def _derive_barnes_caliber(filename: str | None, text: str) -> str | None:
    """Barnes' page-0 text has a mirrored sidebar-tab watermark (e.g. "retsehcniW"/"803" for
    "Winchester"/"308") that can collide in length/shape with the real title for suffix-less
    wildcat calibers like "338-06" — there's no reliable text-only way to always tell them
    apart. The original upload filename is a much more reliable signal for this manufacturer
    specifically (e.g. "308WinchesterForWeb.pdf", "30-06Springfield.pdf", "338-06.pdf")."""
    if filename:
        stem = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
        stem = re.sub(r'forweb$', '', stem, flags=re.IGNORECASE)
        stem = re.sub(r'(\d)([A-Za-z])', r'\1 \2', stem)  # "308Winchester" -> "308 Winchester"
        stem = stem.strip()
        if stem:
            return normalize_caliber(stem)
    for line in text.split("\n"):
        s = line.strip()
        if s and " " in s and not s.startswith(("Case", "Primer", "Barrel", "Twist", "Maximum", "*", "Suggested", "Sectional", "Ballistic", "C.O.A.L")):
            return normalize_caliber(s)
    return None


def parse_barnes_pdf(pdf_bytes: bytes, filename: str | None = None) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page0_text = pdf.pages[0].extract_text() or ""
        caliber = _derive_barnes_caliber(filename, page0_text)

        barrel_length = None
        trim_length = None
        twist = None
        case_brand = None
        primer_display = None
        test_firearm = None
        m = re.search(r'Case Trim:\s*([\d.]+.?)\s*Barrel Length:\s*([\d.]+.?)', page0_text)
        if m:
            trim_length, barrel_length = m.group(1), m.group(2)
        m = re.search(r'Twist Rate:\s*(\S+)', page0_text)
        if m:
            twist = m.group(1)
        # "Case: Winchester Primer: Federal 210" / "Twist Rate: 1:12” Barrel: Krieger" — both
        # previously parsed nowhere at all (only Case Trim/Barrel Length/Twist Rate were kept).
        m = re.search(r'Case:\s*(.+?)\s+Primer:\s*(.+)', page0_text)
        if m:
            case_brand, primer_display = m.group(1).strip(), m.group(2).strip()
        m = re.search(r'Barrel:\s*(.+)', page0_text)
        if m:
            test_firearm = m.group(1).strip()

        rows: list[dict] = []
        rejected: list[str] = []
        for page in pdf.pages[1:]:
            left = _barnes_col_rows(page, "left")
            right = _barnes_col_rows(page, "right")

            # Reconstruct labels: merge consecutive left lines from an "N-grain ..." starter
            # until "Sectional Density" (handles both single-line and word-wrapped labels), then
            # also pick up that same bullet's Sectional Density/Ballistic Coefficient/C.O.A.L.
            # values (previously parsed nowhere at all — thrown away as label-block terminators).
            # "Suggested Bullet Use" is always blank in every real file (confirmed), so it's just
            # another terminator, not a value worth capturing.
            labels: list[dict] = []
            cur = None
            label_done = False
            for top, text in left:
                if _BARNES_LABEL_RE.match(text):
                    if cur is not None:
                        labels.append(cur)
                    cur = {"top": top, "text": text, "sd": None, "bc": None, "coal": None}
                    label_done = False
                    continue
                if cur is None:
                    continue
                if text.startswith("Sectional Density"):
                    label_done = True
                    m2 = re.search(r'(\d*\.\d+)', text)
                    if m2:
                        cur["sd"] = m2.group(1)
                elif text.startswith("Ballistic Coefficient"):
                    label_done = True
                    m2 = re.search(r'(\d*\.\d+)', text)
                    if m2:
                        cur["bc"] = m2.group(1)
                elif text.startswith("C.O.A.L"):
                    label_done = True
                    m2 = re.search(r'(\d*\.\d+)', text)
                    if m2:
                        cur["coal"] = m2.group(1)
                elif text.startswith("Suggested Bullet Use"):
                    label_done = True
                elif not label_done:
                    cur["text"] += " " + text
            if cur is not None:
                labels.append(cur)

            # Tables: contiguous runs of right-column rows that parse as data rows, each
            # preceded by a "Minimum Maximum" / "Powder" / column-header run (skipped).
            table_starts: list[float] = []
            tables: list[list[str]] = []
            current: list[str] | None = None
            for top, text in right:
                if text.startswith(("Minimum", "Maximum", "Powder", "Charge Velocity", "(grains)")):
                    if current is not None:
                        tables.append(current)
                    current = None
                    if text.startswith("Minimum"):
                        table_starts.append(top)
                    continue
                if text.startswith((
                    "With Caution", "C Compressed Load", "Recommended Powder", "Recommended Twist",
                    "*Recommended", "Most Accurate Load", "*Most Accurate", "Compressed Load", "Accurate Load",
                )) or re.match(r'^\d+$', text.strip()):
                    continue
                if current is None:
                    current = []
                current.append(text)
            if current is not None:
                tables.append(current)

            if len(table_starts) != len(tables):
                rejected.append(f"[page anomaly] {len(table_starts)} table headers but {len(tables)} data blocks found")
                continue

            # Assign each label to the last table whose header starts at or before it.
            blocks: list[list[dict]] = [[] for _ in tables]
            for label in labels:
                idx = 0
                for i, start in enumerate(table_starts):
                    if start <= label["top"]:
                        idx = i
                blocks[idx].append(label)

            for block_labels, table_rows in zip(blocks, tables):
                # One block/table can be shared by more than one weight-grain label (confirmed:
                # "110-grain TSX FB / TAC-X FB" immediately followed by "110-grain TTSX FB /
                # TAC-TX FB" sharing one propellant table) — and each label's SD/BC/C.O.A.L. can
                # genuinely differ even at the same weight, so every individual model (after
                # splitting on "/") keeps its own label's spec values rather than one shared set.
                entries: list[tuple[float, str, str | None, str | None, str | None]] = []
                for label in block_labels:
                    m = _BARNES_LABEL_RE.match(label["text"])
                    if not m:
                        continue
                    weight = float(m.group("weight"))
                    for model in (part.strip() for part in m.group("model").split("/") if part.strip()):
                        entries.append((weight, model, label["sd"], label["bc"], label["coal"]))
                if not entries:
                    rejected.append(f"[unmatched block] {table_rows[:1]}")
                    continue
                for row_text in _merge_wrapped_barnes_rows(table_rows):
                    m = _BARNES_ROW_RE.match(row_text.strip())
                    if m is None:
                        rejected.append(row_text)
                        continue
                    d = m.groupdict()
                    powder_brand, powder_name = _split_barnes_powder(d["name"])
                    for weight, model, sd, bc, coal in entries:
                        rows.append({
                            "bullet_weight_gr": weight, "bullet_brand": "Barnes", "bullet_model": model,
                            "bullet_dia": None, "bullet_sd": float(sd) if sd else None, "bullet_bc": float(bc) if bc else None,
                            "case_brand": case_brand, "primer_display": primer_display,
                            "powder_brand": powder_brand, "powder_name": powder_name, "coal": coal,
                            "start_charge_gr": float(d["min_gr"]), "start_is_compressed": False,
                            "start_velocity_fps": int(d["min_vel"]),
                            "start_pressure": None, "start_pressure_unit": None, "start_density_pct": None,
                            "max_charge_gr": float(d["max_gr"]), "max_is_compressed": bool(d["mx_c"]),
                            "max_velocity_fps": int(d["max_vel"]),
                            "max_pressure": None, "max_pressure_unit": None, "max_density_pct": None,
                        })

    return {
        "caliber": caliber, "twist": twist, "barrel_length": barrel_length, "trim_length": trim_length,
        "test_firearm": test_firearm,
        "data_as_of": None, "rows": rows, "rejected_lines": rejected,
        "manufacturer": "Barnes", "scope_bullet_weight_gr": None, "scope_bullet_model": None,
        "case_diagram_bytes": None,
    }


# ── Sierra PDF parsing ───────────────────────────────────────────────────────
# One PDF = one caliber, covering every bullet weight Sierra publishes for it (confirmed:
# 5-14 pages, one weight-block per page). Sierra's data has no start/max range at all — it's a
# matrix of powder x target-velocity, where each cell is the charge needed to reach that
# velocity. Stored as single-point loads (start == max) per the earlier design decision, since
# there's genuinely no "starting load" concept here to preserve.
#
# Every real file except 22-Creedmoor.pdf has a large (40+pt font) repeating diagonal watermark
# ("This data is for individual use only...") that pdfplumber's linear text extraction
# interleaves character-by-character into the real content, corrupting it badly — confirmed by
# checking char sizes directly (real content never exceeds ~16pt here). Filtering out anything
# above size 20 before extracting text/words removes it cleanly.
#
# Charge values are NOT simply "first N values under the first N velocity columns" in text
# order — the columns are genuinely sparse (a powder might only have data for its top few
# velocities) and pdfplumber's linear extraction drops empty cells rather than leaving a gap, so
# a naive positional read would silently misassign every value after the first missing one. The
# fix (confirmed against real x0 coordinates): each charge value's x0 lines up almost exactly
# with its velocity column header's x0, so matching by nearest x0 recovers the true alignment.
#
# One page's "Bullet Caliber Weight Type C.O.A.L." table often lists several distinct bullet
# weights/types together (not just brand variants like Nosler/Barnes) — Sierra publishes one
# shared charge table per similar-weight bundle, so every bullet listed fans out with its own
# weight/model against that page's one velocity matrix.

_SIERRA_BULLET_ROW_RE = re.compile(
    r'^#(?P<sku>\S*)\s+(?P<dia>\.?\d+(?:\.\d+)?)[”"]?\s*(?P<weight>\d+(?:\.\d+)?)\s*gr\.?\s+(?P<type>.+?)\s+(?P<coal>\d+\.\d+)[”"]?\s*\*{0,2}$'
)

_SIERRA_POWDER_MAP = {
    "TAC": "Ramshot", "BIG GAME": "Ramshot", "HUNTER": "Ramshot", "X-TERMINATOR": "Ramshot",
    "EXTERMINATOR": "Ramshot",
    "SUPERFORMANCE": "Hodgdon", "VARGET": "Hodgdon", "BENCHMARK": "Hodgdon", "CFE 223": "Hodgdon",
    "BL-C(2)": "Hodgdon", "LEVEREVOLUTION": "Hodgdon", "AR COMP": "Hodgdon", "AR-COMP": "Hodgdon",
}


def _split_sierra_powder(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    m = re.match(r'^IMR\s*(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "IMR", m.group(1).strip()
    m = re.match(r'^RE\s*(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Alliant", f"Reloder {m.group(1)}"
    m = re.match(r'^R-\s*(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Alliant", f"Reloder {m.group(1)}"
    if raw.upper().startswith("POWER PRO"):
        return "Ramshot", raw
    m = re.match(r'^A\s*(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Accurate", f"A{m.group(1)}"
    m = re.match(r'^H\s*(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Hodgdon", f"H{m.group(1)}"
    m = re.match(r'^N\s*(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Vihtavuori", f"N{m.group(1)}"
    m = re.match(r'^RS\s+(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "Ramshot", m.group(1).strip()
    m = re.match(r'^PP\s+(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "Ramshot", f"Power Pro {m.group(1)}"
    if raw.upper().startswith("WIN "):
        return "Winchester", raw[4:].strip()
    m = re.match(r'^W\s+(\d\S*.*)$', raw, re.IGNORECASE)
    if m:
        return "Winchester", m.group(1).strip()
    mapped = _SIERRA_POWDER_MAP.get(raw.upper())
    if mapped:
        return mapped, raw
    return None, raw


def _sierra_line_rows(page) -> list[tuple[float, str]]:
    """Clusters a size-filtered page's words into (top, text) lines (gap-based, same rationale
    as _barnes_col_rows: a fixed rounding grid can split a row that differs by under a point)."""
    words = page.extract_words()
    words.sort(key=lambda w: w["top"])
    clusters: list[list] = []
    for w in words:
        if clusters and w["top"] - clusters[-1][0]["top"] <= 2.5:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    out = []
    for ws in clusters:
        ws_sorted = sorted(ws, key=lambda w: w["x0"])
        out.append((min(w["top"] for w in ws), ws_sorted))
    return out


def parse_sierra_pdf(pdf_bytes: bytes) -> dict:
    caliber = None
    # "First-seen" spec values become the source-level summary (admin list, etc.); "cur_*"
    # tracks whichever section's values are currently in effect, re-updated on every "Test
    # Specifications:" page — a single Sierra file can contain more than one such section
    # (confirmed: "223 Remington (Bolt Gun)" has a Winchester-case section at 1-12"/1-8" twist,
    # then a GFL-case section at 1-12" only) and every following data row needs to carry
    # whichever section it actually came from, not just the file's first section.
    first_twist = first_barrel_length = first_trim_length = first_test_firearm = None
    cur_twist = cur_barrel_length = cur_trim_length = cur_case_brand = cur_primer_display = cur_test_firearm = None
    rows: list[dict] = []
    rejected: list[str] = []
    diagram_bytes = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [p.filter(lambda obj: obj.get("size", 0) <= 20) for p in pdf.pages]

        for pi, page in enumerate(pages):
            text = page.extract_text() or ""
            if "Test Specifications:" in text:
                if caliber is None:
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    for l in lines:
                        if l in ("SIERRA RELOADING MANUAL • SIXTH EDITION", "Sierra Reloading Manual Sixth Edition", "V. RIFLE RELOADING DATA"):
                            continue
                        caliber = normalize_caliber(l)
                        break
                    if diagram_bytes is None:
                        diagram_bytes = _diagram_from_curves(pdf.pages[pi], x0_frac=0.4, rotate=-90)
                m = re.search(r'Firearm Used:\s*(.+)', text)
                if m:
                    cur_test_firearm = m.group(1).strip()
                m = re.search(r'Twist:\s*(\S+(?:\s+and\s+\S+)?)', text)
                if m:
                    cur_twist = m.group(1)
                m = re.search(r'Barrel Length:\s*([\d.]+.?)', text)
                if m:
                    cur_barrel_length = m.group(1)
                m = re.search(r'Trim-to[- ]Length:\s*([\d.]+.?)', text)
                if m:
                    cur_trim_length = m.group(1)
                m = re.search(r'Case:\s*(.+)', text)
                if m:
                    cur_case_brand = m.group(1).strip()
                m = re.search(r'Primer:\s*(.+)', text)
                if m:
                    cur_primer_display = m.group(1).strip()
                if first_twist is None:
                    first_twist, first_barrel_length = cur_twist, cur_barrel_length
                    first_trim_length, first_test_firearm = cur_trim_length, cur_test_firearm
                continue

            if "Bullet Caliber Weight Type C.O.A.L." not in text:
                continue

            bullets: list[tuple[float, str, str, str, str]] = []  # (weight, type, dia, coal, sku)
            for l in text.split("\n"):
                l = l.strip()
                m = _SIERRA_BULLET_ROW_RE.match(l)
                if m:
                    bullets.append((float(m.group("weight")), m.group("type").strip(), m.group("dia"), m.group("coal"), m.group("sku")))
            if not bullets:
                rejected.append(f"[no bullets found] page {pi}")
                continue

            line_rows = _sierra_line_rows(page)
            header_idx = None
            for i, (top, ws) in enumerate(line_rows):
                joined = " ".join(w["text"] for w in ws)
                if joined.startswith("Powder Velocity"):
                    header_idx = i
                    break
            if header_idx is None:
                rejected.append(f"[no velocity header] page {pi}")
                continue

            header_words = [w for w in line_rows[header_idx][1] if re.match(r'^\d+$', w["text"])]
            velocity_cols = [(w["x0"], int(w["text"])) for w in header_words]
            if not velocity_cols:
                rejected.append(f"[empty velocity header] page {pi}")
                continue
            # Powder names can themselves contain numbers ("IMR 3031", "RE 15", "H 4350") so
            # "is this token numeric" can't distinguish name from charge value — position can:
            # every real charge value's x0 lines up with a velocity column's x0 (confirmed
            # against real coordinates), and every velocity column sits well to the right of
            # where any powder name renders, so a word left of the first column (with a safety
            # margin) is always part of the name, never a value.
            name_boundary = velocity_cols[0][0] - 15

            for top, ws in line_rows[header_idx + 1:]:
                joined = " ".join(w["text"] for w in ws)
                if joined.startswith(("Energy Ft", "Special Load", "Accuracy Load", "Hunting Load", "Sierra does not", "*")):
                    continue
                if re.match(r'^\d+$', joined.strip()):
                    continue  # bare page-number footer
                # The "INDICATES MAXIMUM LOAD..." disclaimer footer (and "The Bulletsmiths(TM)")
                # renders each character doubled or repeated several times over (a bold-via-
                # overstrike effect) on some files instead of the clean single-copy text seen
                # elsewhere — collapsing repeated-character runs before matching catches it
                # regardless of how many times it's doubled.
                collapsed = re.sub(r'(.)\1+', r'\1', joined).upper()
                if "INDICATES" in collapsed or "MINIMUM CHARGE" in collapsed or "SMITH" in collapsed:
                    continue
                name_words = [w for w in ws if w["x0"] < name_boundary]
                value_words = [w for w in ws if w["x0"] >= name_boundary]
                if not name_words:
                    rejected.append(joined)
                    continue
                name = " ".join(w["text"] for w in name_words)
                if not value_words or any(not re.match(r'^\d+(?:\.\d+)?$', w["text"]) for w in value_words):
                    rejected.append(joined)
                    continue
                powder_brand, powder_name = _split_sierra_powder(name)
                for vw in value_words:
                    charge = float(vw["text"])
                    nearest = min(velocity_cols, key=lambda c: abs(c[0] - vw["x0"]))
                    if abs(nearest[0] - vw["x0"]) > 5:
                        rejected.append(f"[unaligned value] {joined}")
                        continue
                    velocity = nearest[1]
                    for weight, btype, dia, coal, sku in bullets:
                        rows.append({
                            "bullet_weight_gr": weight, "bullet_brand": "Sierra", "bullet_model": btype,
                            "bullet_dia": dia, "bullet_code": sku,
                            "case_brand": cur_case_brand, "primer_display": cur_primer_display,
                            "twist": cur_twist, "barrel_length": cur_barrel_length,
                            "trim_length": cur_trim_length, "test_firearm": cur_test_firearm,
                            "powder_brand": powder_brand, "powder_name": powder_name, "coal": coal,
                            "start_charge_gr": charge, "start_is_compressed": False,
                            "start_velocity_fps": velocity,
                            "start_pressure": None, "start_pressure_unit": None, "start_density_pct": None,
                            "max_charge_gr": charge, "max_is_compressed": False,
                            "max_velocity_fps": velocity,
                            "max_pressure": None, "max_pressure_unit": None, "max_density_pct": None,
                        })

    return {
        "caliber": caliber, "twist": first_twist, "barrel_length": first_barrel_length,
        "trim_length": first_trim_length, "test_firearm": first_test_firearm,
        "data_as_of": None, "rows": rows, "rejected_lines": rejected,
        "manufacturer": "Sierra", "scope_bullet_weight_gr": None, "scope_bullet_model": None,
        "case_diagram_bytes": diagram_bytes,
    }


# ── Nosler PDF parsing ───────────────────────────────────────────────────────
# One PDF = one caliber + one bullet-weight class (occasionally two adjacent weights, e.g.
# "223 Rem - 34/35 grain"). Unlike the flattened text seen when this format was first scoped
# from chat-pasted content, extract_words() on the real file turns out to already be cleanly
# ordered — the load-density percentages land at the same top as their charge/velocity row, no
# position-based reconstruction drama needed beyond the same top-clustering used for
# Sierra/Barnes. Column membership is by x0 range (confirmed against every real file, all share
# page width 342): name < 60, abbreviation code ~118-121 (AB/BT/PT/etc, informational only, not
# stored), charge ~60-84, "*" (most-accurate flag) ~84-90, "MAX." keyword ~90-110, velocity
# ~110-130, load density % >= 290.
#
# Each powder has up to 3 charge-level rows (MAX / mid / starting); only the first carries the
# powder's name — continuation rows are blank in that column, *except* when Nosler's own layout
# highlights one powder as a boxed "Most Accurate Load"/"Powder Tested" callout, where those
# literal words render in the name column instead of being blank. Both cases mean "same powder as
# the row above", not a new one, so the name only advances when a real (non-placeholder) name
# appears.
#
# The bullet-family table (AccuBond®/Ballistic Tip®/Partition®/etc., one row per candidate
# bullet) all share this one charge table — confirmed via the original brainstorm/approval this
# session: fan out one row per candidate bullet, matching Barnes/Sierra's precedent for "several
# distinct bullets share one manufacturer-published table" rather than needing separate tables.

_NOSLER_PLACEHOLDER_NAMES = {"MOST ACCURATE", "POWDER TESTED"}


_NOSLER_POWDER_MAP = {"MAGPRO": "Accurate"}


def _split_nosler_powder(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    m = re.match(r'^IMR\s*(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "IMR", m.group(1).strip()
    m = re.match(r'^RL(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Alliant", f"Reloder {m.group(1)}"
    m = re.match(r'^AA\s*(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Accurate", f"A{m.group(1)}"
    m = re.match(r'^PP\s+(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "Ramshot", f"Power Pro {m.group(1)}"
    m = re.match(r'^W(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Winchester", m.group(1).strip()
    m = re.match(r'^H(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Hodgdon", raw
    m = re.match(r'^N(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Vihtavuori", raw
    mapped = _SIERRA_POWDER_MAP.get(raw.upper()) or _NOSLER_POWDER_MAP.get(raw.upper())
    if mapped:
        return mapped, raw
    return None, raw


def parse_nosler_pdf(pdf_bytes: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        diagram_bytes = _diagram_from_image(page, pick="first", crop_left_frac=0.53)

    words.sort(key=lambda w: w["top"])
    clusters: list[list] = []
    for w in words:
        if clusters and w["top"] - clusters[-1][0]["top"] <= 2.5:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    rows = [sorted(c, key=lambda w: w["x0"]) for c in clusters]

    # Title: "223 Rem - 34/35 grain" / "Version 9.0" — a second, sometimes garbled, duplicate
    # title row exists further down (the clean caliber+dia badge on that row is read separately
    # below), so search for whichever row actually matches rather than assuming a fixed index.
    caliber = scope_weight = None
    title_re = re.compile(r'^(?P<caliber>.+?)\s*-\s*(?P<weight>\d+(?:\.\d+)?)(?:/\d+)*\s*grain$', re.IGNORECASE)
    for r in rows:
        title = " ".join(w["text"] for w in r if w["x0"] < 250)
        m = title_re.match(title)
        if m:
            caliber = normalize_caliber(m.group("caliber"))
            scope_weight = float(m.group("weight"))
            break

    dia = None
    for r in rows:
        cal_word = next((w for w in r if w["text"] == "Cal."), None)
        if cal_word:
            dia_word = next((w for w in r if w["x0"] > cal_word["x0"] and "\"" in w["text"]), None)
            if dia_word:
                dm = re.search(r'\.\d+', dia_word["text"])
                if dm:
                    dia = dm.group(0)
            break

    barrel_length = twist = case_brand = primer_display = max_saami_oal = None
    bullets: list[tuple[float, str, str, str, str, str, str]] = []  # (weight, model, code, style, coal, bc, sd)
    header_idx = None
    for i, r in enumerate(rows):
        joined = " ".join(w["text"] for w in r)
        if joined.startswith("CASE TYPE:"):
            case_brand = " ".join(w["text"] for w in r if w["x0"] > 55 and w["x0"] < 130).strip() or None
            primer_display = " ".join(w["text"] for w in r if w["x0"] > 275).strip() or None
        elif joined.startswith("MAXIMUM SAAMI"):
            max_saami_oal_w = next((w["text"] for w in r if 130 < w["x0"] < 160), None)
            max_saami_oal = max_saami_oal_w.rstrip('"') if max_saami_oal_w else None
        elif "BARREL" in joined and "Length/Make" in joined:
            barrel_length = next((w["text"] for w in r if w["x0"] > 275 and w["x0"] < 295), None)
        elif "BARREL" in joined and "Twist" in joined:
            twist = next((w["text"] for w in r if w["x0"] > 275), None)
        elif joined.startswith("POWDER") and "CHG." in joined:
            header_idx = i
            break
        elif re.search(r'\d+gr\.\s', joined) and any(re.match(r'^[A-Z][A-Z&]*$', w["text"]) for w in r if 95 < w["x0"] < 135):
            # The short brand code (AB/BT/BST/CC/RDF/VMG/...) always sits between the model
            # name and the weight — its x0 is a more reliable name/weight boundary than a
            # fixed threshold (a fixed "<60" cutoff truncated multi-word names like "AccuBond
            # Long Range" whose 3rd word starts past x0=60).
            code_w = next((w for w in r if 95 <= w["x0"] < 135), None)
            name = " ".join(w["text"] for w in r if w["x0"] < code_w["x0"]) if code_w else None
            name = re.sub(r'[®™]', '', name).strip() if name else None
            weight_w = next((w for w in r if 130 < w["x0"] < 160), None)
            coal_w = next((w for w in r if 190 < w["x0"] < 260), None)
            bc_w = next((w["text"] for w in r if 265 < w["x0"] < 300), None)
            sd_w = next((w["text"] for w in r if w["x0"] >= 300), None)
            # Bullet profile ("HPBT", "Spitzer", "FB Tipped") sits between the weight and
            # C.O.L. columns — width varies (1-2 words), so join everything in that gap
            # rather than assuming a fixed column count.
            style = " ".join(w["text"] for w in r if weight_w and coal_w and weight_w["x0"] < w["x0"] < coal_w["x0"]) or None
            wm = re.match(r'^(\d+(?:\.\d+)?)', weight_w["text"] if weight_w else "")
            if name and wm and coal_w and bc_w and sd_w:
                # Strip the trailing " so coal is stored the same way Hodgdon's parser stores
                # it (bare number, no inch mark) — the UI appends the " uniformly for every
                # manufacturer, so a manufacturer that bakes it into the raw text would double up.
                bullets.append((float(wm.group(1)), name, code_w["text"], style, coal_w["text"].rstrip('"'), bc_w, sd_w))

    if header_idx is None or not bullets:
        return {
            "caliber": caliber, "twist": twist, "barrel_length": barrel_length, "trim_length": None,
            "max_saami_oal": max_saami_oal,
            "data_as_of": None, "rows": [], "rejected_lines": ["[couldn't locate bullet table or powder header]"],
            "manufacturer": "Nosler", "scope_bullet_weight_gr": scope_weight, "scope_bullet_model": None,
            "case_diagram_bytes": diagram_bytes,
        }

    load_rows: list[dict] = []
    rejected: list[str] = []
    current_name = None
    for r in rows[header_idx + 1:]:
        joined = " ".join(w["text"] for w in r)
        if joined.startswith(("All cartridge", "“Because", "In no event", "* =", "** =")):
            break
        if joined.startswith("TYPE GRS."):
            continue  # second line of the powder-table column header
        name_words = [w["text"] for w in r if w["x0"] < 60]
        name_candidate = " ".join(name_words).strip()
        if name_candidate and name_candidate.upper() not in _NOSLER_PLACEHOLDER_NAMES:
            current_name = name_candidate
        if current_name is None:
            rejected.append(joined)
            continue
        charge_w = next((w for w in r if 60 <= w["x0"] < 84), None)
        # "*" (most accurate load tested) sits right after the charge value, x0≈85.5. "**"
        # (compressed load) sits in a completely different column, x0≈274.9, right before the
        # load-density figure it's actually annotating — confirmed via real word positions, not
        # assumed; a same-x0-range guess here previously left is_compressed always False.
        is_compressed = any(w["text"] == "**" for w in r if 260 <= w["x0"] < 290)
        is_recommended = any(w["text"] == "*" for w in r if 84 <= w["x0"] < 92)
        velocity_w = next((w for w in r if 110 <= w["x0"] < 132), None)
        density_w = next((w for w in r if w["x0"] >= 290), None)
        if charge_w is None or velocity_w is None:
            rejected.append(joined)
            continue
        try:
            charge = float(charge_w["text"])
            velocity = int(velocity_w["text"])
            density = float(density_w["text"].rstrip("%")) if density_w else None
        except ValueError:
            rejected.append(joined)
            continue
        powder_brand, powder_name = _split_nosler_powder(current_name)
        for weight, model, code, style, coal, bc, sd in bullets:
            load_rows.append({
                "bullet_weight_gr": weight, "bullet_brand": "Nosler", "bullet_model": model,
                "bullet_code": code, "bullet_style": style, "bullet_bc": float(bc), "bullet_sd": float(sd),
                "bullet_dia": dia,
                "case_brand": case_brand, "primer_display": primer_display,
                "powder_brand": powder_brand, "powder_name": powder_name, "coal": coal,
                "is_recommended": is_recommended,
                "start_charge_gr": charge, "start_is_compressed": is_compressed,
                "start_velocity_fps": velocity,
                "start_pressure": None, "start_pressure_unit": None, "start_density_pct": density,
                "max_charge_gr": charge, "max_is_compressed": is_compressed,
                "max_velocity_fps": velocity,
                "max_pressure": None, "max_pressure_unit": None, "max_density_pct": density,
            })

    return {
        "caliber": caliber, "twist": twist, "barrel_length": barrel_length, "trim_length": None,
        "max_saami_oal": max_saami_oal,
        "data_as_of": None, "rows": load_rows, "rejected_lines": rejected,
        "manufacturer": "Nosler", "scope_bullet_weight_gr": scope_weight, "scope_bullet_model": None,
        "case_diagram_bytes": diagram_bytes,
    }


# ── Hornady Handbook parsing (whole-book, one-time import) ─────────────────────
# The single 1024-page/41MB book covers ~200 cartridge chapters (Rifle Data + Handgun Data
# sections) rather than one PDF per caliber. Navigation is TOC-driven: the table of contents
# (physical pages 3-12) is parsed for {cartridge name -> printed page number}, "See data at
# hornady.com/data" entries are skipped (no data in the book), and each chapter's physical page
# range is derived from a confirmed-constant +11 offset between printed and physical page number
# (verified at both the start of Rifle Data, page 130, and deep into Handgun Data, page 786).
#
# Per-chapter structure: physical page 1 is the intro (spec box + vector-drawn case diagram,
# same rasterize-the-curves approach as Sierra). Remaining pages hold one or more weight-class
# sections each (a page can hold more than one, unlike Sierra) — up to 3 candidate bullets listed
# side by side (gap-split into column groups, same technique as Barnes' 2-column layout), sharing
# one velocity-matrix charge table (POWDER name + charge "NN.N gr." per velocity column, matched
# by x0 position against the header's velocity columns — same technique as Sierra, confirmed
# these charge values line up with their column the same way).

_HORNADY_WEIGHT_RE = re.compile(r'^(?P<weight>\d+(?:\.\d+)?)\s*GRAIN\s+BULLETS$', re.IGNORECASE)

# Unlike Sierra/Barnes' compact abbreviations, Hornady's powder column already spells out most
# brands in full ("Alliant RL-10X", "Hodgdon H335", "Accurate 2460", "Ramshot TAC") — simple
# prefix stripping, not abbreviation-decoding, confirmed against every real chapter parsed.
_HORNADY_POWDER_BRANDS = ("Accurate", "Alliant", "Hodgdon", "IMR", "Ramshot", "Winchester")


def _split_hornady_powder(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    if raw.upper().startswith("VIHT "):
        return "Vihtavuori", raw[5:].strip()
    if raw.upper().startswith("NORMA "):
        return "Norma", raw[6:].strip()
    if raw.upper().startswith("VECTAN "):
        return "Vectan", raw[7:].strip()
    if raw.upper().startswith("SW "):
        return "Shooters World", raw[3:].strip()
    if raw.upper().startswith("SHOOTER'S WORLD ") or raw.upper().startswith("SHOOTERS WORLD "):
        return "Shooters World", raw.split(" ", 2)[2].strip()
    if raw.upper().startswith("WIN "):
        return "Winchester", raw[4:].strip()
    if raw.upper().startswith("HYBRID"):
        return "Hodgdon", raw
    if raw.upper().startswith("POWER PRO") or raw.upper() == "MAGPRO":
        return "Ramshot" if raw.upper().startswith("POWER PRO") else "Accurate", raw
    if raw.upper().startswith("LIL'") or raw.upper().startswith("LIL "):
        return "Alliant", raw
    for brand in _HORNADY_POWDER_BRANDS:
        if raw.lower().startswith(brand.lower() + " "):
            return brand, raw[len(brand):].strip()
    # Bare Hodgdon-style compact codes ("H4198", "H322", "H4831 SC" with a stray space) not
    # prefixed with the brand name.
    m = re.match(r'^H(\d\S*)$', raw.replace(" ", ""), re.IGNORECASE)
    if m:
        return "Hodgdon", raw
    _HORNADY_ALLIANT_BARE = {
        "BULLSEYE", "RED DOT", "GREEN DOT", "BLUE DOT", "HERCO", "UNIQUE", "POWER PISTOL",
        "AMERICAN SELECT", "SOLO 1000", "ENFORCER", "TRUE BLUE",
    }
    _HORNADY_HODGDON_BARE = {
        "TITEGROUP", "HS-6", "LONGSHOT", "CFE PISTOL", "CLAYS", "UNIVERSAL", "HP-38", "BE-86",
        "RETUMBO", "US 869", "TRAIL BOSS", "STABALL 6.5", "STABALL MATCH", "STABALL HD",
    }
    if raw.upper() in _HORNADY_ALLIANT_BARE:
        return "Alliant", raw
    if raw.upper() in _HORNADY_HODGDON_BARE:
        return "Hodgdon", raw
    if raw.upper() in ("ZIP", "MAGNUM"):
        return "Ramshot", raw
    if raw.upper() == "SILHOUETTE":
        return "Accurate", raw
    # Everything else bare (Varget/Benchmark/BL-C(2)/CFE 223/AR-Comp/TAC/X-Terminator/etc.) —
    # cross-checked against this app's own already-imported Hodgdon/Ramshot data, same maps
    # Sierra/Barnes use.
    mapped = _SIERRA_POWDER_MAP.get(raw.upper()) or _BARNES_POWDER_MAP.get(raw.upper())
    if mapped:
        return mapped, raw
    return None, raw


_HORNADY_BULLET_RE = re.compile(r'^(?P<weight>\d+(?:\.\d+)?)\s*gr\.\s*(?P<model>.+)$', re.IGNORECASE)


def _split_lyman_powder(raw: str) -> tuple[str | None, str]:
    """Lyman's 50th Edition prints bare/lightly-abbreviated powder names (no consistent brand
    prefix), including its own house abbreviation "Rx" for Alliant Reloder (e.g. "Rx15" = Reloder
    15 — confirmed against the real page images; the numbers match Reloder's actual product line,
    and Sierra's own manual abbreviates the same powder "RE15"/"R-15"). Names are normalized to
    match this app's existing Hodgdon-catalog-derived naming (e.g. "H-380" -> "H380", "IMR-4064" ->
    "IMR 4064") so in-stock cross-referencing (exact brand+name match) actually finds hits — see
    project memory on why that match is exact-only, never fuzzy.
    """
    raw = raw.strip().lstrip("*").strip()
    if raw.upper().startswith("NORMA "):
        return "Norma", raw[6:].strip()
    m = re.match(r'^IMR[\s-]+(\S.*)$', raw, re.IGNORECASE)
    if m:
        return "IMR", f"IMR {m.group(1).strip()}"
    m = re.match(r'^R[Xx](\d+)$', raw)
    if m:
        return "Alliant", f"Reloder {m.group(1)}"
    m = re.match(r'^H-?(\d\S*)$', raw, re.IGNORECASE)
    if m:
        return "Hodgdon", f"H{m.group(1)}"
    if raw.upper().startswith("STABALL"):
        return "Winchester", raw
    if raw.upper() in ("HYBRID", "HYBRID 100V"):
        return "Hodgdon", raw
    if raw == "748":
        return "Winchester", "W748"
    if raw == "760":
        return "Winchester", "W760"
    if raw == "2700":
        return "Accurate", "A2700"
    if raw.upper() == "2000-MR":
        return "Alliant", "Power Pro 2000-MR"
    if raw.upper() == "5744":
        return "Accurate", "A5744"
    if raw.upper() in ("VARGET", "CFE 223", "SUPERFORMANCE", "H4831SC"):
        return "Hodgdon", raw
    if raw.upper() in ("BIG GAME", "HUNTER", "TAC", "X-TERMINATOR"):
        return "Ramshot", raw
    if raw.upper() == "N160" or re.match(r'^N\d{3}$', raw, re.IGNORECASE):
        return "Vihtavuori", raw
    return None, raw


def _hornady_toc(pdf) -> tuple[list[tuple[str, int, str]], int]:
    """Returns ([(cartridge_name, printed_page, section), ...] for real (non web-only) entries
    in TOC order, offset) where offset = physical_page_index - printed_page_number.
    """
    toc_text = "\n".join((pdf.pages[i].extract_text() or "") for i in range(3, 13))
    lines = toc_text.split("\n")
    section = None
    entries: list[tuple[str, int, str]] = []
    # Most entries use a continuous dot-leader ("223 Remington..............160") but some use
    # a spaced one ("22 K Hornet . . . . . . . .143") — [.\s]{4,} catches both.
    entry_re = re.compile(r'^(.*?)[.\s]{4,}(\d+)\s*$')
    for l in lines:
        s = l.strip()
        if s == "Rifle Data":
            section = "Rifle"
            continue
        if s == "Handgun Data":
            section = "Handgun"
            continue
        if s.startswith("Charts and Conversion") or s.startswith("Rifle Dies"):
            section = None
            continue
        if section is None or "See data at" in s:
            continue
        m = entry_re.match(s)
        if m:
            entries.append((m.group(1).strip(), int(m.group(2)), section))

    # Confirm the printed-to-physical offset against two known anchors rather than assuming it.
    offset = None
    for i in range(len(pdf.pages)):
        t = pdf.pages[i].extract_text() or ""
        first_line = t.split("\n")[0] if t else ""
        m = re.match(r'^(\d+)\s+Hornady Handbook', first_line)
        if m and entries:
            offset = i - int(m.group(1))
            break
    return entries, offset if offset is not None else 11


def _hornady_row_clusters(page) -> list[tuple[float, list]]:
    words = page.extract_words()
    # The sideways cartridge-name tab (mirrored, e.g. "reguR"/"tenroH") alternates which edge of
    # the page it sits on chapter-page to chapter-page (confirmed x0 fractions ~0.03 / ~0.93 on a
    # 432pt-wide page) — same alternating pattern as Barnes' watermark, exclude both edges.
    words = [w for w in words if 0.05 * page.width < w["x0"] < 0.9 * page.width]
    words.sort(key=lambda w: w["top"])
    clusters: list[list] = []
    for w in words:
        if clusters and w["top"] - clusters[-1][0]["top"] <= 2.5:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    return [(min(w["top"] for w in c), sorted(c, key=lambda w: w["x0"])) for c in clusters]


def _hornady_gap_split(ws: list, min_gap: float = 15) -> list[list]:
    groups = [[ws[0]]]
    for w in ws[1:]:
        if w["x0"] - groups[-1][-1]["x1"] > min_gap:
            groups.append([w])
        else:
            groups[-1].append(w)
    return groups


def _parse_hornady_chapter(pdf, start: int, end: int) -> dict:
    """start/end are physical page indices (inclusive) for one chapter."""
    intro_text = pdf.pages[start].extract_text() or ""
    caliber = twist = barrel_length = trim_length = case_brand = primer_display = None
    diagram_bytes = None
    # The real title is always the line immediately before "Rifle:"/"Handgun:" — other short
    # lines above it are the mirrored sideways cartridge-tab text and the case diagram's own
    # dimension callouts (e.g. ".294", "1.047"), which normalize_caliber() would otherwise
    # accept unchanged since it only validates recognized cartridge names, not rejects garbage.
    intro_lines = [l.strip() for l in intro_text.split("\n")]
    for i, s in enumerate(intro_lines):
        if s.startswith(("Rifle:", "Handgun:")) and i > 0:
            caliber = normalize_caliber(intro_lines[i - 1])
            break
    m = re.search(r'Barrel:[.\s]+([\d.]+)["”],\s*(.+?)\s*Twist\b', intro_text)
    if m:
        barrel_length, twist = m.group(1) + '"', m.group(2)
    m = re.search(r'Case:[.\s]+(.+?)\s*Max\. Case Length:', intro_text)
    if m:
        case_brand = m.group(1).strip(" .")
    m = re.search(r'Primer:[.\s]+(.+?)\s*Case Trim Length:', intro_text)
    if m:
        primer_display = m.group(1).strip(" .")
    m = re.search(r'Case Trim Length:[.\s]+([\d.]+["”])', intro_text)
    if m:
        trim_length = m.group(1)
    diagram_bytes = _diagram_from_curves(pdf.pages[start], x0_frac=0.15)

    rows: list[dict] = []
    rejected: list[str] = []
    weight = dia = None
    bullets: list[tuple[float, str]] = []  # (col_x0, "weight gr model")
    coals: dict[float, str] = {}
    velocity_cols: list[tuple[float, int]] = []
    in_data = False
    for pi in range(start, end + 1):
        for top, ws in _hornady_row_clusters(pdf.pages[pi]):
            joined = " ".join(w["text"] for w in ws)
            if not joined.strip():
                continue
            if joined.startswith("SECTIONAL DENSITY"):
                bullets, coals, velocity_cols, in_data = [], {}, [], False
                continue
            wm = _HORNADY_WEIGHT_RE.search(joined.replace("DIAMETER:", " DIAMETER:").split(" DIAMETER:")[0].strip())
            if wm:
                weight = float(wm.group("weight"))
                dm = re.search(r'DIAMETER:\s*([\d.]+["”]?)', joined)
                if dm:
                    dia = dm.group(1).rstrip('"”')
                continue
            if joined.startswith(("Item No.", "G1 B.C.")):
                continue
            if joined.startswith("C.O.L.:"):
                for grp in _hornady_gap_split(ws):
                    gtext = " ".join(w["text"] for w in grp)
                    cm = re.search(r'C\.O\.L\.:\s*([\d.]+["”]?)', gtext)
                    if cm:
                        coals[grp[0]["x0"]] = cm.group(1).rstrip('"”')
                continue
            if re.match(r'^\d+(?:\.\d+)?\s*gr\.', joined) and weight is not None:
                for grp in _hornady_gap_split(ws):
                    gtext = " ".join(w["text"] for w in grp)
                    bm = _HORNADY_BULLET_RE.match(gtext)
                    if bm:
                        bullets.append((grp[0]["x0"], f"{bm.group('model').strip()}"))
                continue
            if joined.startswith("VELOCITY (FPS"):
                continue
            if joined.startswith("POWDER") and any(re.match(r'^\d{3,5}$', w["text"]) for w in ws):
                velocity_cols = [(w["x0"], int(w["text"])) for w in ws if re.match(r'^\d{3,5}$', w["text"])]
                in_data = bool(velocity_cols)
                continue
            if joined.startswith(("Create custom ballistic", "NOTE:", "INDICATES MAXIMUM", "Rifle Data", "Handgun Data", "Hornady Handbook")) \
                    or re.match(r'^\d+$', joined.strip()) or re.match(r'^\d+\s+Hornady Handbook', joined):
                continue
            if not in_data or not bullets or not velocity_cols:
                continue
            if joined.startswith(("*NOTE", "NOTE:")) or "yard" in joined.lower() or "hornady.com/bc" in joined.lower():
                continue  # footnote text, not a data row
            name_words = [w for w in ws if w["x0"] < velocity_cols[0][0] - 20]
            value_words = [w for w in ws if w["x0"] >= velocity_cols[0][0] - 20 and w["text"] != "gr."]
            if not name_words or not value_words:
                rejected.append(joined)
                continue
            name = " ".join(w["text"] for w in name_words)
            powder_brand, powder_name = _split_hornady_powder(name)
            for vw in value_words:
                try:
                    charge = float(vw["text"])
                except ValueError:
                    rejected.append(joined)
                    continue
                nearest = min(velocity_cols, key=lambda c: abs(c[0] - vw["x0"]))
                if abs(nearest[0] - vw["x0"]) > 6:
                    continue
                velocity = nearest[1]
                for col_x0, model in bullets:
                    coal = min(coals.items(), key=lambda kv: abs(kv[0] - col_x0))[1] if coals else None
                    rows.append({
                        "bullet_weight_gr": weight, "bullet_brand": "Hornady", "bullet_model": model,
                        "bullet_dia": dia,
                        "case_brand": case_brand, "primer_display": primer_display,
                        "powder_brand": powder_brand, "powder_name": powder_name, "coal": coal,
                        "start_charge_gr": charge, "start_is_compressed": False,
                        "start_velocity_fps": velocity,
                        "start_pressure": None, "start_pressure_unit": None, "start_density_pct": None,
                        "max_charge_gr": charge, "max_is_compressed": False,
                        "max_velocity_fps": velocity,
                        "max_pressure": None, "max_pressure_unit": None, "max_density_pct": None,
                    })

    return {
        "caliber": caliber, "twist": twist, "barrel_length": barrel_length, "trim_length": trim_length,
        "data_as_of": None, "rows": rows, "rejected_lines": rejected,
        "manufacturer": "Hornady", "scope_bullet_weight_gr": None, "scope_bullet_model": None,
        "case_diagram_bytes": diagram_bytes,
        "page_range": (start, end),
    }


def parse_hornady_book(pdf_bytes: bytes, max_chapters: int | None = None) -> dict:
    """Returns {"chapters": [chapter_dict, ...], "skipped": [(name, reason), ...]}."""
    chapters = []
    skipped = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        entries, offset = _hornady_toc(pdf)
        physical_entries = [(name, page + offset, section) for name, page, section in entries]
        for i, (name, phys_start, section) in enumerate(physical_entries):
            if max_chapters is not None and len(chapters) >= max_chapters:
                break
            next_start = physical_entries[i + 1][1] if i + 1 < len(physical_entries) else phys_start + 12
            phys_end = min(next_start - 1, phys_start + 20, len(pdf.pages) - 1)
            if phys_start >= len(pdf.pages) or phys_end < phys_start:
                skipped.append((name, "page range out of bounds"))
                continue
            try:
                chapter = _parse_hornady_chapter(pdf, phys_start, phys_end)
            except Exception as e:
                skipped.append((name, f"parse error: {e}"))
                continue
            if not chapter["caliber"] or not chapter["rows"]:
                skipped.append((name, "no caliber or no rows parsed"))
                continue
            chapter["source_name"] = name
            chapter["section"] = section
            chapters.append(chapter)
    return {"chapters": chapters, "skipped": skipped}


# ── Serializers ──────────────────────────────────────────────────────────────

def _source_summary(s: "models.ReloadDataSource") -> dict:
    return {
        "id": s.id, "manufacturer": s.manufacturer, "caliber": s.caliber, "twist": s.twist,
        "scope_bullet_weight_gr": s.scope_bullet_weight_gr, "scope_bullet_model": s.scope_bullet_model,
        "barrel_length": s.barrel_length, "trim_length": s.trim_length, "max_saami_oal": s.max_saami_oal,
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
        "bullet_model": l.bullet_model, "bullet_code": l.bullet_code, "bullet_style": l.bullet_style,
        "bullet_dia": l.bullet_dia,
        "bullet_bc": l.bullet_bc, "bullet_bc_g7": l.bullet_bc_g7, "bullet_sd": l.bullet_sd,
        "case_brand": l.case_brand, "primer_display": l.primer_display,
        "powder_brand": l.powder_brand, "powder_name": l.powder_name, "coal": l.coal,
        "is_recommended": l.is_recommended, "is_max_load": l.is_max_load, "is_reduced_load": l.is_reduced_load,
        "start_charge_gr": l.start_charge_gr, "start_velocity_fps": l.start_velocity_fps,
        "start_pressure": l.start_pressure, "start_pressure_unit": l.start_pressure_unit,
        "start_density_pct": l.start_density_pct, "start_is_compressed": l.start_is_compressed,
        "max_charge_gr": l.max_charge_gr, "max_velocity_fps": l.max_velocity_fps,
        "max_pressure": l.max_pressure, "max_pressure_unit": l.max_pressure_unit,
        "max_density_pct": l.max_density_pct, "max_is_compressed": l.max_is_compressed,
        "powder_in_stock": powder_key in in_stock_powders,
        "bullet_in_stock": bullet_in_stock,
        "bullet_owned_model": bullet_owned_model,
        "manufacturer": l.source.manufacturer if l.source else None,
        "caliber": l.source.caliber if l.source else None,
        # Row-level twist/barrel_length/trim_length/test_firearm win when set (Sierra, whose
        # single file can span more than one "Test Specifications" section) — everyone else only
        # ever sets the source-level column, so this is a no-op fallback for them.
        "twist": l.twist if l.twist is not None else (l.source.twist if l.source else None),
        "barrel_length": l.barrel_length if l.barrel_length is not None else (l.source.barrel_length if l.source else None),
        "trim_length": l.trim_length if l.trim_length is not None else (l.source.trim_length if l.source else None),
        "max_saami_oal": l.source.max_saami_oal if l.source else None,
        "max_case_length": l.source.max_case_length if l.source else None,
        "rcbs_shell_holder": l.source.rcbs_shell_holder if l.source else None,
        "test_firearm": l.test_firearm if l.test_firearm is not None else (l.source.test_firearm if l.source else None),
        "data_as_of": l.source.data_as_of if l.source else None,
        "source_file_path": l.source.source_file_path if l.source else None,
        "case_diagram_path": l.source.case_diagram_path if l.source else None,
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

async def _import_one_reload_pdf(file: UploadFile, manufacturer_hint: str | None, db: Session) -> dict:
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        return {"filename": filename, "error": "Not a PDF file"}
    content = await file.read()
    if len(content) > 20_000_000:
        return {"filename": filename, "error": "PDF too large"}

    try:
        parsed = parse_reload_pdf(content, manufacturer_hint, filename=filename)
    except HTTPException as e:
        return {"filename": filename, "error": e.detail}
    if not parsed["caliber"]:
        return {"filename": filename, "error": "Couldn't determine caliber from this PDF"}
    if not parsed["rows"]:
        return {"filename": filename, "manufacturer": parsed["manufacturer"], "caliber": parsed["caliber"], "error": "No loads could be parsed from this PDF"}

    # Replace scope: manufacturer + caliber + (weight/model only for manufacturers whose files
    # are scoped narrower than a whole caliber — None matches None via SQLAlchemy's `== None`,
    # so Hodgdon/Sierra/Barnes keep their existing whole-caliber replace behavior unchanged).
    existing = db.query(models.ReloadDataSource).filter(
        models.ReloadDataSource.manufacturer == parsed["manufacturer"],
        models.ReloadDataSource.caliber == parsed["caliber"],
        models.ReloadDataSource.scope_bullet_weight_gr == parsed.get("scope_bullet_weight_gr"),
        models.ReloadDataSource.scope_bullet_model == parsed.get("scope_bullet_model"),
    ).all()
    for s in existing:
        if s.source_file_path:
            delete_uploaded_file(s.source_file_path)
        if s.case_diagram_path:
            delete_uploaded_file(s.case_diagram_path)
        db.delete(s)
    db.flush()

    source_file_path = None
    await file.seek(0)
    try:
        source_file_path = await save_uploaded_document(file, "reloaddata")
    except Exception:
        source_file_path = None

    case_diagram_path = _save_case_diagram(parsed.get("case_diagram_bytes"))

    source = models.ReloadDataSource(
        manufacturer=parsed["manufacturer"], caliber=parsed["caliber"],
        scope_bullet_weight_gr=parsed.get("scope_bullet_weight_gr"),
        scope_bullet_model=parsed.get("scope_bullet_model"),
        twist=parsed["twist"], barrel_length=parsed["barrel_length"], trim_length=parsed["trim_length"],
        max_saami_oal=parsed.get("max_saami_oal"), max_case_length=parsed.get("max_case_length"),
        rcbs_shell_holder=parsed.get("rcbs_shell_holder"), test_firearm=parsed.get("test_firearm"),
        data_as_of=parsed["data_as_of"], original_filename=filename,
        source_file_path=source_file_path, case_diagram_path=case_diagram_path,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(source)
    db.flush()

    db.add_all([
        models.ReloadDataLoad(source_id=source.id, **row) for row in parsed["rows"]
    ])
    db.commit()

    if parsed["rejected_lines"]:
        print(f"[reload-data] {len(parsed['rejected_lines'])} rejected line(s) for {parsed['manufacturer']} {parsed['caliber']!r}:")
        for l in parsed["rejected_lines"]:
            print(f"[reload-data]   {l!r}")

    return {
        "filename": filename, "manufacturer": parsed["manufacturer"], "caliber": parsed["caliber"],
        "rows_imported": len(parsed["rows"]), "rows_rejected": len(parsed["rejected_lines"]),
        "data_as_of": parsed["data_as_of"], "rejected_sample": parsed["rejected_lines"][:10],
    }


@router.post("/reload-data/upload")
async def upload_reload_data(
    request: Request,
    files: list[UploadFile] = File(...),
    manufacturer: str = Form(None),
    db: Session = Depends(get_db),
):
    _require_admin(request)
    manufacturer_hint = manufacturer if manufacturer and manufacturer.lower() != "auto" else None
    results = []
    for file in files:
        results.append(await _import_one_reload_pdf(file, manufacturer_hint, db))
    return results


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
    if source.case_diagram_path:
        delete_uploaded_file(source.case_diagram_path)
    db.delete(source)
    db.commit()
    return {"ok": True}


@router.get("/reload-data/filters")
def reload_data_filters(
    manufacturer: str = Query(None), caliber: str = Query(None), powder_brand: str = Query(None),
    db: Session = Depends(get_db),
):
    manufacturers = [r[0] for r in db.query(models.ReloadDataSource.manufacturer).distinct().order_by(models.ReloadDataSource.manufacturer).all()]
    caliber_q = db.query(models.ReloadDataSource.caliber).distinct()
    if manufacturer:
        caliber_q = caliber_q.filter(models.ReloadDataSource.manufacturer == manufacturer)
    calibers = [r[0] for r in caliber_q.order_by(models.ReloadDataSource.caliber).all()]

    # The Reloading Data Center browse tab is organized one-tab-per-manufacturer, so every
    # filter list — not just caliber — is scoped to whichever manufacturer's tab is active.
    load_q = db.query(models.ReloadDataLoad).join(models.ReloadDataSource)
    if manufacturer:
        load_q = load_q.filter(models.ReloadDataSource.manufacturer == manufacturer)
    bullet_brands = [r[0] for r in load_q.with_entities(models.ReloadDataLoad.bullet_brand).filter(
        models.ReloadDataLoad.bullet_brand.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.bullet_brand).all()]
    powder_brands = [r[0] for r in load_q.with_entities(models.ReloadDataLoad.powder_brand).filter(
        models.ReloadDataLoad.powder_brand.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.powder_brand).all()]
    # Powder name is additionally scoped to the selected powder brand, once one is picked —
    # otherwise the dropdown offers every brand's powders regardless of the brand filter.
    powder_name_q = load_q
    if powder_brand:
        powder_name_q = powder_name_q.filter(models.ReloadDataLoad.powder_brand == powder_brand)
    powder_names = [r[0] for r in powder_name_q.with_entities(models.ReloadDataLoad.powder_name).filter(
        models.ReloadDataLoad.powder_name.isnot(None)
    ).distinct().order_by(models.ReloadDataLoad.powder_name).all()]

    # Bullet weight options are additionally scoped to the caliber typed into the caliber
    # field (once it resolves to a real caliber) — a "weight" only makes sense in the context
    # of a specific cartridge, unlike the other filters which are fine at manufacturer scope.
    bullet_weights = []
    if caliber:
        weight_q = load_q.filter(models.ReloadDataSource.caliber == normalize_caliber(caliber))
        bullet_weights = [r[0] for r in weight_q.with_entities(models.ReloadDataLoad.bullet_weight_gr).filter(
            models.ReloadDataLoad.bullet_weight_gr.isnot(None)
        ).distinct().order_by(models.ReloadDataLoad.bullet_weight_gr).all()]

    return {
        "manufacturers": manufacturers, "calibers": calibers, "bullet_brands": bullet_brands,
        "powder_brands": powder_brands, "powder_names": powder_names, "bullet_weights": bullet_weights,
    }


@router.get("/reload-data/loads")
def list_reload_data_loads(
    manufacturer: str = Query(None), caliber: str = Query(None), bullet_weight_gr: float = Query(None),
    bullet_brand: str = Query(None), powder_brand: str = Query(None),
    powder_name: str = Query(None), in_stock_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.ReloadDataLoad).join(models.ReloadDataSource).options(joinedload(models.ReloadDataLoad.source))
    if manufacturer:
        q = q.filter(models.ReloadDataSource.manufacturer == manufacturer)
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


_HORNADY_BOOK_PATH = "static/reloading_data/hornady/Hornday 10th Edition.pdf"


@router.post("/admin/reload-data/import-hornady-book")
def import_hornady_book_endpoint(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    if not os.path.exists(_HORNADY_BOOK_PATH):
        raise HTTPException(404, f"Hornady Handbook PDF not found at {_HORNADY_BOOK_PATH}")
    with open(_HORNADY_BOOK_PATH, "rb") as f:
        pdf_bytes = f.read()

    parsed = parse_hornady_book(pdf_bytes)

    # Wipe all existing Hornady sources and re-insert fresh — this is a whole-book batch import,
    # not the per-file scoped replace the other manufacturers use, so re-running it always
    # produces a clean, complete re-import rather than trying to diff ~200 chapters individually.
    existing = db.query(models.ReloadDataSource).filter(models.ReloadDataSource.manufacturer == "Hornady").all()
    for s in existing:
        if s.source_file_path:
            delete_uploaded_file(s.source_file_path)
        if s.case_diagram_path:
            delete_uploaded_file(s.case_diagram_path)
        db.delete(s)
    db.flush()

    pdfium_doc = pdfium.PdfDocument(_HORNADY_BOOK_PATH)
    total_rows = 0
    for chapter in parsed["chapters"]:
        start, end = chapter["page_range"]

        # Per-chapter PDF excerpt so "view source" never has to serve the whole 41MB/1024-page
        # book — same pypdfium2 page-range extraction confirmed working during planning.
        excerpt_doc = pdfium.PdfDocument.new()
        excerpt_doc.import_pages(pdfium_doc, pages=list(range(start, end + 1)))
        buf = io.BytesIO()
        excerpt_doc.save(buf)
        excerpt_filename = f"reloaddata_{uuid.uuid4()}.pdf"
        with open(os.path.join(UPLOAD_DIR, excerpt_filename), "wb") as f:
            f.write(buf.getvalue())
        source_file_path = f"/static/uploads/{excerpt_filename}"

        case_diagram_path = _save_case_diagram(chapter.get("case_diagram_bytes"))

        source = models.ReloadDataSource(
            manufacturer="Hornady", caliber=chapter["caliber"],
            scope_bullet_weight_gr=None, scope_bullet_model=None,
            twist=chapter["twist"], barrel_length=chapter["barrel_length"], trim_length=chapter["trim_length"],
            data_as_of=None, original_filename=f"Hornady Handbook — {chapter['source_name']} ({chapter['section']})",
            source_file_path=source_file_path, case_diagram_path=case_diagram_path,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(source)
        db.flush()
        db.add_all([models.ReloadDataLoad(source_id=source.id, **row) for row in chapter["rows"]])
        total_rows += len(chapter["rows"])
    db.commit()

    if parsed["skipped"]:
        print(f"[reload-data] Hornady import skipped {len(parsed['skipped'])} chapter(s):")
        for name, reason in parsed["skipped"]:
            print(f"[reload-data]   {name!r}: {reason}")

    return {
        "chapters_imported": len(parsed["chapters"]),
        "chapters_skipped": len(parsed["skipped"]),
        "rows_imported": total_rows,
    }
