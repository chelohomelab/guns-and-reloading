import html
import json
import os
import re
import secrets
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

import database as _models
from config import UPLOAD_DIR
from dependencies import get_db
from routers.barcode import (
    _lookup_bc,
    _parse_bullet_type,
    _parse_brand,
    _parse_caliber,
    _parse_primer_model,
    _parse_primer_type,
    _parse_product_line,
    _parse_rounds,
    _parse_weight,
    normalize_caliber,
)

router = APIRouter(prefix="/import", tags=["import"])

_TOKEN_SETTING_KEY = "import_token"


def _require_admin(request: Request):
    if not getattr(request.state, "user", None) or not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")


def _get_or_create_import_token(db: Session) -> str:
    row = db.query(_models.Setting).filter(_models.Setting.key == _TOKEN_SETTING_KEY).first()
    if row:
        return row.value
    token = secrets.token_urlsafe(24)
    db.add(_models.Setting(key=_TOKEN_SETTING_KEY, value=token))
    db.commit()
    return token


def _extract_og_image(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find('meta', attrs={'property': 'og:image'})
    return tag['content'] if tag and tag.get('content') else None


def _download_product_image(url: Optional[str]) -> Optional[str]:
    """The bookmarklet sends HTML text only (no file upload), so the product photo
    has to be fetched server-side from its URL — same download+compress pattern as
    the UPC image cache in barcode.py.
    """
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "homelab-inventory/1.14"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
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
        filename = f"import_{uuid.uuid4()}.jpg"
        with open(os.path.join(UPLOAD_DIR, filename), 'wb') as f:
            f.write(data)
        return f"/static/uploads/{filename}"
    except Exception:
        return None


def _extract_dom_price(soup: BeautifulSoup) -> Optional[float]:
    """Fallback for when JSON-LD is unavailable (only present on pre-render saves;
    fully-rendered 'Single File' saves drop the JSON-LD script entirely).
    """
    el = soup.find(class_='sticky-product-price')
    if el:
        m = re.search(r'[\d,]+\.\d{2}', el.get_text())
        if m:
            return float(m.group(0).replace(',', ''))
    return None


def _extra_rounds(text: str) -> Optional[int]:
    """MidwayUSA-style 'Box of 20' / 'Case of 200' phrasing the generic parser doesn't cover."""
    m = re.search(r'\b(?:box|case)\s+of\s+(\d+)\b', text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# Maps a lowercased, colon-stripped MidwayUSA spec-table label to our field name.
_SPEC_LABEL_MAP = {
    'cartridge': 'caliber',
    'grain weight': 'weight_gr',
    'quantity': 'rounds_per_box',
    'bullet style': 'bullet_type',
    'bullet brand and model': 'product_line',
    'primer': 'primer_type',
    'g1 ballistic coefficient': 'bc_g1',
    'muzzle velocity': 'factory_velocity_fps',
    'muzzle energy': 'muzzle_energy_ftlb',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
    'case type': 'case_type',
}
_NUMERIC_SPEC_KEYS = {'weight_gr', 'rounds_per_box', 'bc_g1', 'factory_velocity_fps', 'muzzle_energy_ftlb'}
_YES_NO_SPEC_KEYS = {'reloadable', 'lead_free'}


def _rows_to_specs(rows, label_map: dict) -> dict:
    out: dict = {}
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).rstrip(':').lower()
        value = cells[1].get_text(strip=True)
        key = label_map.get(label)
        if not key or not value:
            continue
        if key in _NUMERIC_SPEC_KEYS:
            m = re.search(r'[\d.]+', value)
            if m:
                out[key] = float(m.group(0))
        elif key in _YES_NO_SPEC_KEYS:
            vl = value.strip().lower()
            if vl in ('yes', 'true'):
                out[key] = True
            elif vl in ('no', 'false'):
                out[key] = False
        else:
            out[key] = value
    return out


def _extract_specs_table(soup: BeautifulSoup) -> dict:
    """Parse MidwayUSA's 'Specifications' key/value table.

    Only present when the page was saved after its React app finished rendering —
    a save taken too early (or Chrome's "HTML only" before full load) captures just
    the pre-render skeleton and this table won't exist. Callers must tolerate {}.
    """
    host = soup.find(id='specifications-content') or soup.find(id='specifications')
    table = host.find('table') if host else soup.find('table')
    if table is None:
        return {}
    return _rows_to_specs(table.find_all('tr'), _SPEC_LABEL_MAP)


# Target Sports USA's product page has a key/value table in its details tab — but at
# least two live template variants exist across their catalog: a richer one with an
# explicit "Field | Details" header row, and a sparser, header-less one with slightly
# different label wording. Both are server-rendered (unlike MidwayUSA, no React
# hydration wait needed). Aliases below cover label spelling from both variants.
_TSUSA_SPEC_LABEL_MAP = {
    'upc': 'upc',
    'mpn': 'mpn',
    'caliber': 'caliber',
    'grain weight': 'weight_gr',
    'grain': 'weight_gr',
    'quantity per package': 'rounds_per_box',
    'ammo type': 'bullet_type',
    'bullet type': 'bullet_type',
    'primer type': 'primer_type',
    'primer': 'primer_type',
    'ballistic coefficient (g1)': 'bc_g1',
    'muzzle velocity': 'factory_velocity_fps',
    'muzzle energy': 'muzzle_energy_ftlb',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
    'case type': 'case_type',
    'casing': 'case_type',
}


def _is_field_details_header(row) -> bool:
    cells = [c.get_text(strip=True).lower() for c in row.find_all(['th', 'td'])]
    return 'field' in cells and 'details' in cells


def _extract_tsusa_specs_table(soup: BeautifulSoup) -> dict:
    # The spec table always lives in the details tab — scoping here avoids picking up
    # an unrelated table elsewhere on the page (e.g. a "similar products" comparison).
    scope = soup.find(id='tab-details') or soup
    specs: dict = {}
    for table in scope.find_all('table'):
        if table.get('class'):
            # "Similar/recommended products" widgets (e.g. class="tsrec-specs") use the
            # exact same field labels (Grain, Muzzle Velocity...) but describe a DIFFERENT
            # product entirely. The real spec table is always unclassed (either
            # <table border="1">  or a bare <table>), so skip anything with a class.
            continue
        rows = table.find_all('tr')
        if not rows:
            continue
        data_rows = rows[1:] if _is_field_details_header(rows[0]) else rows
        table_specs = _rows_to_specs(data_rows, _TSUSA_SPEC_LABEL_MAP)
        # Require at least 2 recognized fields before trusting a table as "the" spec
        # table — guards against an unrelated table coincidentally having one matching
        # label (e.g. a stray "Caliber" column in a recommendation grid).
        if len(table_specs) >= 2:
            for k, v in table_specs.items():
                specs.setdefault(k, v)
    return specs


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        try:
            data = json.loads(tag.string or '')
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict):
                yield item


def _extract_jsonld_product(soup: BeautifulSoup) -> dict:
    for item in _iter_jsonld(soup):
        if item.get('@type') == 'Product':
            return item
    return {}


def _extract_breadcrumb_caliber(soup: BeautifulSoup) -> Optional[str]:
    for item in _iter_jsonld(soup):
        if item.get('@type') == 'BreadcrumbList':
            crumbs = item.get('itemListElement') or []
            if len(crumbs) >= 3:
                name = ((crumbs[-2].get('item') or {}).get('name') or '').strip()
                return name or None
    return None


def parse_midway_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')
    product = _extract_jsonld_product(soup)
    name = html.unescape(product.get('name') or '')
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    brand_obj = product.get('brand')
    raw_brand = (brand_obj.get('name') if isinstance(brand_obj, dict) else '') or ''

    upc = re.sub(r'\D', '', product.get('mpn') or '') or None

    price = None
    offers = product.get('offers')
    if isinstance(offers, dict) and offers.get('price'):
        try:
            price = float(offers['price'])
        except (TypeError, ValueError):
            pass
    if price is None:
        price = _extract_dom_price(soup)

    specs = _extract_specs_table(soup)
    tier = 'full_specs' if specs else 'title_only'

    caliber = (
        normalize_caliber(specs.get('caliber'))
        or normalize_caliber(_extract_breadcrumb_caliber(soup))
        or _parse_caliber(name)
    )
    brand = _parse_brand(raw_brand, name) or raw_brand or None
    weight_gr = specs.get('weight_gr') or _parse_weight(name)
    rounds_per_box = specs.get('rounds_per_box')
    if rounds_per_box is None:
        rounds_per_box = _extra_rounds(name) or _parse_rounds(name)
    product_line = specs.get('product_line') or _parse_product_line(name)
    # "Bullet Style" (e.g. "Polymer Tip") is the ideal source; some products only list
    # "Bullet Brand And Model" (e.g. "Sierra GameKing") — better than leaving it blank.
    bullet_type = specs.get('bullet_type') or _parse_bullet_type(name) or product_line
    primer_type = specs.get('primer_type') or _parse_primer_type(name)
    bc_g1 = specs.get('bc_g1')
    if bc_g1 is None:
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        bc_g1 = bc_data.get('bc_g1')

    return {
        'title': name or None,
        'brand': brand,
        'caliber': caliber,
        # Ammo entries key the bullet weight field as "bullet_weight" (see database.py's
        # Ammo model and the Review-tab edit form) — "weight_gr" is the reloading-component
        # naming convention used elsewhere in this codebase, not ammo.
        'bullet_weight': weight_gr,
        'bullet_type': bullet_type,
        'product_line': product_line,
        'rounds_per_box': int(rounds_per_box) if rounds_per_box else None,
        'price': price,
        'upc': upc,
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': specs.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': specs.get('muzzle_energy_ftlb'),
        'lead_free': specs.get('lead_free'),
        'case_type': specs.get('case_type'),
        'reloadable': specs.get('reloadable'),
        'image_url': _extract_og_image(soup),
        'tier': tier,
        'source': 'midway_page',
    }


def parse_targetsportsusa_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')

    name_tag = soup.find(attrs={'itemprop': 'name'})
    name = html.unescape(name_tag.get_text(strip=True)) if name_tag else ''
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    brand_tag = soup.find(attrs={'itemprop': 'Manufacturer'})
    raw_brand = brand_tag.get_text(strip=True) if brand_tag else ''

    specs = _extract_tsusa_specs_table(soup)
    tier = 'full_specs' if specs else 'title_only'

    upc = re.sub(r'\D', '', str(specs.get('upc') or '')) or None
    if not upc:
        # Fallback: "Product SKU # :TSPMC308B | MPN: PMC308B | UPC # :741569060288"
        numbers_el = soup.find(class_='product-numbers')
        if numbers_el:
            m = re.search(r'UPC\s*#?\s*:?\s*(\d{8,14})', numbers_el.get_text())
            if m:
                upc = m.group(1)

    # "308 Winchester / 7.62x51mm NATO" — keep the primary (SAAMI) name only.
    caliber_raw = (specs.get('caliber') or '').split('/')[0].strip()
    caliber = normalize_caliber(caliber_raw) or _parse_caliber(name)
    brand = _parse_brand(raw_brand, name) or raw_brand or None
    weight_gr = specs.get('weight_gr') or _parse_weight(name)
    rounds_per_box = specs.get('rounds_per_box')
    if rounds_per_box is None:
        rounds_per_box = _extra_rounds(name) or _parse_rounds(name)
    product_line = _parse_product_line(name)
    bullet_type = specs.get('bullet_type') or _parse_bullet_type(name) or product_line
    primer_type = specs.get('primer_type') or _parse_primer_type(name)
    bc_g1 = specs.get('bc_g1')
    if bc_g1 is None:
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        bc_g1 = bc_data.get('bc_g1')

    price = None
    price_tag = soup.find(attrs={'itemprop': 'price'})
    if price_tag:
        try:
            price = float(price_tag.get_text(strip=True))
        except ValueError:
            pass
    if price is None:
        price = _extract_dom_price(soup)

    # The product photo tag is present in the initial server-rendered HTML (unlike
    # og:image here, which this site injects via JS after load) so prefer it.
    image_url = None
    img_tag = soup.find('img', attrs={'itemprop': 'image'})
    if img_tag and img_tag.get('src'):
        image_url = img_tag['src']
    if not image_url:
        image_url = _extract_og_image(soup)

    # The header-less template's "Casing" row reads e.g. "Brass Casing" — trim the
    # redundant trailing word so it matches the other template's "Brass".
    case_type = specs.get('case_type')
    if case_type:
        case_type = re.sub(r'\s+casing\s*$', '', case_type, flags=re.IGNORECASE).strip() or case_type

    return {
        'title': name or None,
        'brand': brand,
        'caliber': caliber,
        'bullet_weight': weight_gr,
        'bullet_type': bullet_type,
        'product_line': product_line,
        'rounds_per_box': int(rounds_per_box) if rounds_per_box else None,
        'price': price,
        'upc': upc,
        'mpn': specs.get('mpn'),
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': specs.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': specs.get('muzzle_energy_ftlb'),
        'lead_free': specs.get('lead_free'),
        'case_type': case_type,
        'reloadable': specs.get('reloadable'),
        'image_url': image_url,
        'tier': tier,
        'source': 'targetsportsusa_page',
    }


def parse_product_html(html_text: str, source_url: Optional[str] = None) -> dict:
    """Dispatches to the right site-specific parser based on the captured page's URL."""
    host = urlparse(source_url).netloc.lower() if source_url else ''
    if 'targetsportsusa.com' in host:
        return parse_targetsportsusa_html(html_text)
    return parse_midway_html(html_text)


@router.get("/token")
def get_import_token(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    return {"token": _get_or_create_import_token(db)}


@router.post("/token/regenerate")
def regenerate_import_token(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    token = secrets.token_urlsafe(24)
    row = db.query(_models.Setting).filter(_models.Setting.key == _TOKEN_SETTING_KEY).first()
    if row:
        row.value = token
    else:
        db.add(_models.Setting(key=_TOKEN_SETTING_KEY, value=token))
    db.commit()
    return {"token": token}


_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Import-Token",
}


@router.options("/capture")
async def capture_preflight():
    # Manual CORS handling scoped to this one route only — the bookmarklet runs on
    # the retailer's site (a different origin) and authenticates via X-Import-Token
    # instead of cookies, so there's no session/credential exposure in opening this up.
    return Response(status_code=204, headers=_CORS_HEADERS)


@router.post("/capture")
async def capture_page(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Import-Token", "")
    if not token or token != _get_or_create_import_token(db):
        return JSONResponse(status_code=403, content={"detail": "Invalid import token"}, headers=_CORS_HEADERS)

    body = await request.json()
    html_text = body.get("html") or ""
    source_url = body.get("url") or None
    if not html_text:
        return JSONResponse(status_code=400, content={"detail": "No HTML provided"}, headers=_CORS_HEADERS)
    if len(html_text) > 8_000_000:
        return JSONResponse(status_code=400, content={"detail": "Page too large"}, headers=_CORS_HEADERS)

    result = parse_product_html(html_text, source_url)
    extra_keys = (
        "product_line", "bullet_weight", "bullet_type", "rounds_per_box", "price",
        "primer_type", "primer_model", "bc_g1", "factory_velocity_fps",
        "muzzle_energy_ftlb", "lead_free", "case_type", "reloadable", "mpn",
    )
    data = {k: result[k] for k in extra_keys if result.get(k) is not None}
    image_path = _download_product_image(result.get("image_url"))
    upc = result.get("upc")

    # UPC already sitting in the review queue (e.g. a repeat tap of the bookmarklet on
    # the same product) — refresh that entry in place instead of piling up duplicates.
    existing_entry = db.query(_models.ScannerEntry).filter(
        _models.ScannerEntry.category == "ammo", _models.ScannerEntry.upc == upc,
    ).first() if upc else None

    if existing_entry:
        existing_entry.title = result.get("title")
        existing_entry.brand = result.get("brand")
        existing_entry.caliber = result.get("caliber")
        existing_entry.data_json = json.dumps(data) if data else None
        existing_entry.source_url = source_url
        if image_path:
            existing_entry.image_path_1 = image_path
        existing_entry.created_at = datetime.now(timezone.utc).date().isoformat()
        db.commit()
        db.refresh(existing_entry)
        entry = existing_entry
        updated = True
    else:
        entry = _models.ScannerEntry(
            category="ammo",
            upc=upc,
            title=result.get("title"),
            brand=result.get("brand"),
            caliber=result.get("caliber"),
            data_json=json.dumps(data) if data else None,
            image_path_1=image_path,
            created_at=datetime.now(timezone.utc).date().isoformat(),
            source_url=source_url,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        updated = False

    return JSONResponse(
        content={"ok": True, "id": entry.id, "title": entry.title, "tier": result.get("tier"), "updated": updated},
        headers=_CORS_HEADERS,
    )
