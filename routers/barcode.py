import html
import io
import json
import os
import re
import uuid
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import database as _models
from config import UPLOAD_DIR
from dependencies import get_db

router = APIRouter()

_UPC_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads', 'upc_cache')
_FLARESOLVERR_URL = os.environ.get('FLARESOLVERR_URL', 'http://192.168.125.2:8191')


def _download_upc_image(upc: str, url: str) -> str | None:
    """Download a product image, compress it, and save locally. Returns the /static/… path or None."""
    os.makedirs(_UPC_CACHE_DIR, exist_ok=True)
    dest = os.path.join(_UPC_CACHE_DIR, f"{upc}.jpg")
    if os.path.exists(dest):
        return f"/static/uploads/upc_cache/{upc}.jpg"
    # Backwards compat: check old extension-preserving filenames
    for old_ext in ('.png', '.webp', '.gif'):
        old = os.path.join(_UPC_CACHE_DIR, f"{upc}{old_ext}")
        if os.path.exists(old):
            return f"/static/uploads/upc_cache/{upc}{old_ext}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "homelab-inventory/1.8"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
        try:
            from PIL import Image as _Img, ImageOps as _IOps
            import io as _io
            img = _Img.open(_io.BytesIO(data))
            img = _IOps.exif_transpose(img)
            img.thumbnail((800, 800), _Img.LANCZOS)
            out = _io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=75, optimize=True)
            data = out.getvalue()
        except Exception:
            pass
        with open(dest, 'wb') as f:
            f.write(data)
        return f"/static/uploads/upc_cache/{upc}.jpg"
    except Exception:
        return None


def upsert_upc_cache(db: Session, upc: str, **kwargs) -> None:
    """Create or update a UPC cache entry with the supplied keyword fields."""
    if not upc:
        return
    upc = _normalize_upc(upc)
    entry = db.query(_models.UpcCache).filter(_models.UpcCache.upc == upc).first()
    if entry is None:
        entry = _models.UpcCache(upc=upc)
        db.add(entry)
    for k, v in kwargs.items():
        if v is not None and hasattr(entry, k):
            setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc).isoformat()
    db.commit()


def _cache_to_response(entry: "_models.UpcCache") -> dict:
    return {
        "upc": entry.upc,
        "title": entry.title,
        "product_type": entry.product_type,
        "brand": entry.brand,
        "product_line": entry.product_line,
        "powder_name": entry.powder_name,
        "caliber": entry.caliber,
        "weight_gr": entry.weight_gr,
        "bullet_type": entry.bullet_type,
        "rounds_per_box": entry.rounds_per_box,
        "price": None,
        "bc_g1": entry.bc_g1,
        "primer_type": entry.primer_type,
        "primer_model": entry.primer_model,
        "image_path": entry.image_path,
        "ammo_category": getattr(entry, 'ammo_category', None),
        "factory_velocity_fps": getattr(entry, 'factory_velocity_fps', None),
        "muzzle_energy_ftlb": getattr(entry, 'muzzle_energy_ftlb', None),
        "lead_free": getattr(entry, 'lead_free', None),
        "case_type": getattr(entry, 'case_type', None),
        "reloadable": getattr(entry, 'reloadable', None),
        "source": "cache",
    }

_BC_REF: list[dict] | None = None

def _load_bc_ref() -> list[dict]:
    global _BC_REF
    if _BC_REF is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'static', 'bc_reference.json')
        with open(os.path.abspath(path)) as f:
            _BC_REF = json.load(f)
    return _BC_REF


def _parse_weight(text: str) -> float | None:
    # Match "140gr", "140 gr", "140grains", "129g" (Barnes-style bare "g")
    m = re.search(r'(\d+(?:\.\d+)?)\s*g(?:r(?:ain)?s?)?\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # Speer/Sierra "caliber-weight-style" format: e.g. "277-130-BT" → weight=130
    m2 = re.search(r'(?<!\d)(?:2[2-9]\d|3[0-9]\d|4[0-5]\d)-(\d{2,3})-[A-Za-z]', text)
    if m2:
        return float(m2.group(1))
    return None


def _parse_rounds(text: str) -> int | None:
    m = re.search(r'(\d+)\s*(?:count|ct\.?|rounds?|rds?\.?|pack|pk|box)\b', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r'\b(\d+)\s*-?\s*(?:count|pack|pk|rd)\b', text, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    # Shotgun pack: "5 100" at end = 5-round box, 100 per case
    m3 = re.search(r'\b(\d{1,2})\s+\d{2,4}\s*$', text.strip())
    if m3 and int(m3.group(1)) <= 25:
        return int(m3.group(1))
    # "20/200" box/case format — take the box count
    m4 = re.search(r'\b(\d{1,3})/(\d{2,4})\b', text)
    if m4:
        box, case = int(m4.group(1)), int(m4.group(2))
        if box <= 100 and case > box:
            return box
    return None


# Cartridge-name canonicalization — collapses retailer/site phrasing differences
# (".308 Win", "308 Winchester Ammo", "308 WIN") down to one form ("308 Winchester").
# Only for cartridge-name-style caliber text (Ammo/casing/load-data). Bare bore-diameter
# values used for BulletInventory.caliber (e.g. ".277") are a separate convention and are
# never passed through this — see the Speer/Sierra and bore-only branches below.
_CALIBER_TRAILING_JUNK = re.compile(
    r'\s*(ammo|ammunition|cartridges?|rifle ammo|pistol ammo|handgun ammo)\.?\s*$',
    re.IGNORECASE,
)
_CALIBER_WORD_EXPANSIONS = {
    'win': 'Winchester', 'rem': 'Remington', 'mag': 'Magnum',
    'spl': 'Special', 'spc': 'Special', 'wby': 'Weatherby',
    'creedmore': 'Creedmoor',  # common misspelling
}
# A bare number with no qualifying word is only ever really one cartridge in practice.
_CALIBER_BARE_NUMBER_INFERENCE = {
    '22': '22 LR',
    '270': '270 Winchester',
}


def normalize_caliber(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r'^\.(?=\d)', '', s)  # ".308 Win" → "308 Win"
    s = re.sub(r'(?<=\d)\s+mm\b', 'mm', s, flags=re.IGNORECASE)  # "7 mm" → "7mm"
    prev = None
    while prev != s:
        prev = s
        s = _CALIBER_TRAILING_JUNK.sub('', s).strip()
    tokens = s.split(' ')
    out = []
    for i, tok in enumerate(tokens):
        key = tok.lower().rstrip('.')
        if i == 0:
            # Never touch the leading number/bore token (avoids mangling e.g. "300 AAC").
            out.append(tok)
        elif key in _CALIBER_WORD_EXPANSIONS:
            out.append(_CALIBER_WORD_EXPANSIONS[key])
        elif tok.isupper() and tok.isalpha() and len(tok) > 4:
            # Shouted-case full word (e.g. site-supplied "WINCHESTER") → Title case.
            # Short all-caps tokens (NATO, PRC, WSM, GA, LR...) are left alone — they're
            # genuine acronyms, not just a retailer's ALL CAPS styling.
            out.append(tok.capitalize())
        else:
            out.append(tok)
    s = re.sub(r'\s+', ' ', ' '.join(out)).strip()
    s = _CALIBER_BARE_NUMBER_INFERENCE.get(s, s)
    return s or None


def _parse_caliber(text: str) -> str | None:
    t = text.lower()

    # Shotgun gauges — check before generic patterns. Gauge/bore phrasing keeps its own
    # convention (e.g. ".410 Bore") and is never run through cartridge normalization.
    gauge_map = [
        (r'\b12\s*ga(?:uge)?\b', '12 Gauge'),
        (r'\b20\s*ga(?:uge)?\b', '20 Gauge'),
        (r'\b28\s*ga(?:uge)?\b', '28 Gauge'),
        (r'\.410\b|410\s*(?:bore|ga(?:uge)?)', '.410 Bore'),
    ]
    for gp, label in gauge_map:
        if re.search(gp, t, re.IGNORECASE):
            return label

    # Speer/Sierra "caliber-weight-style" format: e.g. "277-130-BT" → caliber=.277
    # This is a bare bore diameter (bullet components), not a cartridge name — no
    # normalization, so it stays distinct from Ammo/casing caliber values.
    m = re.search(r'(?<!\d)(2[2-9]\d|3[0-9]\d|4[0-5]\d)-\d{2,3}-[A-Za-z]', text)
    if m:
        return f'.{m.group(1)}'

    # Named abbreviations that need explicit return values — cartridge names, always
    # normalized so retailer-phrasing differences collapse to one canonical form.
    abbrevs = [
        (r'\b6\.5\s*(?:mm\s*)?creedmoor\b', '6.5 Creedmoor'),
        (r'\b6\.5\s*creed\b',               '6.5 Creedmoor'),
        (r'\b6\.5\s*cm\b',                  '6.5 Creedmoor'),
        (r'\b6\s*(?:mm\s*)?creedmoor\b',    '6 Creedmoor'),
        (r'\b6\.5\s*(?:mm\s*)?prc\b',       '6.5 PRC'),
        (r'\b6\.5\s*(?:mm\s*)?grendel\b',   '6.5 Grendel'),
        (r'\b6\.8\s*(?:mm\s*)?western\b',   '6.8 Western'),
        (r'\b7\s*mm\s*rem(?:ington)?\s*mag\b', '7mm Rem Mag'),
        (r'\b7\s*mm\s*prc\b',               '7mm PRC'),
        (r'\b308\s*win(?:chester)?\b',      '.308 Win'),
        (r'\b30\s*-\s*06\b',               '.30-06'),
        (r'\b300\s*win(?:chester)?\s*mag\b', '.300 Win Mag'),
        (r'\b338\s*lapua\b',               '.338 Lapua'),
        (r'\b243\s*win(?:chester)?\b',      '.243 Win'),
        (r'\b223\s*rem(?:ington)?\b',       '.223 Rem'),
        (r'\b5\.56\s*(?:mm\s*)?nato\b',     '5.56 NATO'),
        (r'\b224\s*valkyrie\b',            '.224 Valkyrie'),
        (r'\b6\s*mm\s*arc\b',              '6mm ARC'),
    ]
    for abbr, name in abbrevs:
        if re.search(abbr, t, re.IGNORECASE):
            return normalize_caliber(name)

    cartridge_patterns = [
        r'\b6\.5-284\b',
        r'\b6\.5x55\b',
        r'\b7mm-08\b',
        r'\b\.308\s*win(?:chester)?\b',
        r'\b\.30-06\b',
        r'\b\.300\s*prc\b',
        r'\b\.300\s*wsm\b',
        r'\b\.22-250\b',
    ]
    for p in cartridge_patterns:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            raw = m.group(0).strip()
            raw = raw.upper() if raw.startswith('.') or raw[0].isdigit() else raw.title()
            return normalize_caliber(raw)

    # Bare bore-diameter fallback (no full cartridge name found) — kept in its original
    # dot-prefixed / lowercase-mm form, not run through cartridge-name normalization.
    bore_only_patterns = [
        r'(?<!\d)\.\d{2,3}(?!\d)',   # .277, .264, .308 — lookbehind/ahead avoids matching decimals
        r'\b\d+(?:\.\d+)?mm\b',      # 7mm, 6.5mm — last resort numeric fallback
    ]
    for p in bore_only_patterns:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            raw = m.group(0).strip()
            if raw.endswith('mm'):
                return raw.lower()  # 6.5mm, 7mm — keep lowercase
            return raw.upper() if raw.startswith('.') or raw[0].isdigit() else raw.title()
    return None


def _parse_bullet_type(text: str) -> str | None:
    # Barnes abbreviated product names used in UPC databases
    if re.search(r'\bLr\s*Xbt\b', text, re.IGNORECASE): return 'LRX'
    if re.search(r'\bTt\s*Sx\b', text, re.IGNORECASE):  return 'TTSX'
    if re.search(r'\bTac\s*Tx\b', text, re.IGNORECASE): return 'TAC-TX'
    keywords = [
        'ELD-X', 'ELD-M', 'ELD Match', 'A-TIP', 'SST', 'GMX', 'FTX', 'InterBond',
        'InterLock', 'XTP', 'V-Max',
        'MatchKing', 'Tipped MatchKing', 'TMK', 'GameKing', 'ProHunter',
        'Hybrid', 'OTM', 'VLD', 'Juggernaut',
        'AccuBond', 'Ballistic Tip', 'Partition', 'E-Tip', 'RDF',
        'TTSX', 'TSX', 'LRX', 'TAC-TX',
        'Scenar', 'Mega', 'FMJ', 'FMJBT', 'Lock Base',
        'Trophy Bonded', 'Fusion', 'Power-Shok',
        'Gold Dot', 'Hot-Cor', 'DeepCurl',
        'PSP BT', 'PSP', 'PSPBT',
        'FMJ', 'FMJBT', 'BTHP', 'HPBT', 'HP', 'SP', 'BT',
        'Soft Point', 'Hollow Point', 'Boat Tail',
        'Power-Point', 'Silvertip',
        'Core-Lokt', 'CoreLokt',
        'Slug', 'Sabot Slug', 'Buckshot', 'Birdshot',
    ]
    t = text
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', t, re.IGNORECASE):
            return kw
    return None


def _parse_product_line(text: str) -> str | None:
    # Barnes abbreviated product names used in UPC databases
    if re.search(r'\bLr\s*Xbt\b', text, re.IGNORECASE): return 'LRX'
    if re.search(r'\bTt\s*Sx\b', text, re.IGNORECASE):  return 'TTSX'
    if re.search(r'\bTac\s*Tx\b', text, re.IGNORECASE): return 'TAC-TX'
    # Aliases: product names as they appear in retailer titles → canonical bc_reference.json name
    if re.search(r'\bELD\s*-?\s*X\b', text, re.IGNORECASE):          return 'ELD-X'
    if re.search(r'\bELD\s*-?\s*M(?:atch)?\b', text, re.IGNORECASE): return 'ELD-M'
    # Bare "ELD" → ELD-M (Hornady Match uses ELD-M; ELD-X is always labelled with an X)
    if re.search(r'\bELD\b', text, re.IGNORECASE):
        return 'ELD-M'
    known_lines = [
        # Hornady
        'ELD-X', 'ELD-M', 'A-TIP', 'SST', 'GMX', 'FTX', 'V-Max', 'XTP',
        'Precision Hunter', 'Critical Defense', 'Critical Duty', 'American Gunner',
        'Outfitter', 'Subsonic', 'BLACK', 'Superformance',
        # Sierra
        'MatchKing', 'Tipped MatchKing', 'GameKing', 'Hybrid', 'OTM', 'VLD', 'Juggernaut', 'RDF',
        # Nosler
        'AccuBond Long Range', 'AccuBond', 'Ballistic Tip', 'Partition', 'E-Tip',
        'Trophy Grade', 'Defense', 'Custom Competition',
        # Barnes
        'TTSX', 'TSX', 'LRX', 'VOR-TX', 'TAC-X',
        # Lapua
        'Scenar-L', 'Scenar', 'Mega', 'Lock Base',
        # Federal
        'Gold Medal Match', 'Gold Medal Berger', 'Gold Medal',
        'Trophy Bonded Tip', 'Trophy Bonded',
        'Fusion', 'Power-Shok', 'American Eagle', 'Vital-Shok',
        'Punch', 'HST', 'Hydra-Shok', 'Force X2',
        'Expedition Big Game Long Range', 'Expedition Big Game',
        'Terminal Ascent', 'Edge TLR',
        # Winchester
        'Power-Point', 'Silvertip', 'Super-X', 'Super Suppressed',
        'Deer Season XP', 'Varmint X', 'Defender', 'PDX1',
        'Ranger', 'Train & Defend',
        # Remington
        'Core-Lokt', 'Premier Match', 'Golden Saber', 'HTP', 'UMC', 'Golden Bullet',
        'Express', 'Slugger', 'AccuTip', 'Managed-Recoil', 'Disruptor',
        # CCI
        'Mini-Mag', 'Stinger', 'Velocitor', 'Blazer Brass', 'Blazer', 'Clean-22', 'Quiet',
        # Speer
        'Gold Dot', 'Hot-Cor', 'Lawman',
        # PMC
        'Bronze', 'X-Tac', 'Xtac', 'Starfire',
        # Black Hills / Fiocchi / Sig / Norma / misc
        'Black Hills', 'Match', 'Premier Match',
        'Shooting Dynamics', 'Elite Performance', 'V-Crown', 'Elite Hunter',
        'Oryx', 'TipStrike', 'MRP',
        # Traditions (muzzleloader projectiles)
        'Smackdown Carnivore', 'Smackdown', 'Carnivore',
    ]
    t = text
    for line in sorted(known_lines, key=len, reverse=True):
        if re.search(r'\b' + re.escape(line) + r'\b', t, re.IGNORECASE):
            return line
    return None


def _infer_ammo_category(caliber: str, title: str) -> str | None:
    """Infer ammo_category from caliber and title. Returns centerfire/handgun/rimfire/shotgun/shotgun_slug/muzzleloader or None."""
    t = ((caliber or '') + ' ' + (title or '')).lower()

    if re.search(r'muzzleloader|black\s*powder|percussion', t):
        return 'muzzleloader'

    # Rimfire calibers
    if re.search(r'\b\.22\s*(lr|long\s*rifle|short|long|cb|wmr|mag|winchester\s*mag)\b|\b\.17\s*(hmr|wsm|mach\s*2)\b', t):
        return 'rimfire'

    # Shotgun slug (check before generic shotgun)
    if re.search(r'\bslug\b', t) and re.search(r'\bgauge\b|\bga\b|\.410\b|\bshell\b', t):
        return 'shotgun_slug'
    if re.search(r'\bslug\b', t) and not re.search(r'\brifle\b|\bpistol\b', t):
        return 'shotgun_slug'

    # Shotgun
    if re.search(r'\d+\s*gauge|\d+\s*ga\b|\.410\b|\bshotgun\b|\bshot\s*shell\b|\bbirdshot\b|\bbuckshot\b', t):
        return 'shotgun'

    # Handgun / pistol calibers
    if re.search(r'\b9\s*mm\b|\b9x19\b|9\s*luger|\.380\s*acp|\.380\s*auto|\b\.45\s*acp\b|\b\.45\s*auto\b|'
                 r'\.40\s*s\s*&\s*w|\.40\s*sw|\b10\s*mm\b|\b\.357\s*mag|\b\.357\s*sig|\b\.44\s*mag|'
                 r'\b\.38\s*spl|\b\.38\s*special|\b\.32\s*acp|\b\.25\s*acp|\b\.45\s*gap|'
                 r'\b5\.7\s*x\s*28|\b4\.6\s*x\s*30|\bpistol\b|\bhandgun\b', t):
        return 'handgun'

    # Centerfire rifle (keyword or caliber pattern)
    if re.search(r'\bcenterfire\b|\brifle\b', t):
        return 'centerfire'
    if re.search(r'\b\.22[3-9]\b|\b5\.56|\b\.243\b|\b\.270\b|\b\.30[0-9-]|\b\.308\b|'
                 r'\b30-06|\b7\s*mm|\b7x|\b6\.5|\b6\.\d|\b\.300\b|\b\.338\b|'
                 r'\b\.350\b|\b\.375\b|\b\.416\b|\b\.45-70\b|\b\.458\b|'
                 r'\b\.50\b|\b\.510\b|\b8x|\b7\.62', t):
        return 'centerfire'

    return None


def _parse_primer_model(text: str) -> str | None:
    # Must have a letter suffix (e.g. 41A, 209A) OR be a known primer model number
    # Avoid matching generic counts like "97 Count", "20 Rounds"
    _KNOWN_MODELS = {'41', '34', '200', '205', '209', '210', '215', '250', '400', '450', '500'}
    m = re.search(r'\b(\d{2,3}[A-Za-z]{1,3}(?:SC)?)\b', text)
    if m:
        suffix = re.sub(r'^\d+', '', m.group(1)).upper()
        if suffix not in ('G', 'GR', 'GRS'):
            return m.group(1)
    m2 = re.search(r'\b(\d{2,3})\b', text)
    if m2 and m2.group(1) in _KNOWN_MODELS:
        return m2.group(1)
    return None


def _parse_primer_type(text: str) -> str | None:
    t = text.lower()
    if re.search(r'small\s*rifle\s*magnum', t): return 'Small Rifle Magnum'
    if re.search(r'large\s*rifle\s*magnum', t): return 'Large Rifle Magnum'
    if re.search(r'small\s*rifle', t):          return 'Small Rifle'
    if re.search(r'large\s*rifle', t):          return 'Large Rifle'
    if re.search(r'small\s*pistol\s*magnum', t): return 'Small Pistol Magnum'
    if re.search(r'large\s*pistol\s*magnum', t): return 'Large Pistol Magnum'
    if re.search(r'small\s*pistol', t):          return 'Small Pistol'
    if re.search(r'large\s*pistol', t):          return 'Large Pistol'
    return None


def _parse_powder_name(title: str) -> tuple[str | None, str | None]:
    """Returns (brand, name) for powder products."""
    known = {
        'hodgdon': ['H4350', 'H4831', 'H4831SC', 'H1000', 'H4895', 'Varget', 'Benchmark',
                    'CFE 223', 'CFE BLK', 'H322', 'H335', 'H380', 'Lil\'Gun', 'Retumbo',
                    'IMR 4350', 'IMR 4831', 'IMR 4064', 'IMR 4166', 'IMR 4451',
                    'IMR 8208 XBR', 'Trail Boss'],
        'alliant':  ['Reloder 16', 'Reloder 17', 'Reloder 19', 'Reloder 23', 'Reloder 26',
                     'Power Pro 2000-MR', 'Power Pro 300-MP', 'AR-Comp', 'Power Pro 4000-MR'],
        'vihtavuori': ['N140', 'N150', 'N160', 'N165', 'N170', 'N555', 'N560', 'N565',
                       '20N29', '24N41', 'N133', 'N135'],
        'accurate': ['2230', '2460', '2495', '4064', '4350', 'LT-30', 'LT-32', 'No. 5',
                     'No. 7', 'No. 9'],
        'ramshot': ['Hunter', 'Big Game', 'Magnum', 'LRT', 'TAC', 'X-Terminator'],
        'shooters world': ['Precision', 'Long Rifle', 'Match Rifle', 'Duty Pistol'],
    }
    t = title
    for brand, names in known.items():
        for name in sorted(names, key=len, reverse=True):
            if re.search(r'\b' + re.escape(name) + r'\b', t, re.IGNORECASE):
                return brand.title(), name
    return None, None


_JUNK_BRANDS = {'brand', 'manufacturer', 'n/a', 'na', 'unknown', 'other', 'generic', 'misc'}

def _parse_brand(raw_brand: str, title: str) -> str | None:
    raw_brand = html.unescape(raw_brand or '').strip()
    known_brands = [
        'Hornady', 'Federal', 'Winchester', 'Remington', 'Nosler',
        'Sierra', 'Berger', 'Lapua', 'Barnes', 'Speer',
        'CCI', 'Fiocchi', 'PMC', 'Sellier & Bellot', 'PPU',
        'Black Hills', 'HSM', 'Weatherby', 'Magtech', 'Wolf',
        'Norma', 'Sako', 'Vihtavuori', 'Cutting Edge', 'Hammer', 'Traditions',
    ]
    if raw_brand and raw_brand.lower() not in _JUNK_BRANDS:
        raw_l = raw_brand.lower()
        for b in known_brands:
            b_l = b.lower()
            # Match exact, or prefix ("Barnes Bullets" → "Barnes")
            if raw_l == b_l or raw_l.startswith(b_l + ' '):
                return b
        # Unrecognized but non-junk — trust the manufacturer-supplied value as-is.
        # (Previously this scanned the full combined text — title + description +
        # offers — for a known brand name and let that win, which meant marketing
        # copy like "...cutting edge ballistic coefficients..." could hijack a
        # correct raw brand like "Traditions" into "Cutting Edge".)
        return raw_brand.title()
    # No usable manufacturer-supplied brand — fall back to scanning the title, but
    # prefer whichever known brand appears earliest (retailer titles conventionally
    # lead with the brand, e.g. "Barnes VOR-TX 308 Winchester..." — a naive first-in-list
    # match would wrongly pick "Winchester" from the caliber name over "Barnes").
    best, best_pos = None, None
    for b in known_brands:
        m = re.search(r'\b' + re.escape(b) + r'\b', title, re.IGNORECASE)
        if m and (best_pos is None or m.start() < best_pos):
            best, best_pos = b, m.start()
    return best


def _caliber_matches_hint(caliber: str, hint: str) -> bool:
    """True when the leading numeric part of caliber matches the hint (e.g. '6.5 Creedmoor' ~ '6.5mm')."""
    if not caliber or not hint:
        return False
    def _lead(s: str) -> str:
        m = re.match(r'^[.]?(\d+(?:\.\d+)?)', s.strip().lstrip('.'))
        return m.group(1) if m else ''
    return bool(_lead(caliber) and _lead(caliber) == _lead(hint))


def _lookup_bc(brand: str, product_line: str | None, weight_gr: float | None,
               caliber: str | None = None) -> dict:
    if weight_gr is None:
        return {}
    ref = _load_bc_ref()
    brand_l = brand.lower() if brand else ''
    line_l = product_line.lower() if product_line else ''

    # Tier 1: brand + product_line + weight
    if line_l:
        for entry in ref:
            if (entry['brand'] == brand_l and
                    entry['product_line'] == line_l and
                    abs(entry['weight_gr'] - weight_gr) < 0.6):
                return {'bc_g1': entry.get('bc_g1')}

    # Tier 2: brand + weight only (unique match)
    candidates = [e for e in ref if e['brand'] == brand_l and abs(e['weight_gr'] - weight_gr) < 0.6]
    if len(candidates) == 1:
        return {'bc_g1': candidates[0].get('bc_g1')}

    # Tier 3: brand + weight + caliber (narrows multi-weight-matches by caliber)
    if caliber and candidates:
        cal_candidates = [e for e in candidates
                          if _caliber_matches_hint(caliber, e.get('caliber_hint', ''))]
        if len(cal_candidates) == 1:
            return {'bc_g1': cal_candidates[0].get('bc_g1')}
        # Multiple entries with same caliber — return if they all agree on BC (G1)
        if cal_candidates:
            bc_set = {e.get('bc_g1') for e in cal_candidates}
            if len(bc_set) == 1:
                return {'bc_g1': cal_candidates[0].get('bc_g1')}

    return {}


def _scrape_barcodelookup(upc: str) -> dict | None:
    """Fetch product data from barcodelookup.com via FlareSolverr. Returns a raw-data dict or None."""
    if not _FLARESOLVERR_URL:
        return None
    try:
        payload = json.dumps({
            "cmd": "request.get",
            "url": f"https://www.barcodelookup.com/{upc}",
            "maxTimeout": 45000,
        }).encode()
        req = urllib.request.Request(
            f"{_FLARESOLVERR_URL}/v1",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=55) as resp:
            d = json.loads(resp.read().decode())
        body = d.get("solution", {}).get("response", "")
        if not body or len(body) < 500:
            return None

        # Confirm the page is a product page for this UPC (not a 404 / login wall)
        if upc not in body:
            return None
        h1 = re.search(r'<h1[^>]*>\s*UPC\s+' + re.escape(upc) + r'\s*</h1>', body, re.IGNORECASE)
        if not h1:
            return None

        # Product title from <h4> (first meaningful one is the product name)
        h4 = re.search(r'<h4[^>]*>\s*(.*?)\s*</h4>', body, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', h4.group(1)).strip() if h4 else ''
        _noise = {'edit the product data', 'write a product review', 'log in to your api account', ''}
        if title.lower() in _noise:
            return None

        # Manufacturer lives inside a <span> after "Manufacturer: "
        mfr = re.search(r'Manufacturer:\s*<[^>]+>\s*([^<\n]{2,60})\s*</span>', body, re.IGNORECASE)
        raw_brand = mfr.group(1).strip() if mfr else ''

        # Store affiliate links carry product slugs in a nested ?url= query parameter
        raw_hrefs = re.findall(r'href="([^"]{20,})"', body)
        slug_words: list[str] = []
        for href in raw_hrefs:
            decoded = urllib.parse.unquote(href)
            parsed = urllib.parse.urlparse(decoded)
            qs = urllib.parse.parse_qs(parsed.query)
            inner_url = qs.get('url', [None])[0]
            if inner_url:
                inner_path = urllib.parse.urlparse(inner_url).path.rstrip('/')
                slug = inner_path.split('/')[-1]
                if len(slug) > 10:
                    slug_words.append(slug.replace('-', ' '))

        combined = f"{title} {raw_brand} {' '.join(slug_words[:6])}"

        return {"title": title, "raw_brand": raw_brand, "combined": combined}
    except Exception:
        return None


def _normalize_upc(upc: str) -> str:
    """Normalize UPC: strip leading zero from 13-digit EAN-13 that is really a UPC-A."""
    if len(upc) == 13 and upc.startswith('0'):
        return upc[1:]
    return upc


@router.get("/barcode/lookup")
def barcode_lookup(upc: str, db: Session = Depends(get_db)):
    if not re.match(r'^\d{6,14}$', upc):
        raise HTTPException(400, "Invalid UPC")

    upc = _normalize_upc(upc)

    # Local cache takes priority — user-corrected data is always best
    cached = db.query(_models.UpcCache).filter(_models.UpcCache.upc == upc).first()
    if cached:
        resp = _cache_to_response(cached)
        existing = db.query(_models.Ammo).filter(
            _models.Ammo.upc == upc, _models.Ammo.is_handload == False
        ).first()
        resp["existing_ammo_id"] = existing.id if existing else None
        return resp

    # If UPC is already in inventory (no cache entry yet), redirect immediately
    existing_ammo = db.query(_models.Ammo).filter(
        _models.Ammo.upc == upc, _models.Ammo.is_handload == False
    ).first()
    if existing_ammo:
        return {
            "upc": upc,
            "title": None,
            "product_type": "ammo",
            "existing_ammo_id": existing_ammo.id,
            "source": "inventory",
        }

    # ── Primary: UPC Item DB ──────────────────────────────────────────────────
    url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={urllib.parse.quote(upc)}"
    api_data: dict = {}
    _upcdb_ok = False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "homelab-inventory/1.6"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            api_data = json.loads(resp.read().decode())
        _upcdb_ok = True
    except Exception:
        pass

    items = api_data.get("items", []) if _upcdb_ok else []

    # ── Fallback: barcodelookup.com via FlareSolverr ──────────────────────────
    _scraped: dict | None = None
    if not items:
        _scraped = _scrape_barcodelookup(upc)
        if not _scraped and not _upcdb_ok:
            raise HTTPException(404, "UPC not found — lookup services unavailable")
        if not _scraped:
            raise HTTPException(404, "Barcode not found in UPC database")

    if _scraped:
        title = _scraped["title"]
        raw_brand = _scraped["raw_brand"]
        combined = _scraped["combined"]
        lowest_price = None
        api_images: list = []
    else:
        item = items[0]
        title = item.get("title") or item.get("description") or ""
        raw_brand = item.get("brand") or ""
        lowest_price = item.get("lowest_recorded_price")
        api_images = item.get("images") or []
        # Build a richer combined text from all text fields the API provides.
        # Offer/store titles from retailers often include grain weight and bullet type
        # even when the main product title doesn't.
        _extra_parts = [
            item.get("description") or "",
            item.get("model") or "",
            item.get("size") or "",
        ]
        for offer in (item.get("offers") or [])[:6]:
            _extra_parts.append(offer.get("title") or "")
        for store in (item.get("stores") or [])[:6]:
            _extra_parts.append(store.get("name") or "")
        combined = " ".join([title] + [p for p in _extra_parts if p])

    # Download product image once if available (UPC Item DB path only)
    image_path = None
    for img_url in api_images:
        if img_url:
            image_path = _download_upc_image(upc, img_url)
            if image_path:
                break

    brand = _parse_brand(raw_brand, combined)
    weight_gr = _parse_weight(combined)
    caliber = _parse_caliber(combined)
    bullet_type = _parse_bullet_type(combined)
    product_line = _parse_product_line(combined)
    rounds_per_box = _parse_rounds(combined)
    primer_type = _parse_primer_type(combined)
    powder_brand, powder_name = _parse_powder_name(combined)

    bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)

    # Infer product type so the frontend can auto-navigate to the right form
    _is_ammo_title  = bool(re.search(r'\b(?:ammo|ammunition|centerfire|rimfire|shotshell|slug|buckshot)\b', combined, re.IGNORECASE))
    _is_bullet_title = bool(re.search(r'\bbullets?\b', combined, re.IGNORECASE))
    # Product lines that only appear on component bullets, never on factory-ammo boxes
    _component_only = {'eld-x','eld-m','a-tip','matchking','tipped matchking','vld','hybrid',
                       'accubond','partition','lrx','ttsx','tsx','tac-tx','rdf','juggernaut','e-tip'}
    _is_component_line = bool(product_line and product_line.lower() in _component_only)

    if powder_name:
        product_type = "powder"
    elif primer_type or re.search(r'\bprimer\b', combined, re.IGNORECASE):
        product_type = "primer"
    elif _is_ammo_title:
        product_type = "ammo"
    elif rounds_per_box and caliber and not _is_bullet_title and not _is_component_line:
        product_type = "ammo"
    elif weight_gr and (bullet_type or bc_data or product_line):
        product_type = "bullet"
    elif caliber and not weight_gr and not rounds_per_box:
        product_type = "casing"
    else:
        product_type = None

    primer_model = _parse_primer_model(combined)
    ammo_category = _infer_ammo_category(caliber, combined) if product_type == 'ammo' else None

    # Persist to local cache so repeat scans never hit the internet
    upsert_upc_cache(db, upc,
        title=title,
        product_type=product_type,
        brand=powder_brand or brand,
        product_line=product_line,
        powder_name=powder_name,
        caliber=caliber,
        weight_gr=weight_gr,
        bullet_type=bullet_type,
        rounds_per_box=rounds_per_box,
        bc_g1=bc_data.get("bc_g1"),
        primer_type=primer_type,
        primer_model=primer_model,
        image_path=image_path,
        ammo_category=ammo_category,
    )

    existing = db.query(_models.Ammo).filter(
        _models.Ammo.upc == upc, _models.Ammo.is_handload == False
    ).first()

    return {
        "upc": upc,
        "title": title,
        "product_type": product_type,
        "brand": powder_brand or brand,
        "product_line": product_line,
        "powder_name": powder_name,
        "caliber": caliber,
        "weight_gr": weight_gr,
        "bullet_type": bullet_type,
        "rounds_per_box": rounds_per_box,
        "price": lowest_price,
        "bc_g1": bc_data.get("bc_g1"),
        "primer_type": primer_type,
        "primer_model": primer_model,
        "image_path": image_path,
        "ammo_category": ammo_category,
        "source": "scrape" if _scraped else "api",
        "existing_ammo_id": existing.id if existing else None,
    }


@router.get("/barcode/image-search")
def image_search(q: str):
    """Search DuckDuckGo for product images. Returns up to 8 thumbnail URLs."""
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    try:
        encoded_q = urllib.parse.quote(q)
        # Step 1: fetch DDG page to extract vqd token
        req1 = urllib.request.Request(
            f"https://duckduckgo.com/?q={encoded_q}&ia=images",
            headers={"User-Agent": ua}
        )
        with urllib.request.urlopen(req1, timeout=8) as r:
            html_body = r.read().decode("utf-8", errors="replace")
        vqd_match = re.search(r'vqd=(["\'])([^"\']+)\1', html_body)
        if not vqd_match:
            vqd_match = re.search(r'vqd=([\d-]+)', html_body)
        if not vqd_match:
            return {"images": []}
        vqd = vqd_match.group(2) if vqd_match.lastindex == 2 else vqd_match.group(1)
        # Step 2: query DDG image API
        api_url = (
            f"https://duckduckgo.com/i.js?q={encoded_q}&vqd={urllib.parse.quote(vqd)}"
            "&o=json&p=1&s=0&u=bing&f=,,,&l=us-en"
        )
        req2 = urllib.request.Request(api_url, headers={"User-Agent": ua, "Referer": "https://duckduckgo.com/"})
        with urllib.request.urlopen(req2, timeout=8) as r2:
            data = json.loads(r2.read().decode("utf-8"))
        results = data.get("results", [])[:8]
        images = [{"url": item.get("image"), "thumb": item.get("thumbnail"), "title": item.get("title", "")} for item in results if item.get("image")]
        return {"images": images}
    except Exception:
        return {"images": []}


@router.post("/barcode/fetch-image")
def fetch_image(payload: dict):
    """Download an external image URL and save it locally. Returns the /static/… path."""
    url = payload.get("url", "")
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "homelab-inventory/1.8"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        try:
            from PIL import Image as _Img, ImageOps as _IOps
            import io as _io
            img = _Img.open(_io.BytesIO(data))
            img = _IOps.exif_transpose(img)
            img.thumbnail((1200, 1200), _Img.LANCZOS)
            out = _io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=80, optimize=True)
            data = out.getvalue()
        except Exception:
            pass
        filename = f"web_{uuid.uuid4()}.jpg"
        dest = os.path.join(UPLOAD_DIR, filename)
        with open(dest, "wb") as f:
            f.write(data)
        return {"path": f"/static/uploads/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
