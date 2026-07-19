import html
import json
import os
import re
import secrets
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

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
    _normalize_upc,
    cache_ammo_capture,
    calc_muzzle_energy_ftlb,
    missing_ammo_fields,
    normalize_caliber,
    upsert_upc_cache,
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


def _pairs_to_specs(pairs, label_map: dict) -> dict:
    """Core label->field mapping, shared by anything that reduces down to a list of
    (label, value) string pairs — a <table>'s rows, a <ul>'s "<strong>Label:</strong>
    Value" list items, whatever a given site uses for its spec block.
    """
    out: dict = {}
    for label, value in pairs:
        label = label.rstrip(':').lower()
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


def _rows_to_specs(rows, label_map: dict) -> dict:
    pairs = []
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        pairs.append((cells[0].get_text(strip=True), cells[1].get_text(strip=True)))
    return _pairs_to_specs(pairs, label_map)


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


# ── Academy Sports + Outdoors ────────────────────────────────────────────────────
# Server-rendered with a JSON-LD Product block (name/brand/price) plus a plain
# "Specifications" <ul> (no id/class hook — found by heading text). No MPN or
# ballistics data (velocity/energy/BC) anywhere on the page; UPC is only present
# inside a large inline JSON blob used for search/analytics, not in visible HTML.
_ACADEMY_SPEC_LABEL_MAP = {
    'grain weight': 'weight_gr',
    'number of rounds': 'rounds_per_box',
    'caliber': 'caliber',
    'bullet type': 'bullet_type',
    'primer type': 'primer_type',
    'muzzle velocity': 'factory_velocity_fps',
    'muzzle energy': 'muzzle_energy_ftlb',
    'case type': 'case_type',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
}


def _extract_academy_specs(soup: BeautifulSoup) -> dict:
    heading = None
    for h4 in soup.find_all('h4'):
        if h4.get_text(strip=True).lower() == 'specifications':
            heading = h4
            break
    if not heading:
        return {}
    container = heading.find_next_sibling('div')
    if not container:
        return {}
    pairs = []
    for li in container.find_all('li'):
        text = li.get_text(strip=True)
        if ':' not in text:
            continue
        label, _, value = text.partition(':')
        pairs.append((label.strip(), value.strip()))
    return _pairs_to_specs(pairs, _ACADEMY_SPEC_LABEL_MAP)


def parse_academy_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')
    product = _extract_jsonld_product(soup)
    name = html.unescape(product.get('name') or '')
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    brand_obj = product.get('brand')
    raw_brand = (brand_obj.get('name') if isinstance(brand_obj, dict) else '') or ''

    price = None
    offers = product.get('offers')
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict) and offers.get('price'):
        try:
            price = float(offers['price'])
        except (TypeError, ValueError):
            pass

    specs = _extract_academy_specs(soup)
    tier = 'full_specs' if specs else 'title_only'

    upc = None
    m = re.search(r'"UPCcode"\s*:\s*\[\s*"(\d+)"', html_text)
    if m:
        upc = m.group(1)

    caliber = normalize_caliber(specs.get('caliber')) or _parse_caliber(name)
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
        'mpn': None,  # Academy only exposes its own internal part number, not a real MPN
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
        'source': 'academy_page',
    }


# ── Palmetto State Armory ─────────────────────────────────────────────────────────
# Magento. Two data sources: the standard #product-attribute-specs-table (SKU/Brand/
# MPN/UPC/Bullet Type) plus a separate ".product.attribute.overview" <ul> with
# "<strong>Label:</strong> Value" items (Caliber/Round Count/Bullet Type/Grain Weight).
_PSA_SPECS_LABEL_MAP = {
    'sku': 'sku',
    'brand': 'brand_raw',
    'mpn': 'mpn',
    'upc': 'upc',
    'bullet type': 'bullet_type',
}
_PSA_OVERVIEW_LABEL_MAP = {
    'caliber': 'caliber',
    'ammo round count': 'rounds_per_box',
    'round count': 'rounds_per_box',
    'ammo bullet type 1': 'bullet_type',
    'bullet type': 'bullet_type',
    'ammo grain weight': 'weight_gr',
    'grain weight': 'weight_gr',
    'ammo bullet weight': 'weight_gr',
    'ammo muzzle velocity': 'factory_velocity_fps',
    'muzzle velocity': 'factory_velocity_fps',
    'ammo muzzle energy': 'muzzle_energy_ftlb',
    'muzzle energy': 'muzzle_energy_ftlb',
    'ammo casing material': 'case_type',
    'casing material': 'case_type',
    'ammo primer type': 'primer_type',
    'primer type': 'primer_type',
    'ammo reloadable': 'reloadable',
    'reloadable': 'reloadable',
    'ammo lead free': 'lead_free',
    'lead free': 'lead_free',
}


def _extract_psa_overview(soup: BeautifulSoup) -> dict:
    container = soup.select_one('.product.attribute.overview')
    if not container:
        return {}
    pairs = []
    for li in container.find_all('li'):
        strong = li.find('strong')
        if not strong:
            continue
        label = strong.get_text(strip=True)
        value = li.get_text(strip=True)[len(label):].strip()
        pairs.append((label, value))
    return _pairs_to_specs(pairs, _PSA_OVERVIEW_LABEL_MAP)


def parse_palmettostatearmory_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')

    name_tag = soup.select_one('.page-title-wrapper [itemprop="name"]') or soup.find(attrs={'itemprop': 'name'})
    name = html.unescape(name_tag.get_text(strip=True)) if name_tag else ''
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    specs_table = soup.find('table', id='product-attribute-specs-table')
    specs = _rows_to_specs(specs_table.find_all('tr'), _PSA_SPECS_LABEL_MAP) if specs_table else {}
    overview = _extract_psa_overview(soup)
    tier = 'full_specs' if (specs or overview) else 'title_only'

    raw_brand = specs.get('brand_raw', '')
    upc = re.sub(r'\D', '', str(specs.get('upc') or '')) or None
    mpn = specs.get('mpn')

    caliber = normalize_caliber(overview.get('caliber')) or _parse_caliber(name)
    brand = _parse_brand(raw_brand, name) or raw_brand or None
    weight_gr = overview.get('weight_gr') or _parse_weight(name)
    rounds_per_box = overview.get('rounds_per_box')
    if rounds_per_box is None:
        rounds_per_box = _extra_rounds(name) or _parse_rounds(name)
    product_line = _parse_product_line(name)
    bullet_type = overview.get('bullet_type') or specs.get('bullet_type') or _parse_bullet_type(name) or product_line
    primer_type = overview.get('primer_type') or _parse_primer_type(name)
    bc_g1 = overview.get('bc_g1')
    if bc_g1 is None:
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        bc_g1 = bc_data.get('bc_g1')

    price = None
    price_tag = soup.find('meta', attrs={'itemprop': 'price'})
    if price_tag and price_tag.get('content'):
        try:
            price = float(price_tag['content'])
        except ValueError:
            pass

    image_url = None
    img_link = soup.find('link', attrs={'itemprop': 'image'})
    if img_link and img_link.get('href'):
        image_url = img_link['href']
    if not image_url:
        img_tag = soup.select_one('.gallery-placeholder__image')
        if img_tag and img_tag.get('src'):
            image_url = img_tag['src']
    if not image_url:
        image_url = _extract_og_image(soup)

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
        'mpn': mpn,
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': overview.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': overview.get('muzzle_energy_ftlb'),
        'lead_free': overview.get('lead_free'),
        'case_type': overview.get('case_type'),
        'reloadable': overview.get('reloadable'),
        'image_url': image_url,
        'tier': tier,
        'source': 'palmettostatearmory_page',
    }


# ── LuckyGunner ────────────────────────────────────────────────────────────────────
# Also Magento — same #product-attribute-specs-table convention as Palmetto State
# Armory, but a richer single table (no separate overview list needed) plus a full
# JSON-LD Product block (name/brand/price/image/mpn), MidwayUSA-style.
_LUCKYGUNNER_SPEC_LABEL_MAP = {
    'bullet weight': 'weight_gr',
    'bullet type': 'bullet_type',
    'ammo casing': 'case_type',
    'quantity': 'rounds_per_box',
    'ammo caliber': 'caliber',
    'manufacturer sku': 'mpn',
    'primer type': 'primer_type',
    'muzzle velocity (fps)': 'factory_velocity_fps',
    'muzzle energy (ft lbs)': 'muzzle_energy_ftlb',
    'upc barcode': 'upc',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
    'lead-free': 'lead_free',
}


def parse_luckygunner_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')
    product = _extract_jsonld_product(soup)
    name = html.unescape(product.get('name') or '')
    if not name:
        h1 = soup.find('h1', class_='product-name') or soup.find('h1')
        name = h1.get_text(strip=True) if h1 else ''
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    brand_obj = product.get('brand')
    raw_brand = (brand_obj.get('name') if isinstance(brand_obj, dict) else '') or ''

    mpn = product.get('mpn')

    price = None
    offers = product.get('offers')
    if isinstance(offers, dict) and offers.get('price'):
        try:
            price = float(offers['price'])
        except (TypeError, ValueError):
            pass

    specs_table = soup.find('table', id='product-attribute-specs-table')
    specs = _rows_to_specs(specs_table.find_all('tr'), _LUCKYGUNNER_SPEC_LABEL_MAP) if specs_table else {}
    tier = 'full_specs' if specs else 'title_only'

    if not mpn:
        mpn = specs.get('mpn')

    upc = re.sub(r'\D', '', str(specs.get('upc') or '')) or None

    caliber_raw = (specs.get('caliber') or '').split('(')[0].strip()
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

    image_url = product.get('image') or _extract_og_image(soup)
    if isinstance(image_url, list):
        image_url = image_url[0] if image_url else None
    elif isinstance(image_url, dict):
        image_url = image_url.get('url')

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
        'mpn': mpn,
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': specs.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': specs.get('muzzle_energy_ftlb'),
        'lead_free': specs.get('lead_free'),
        'case_type': specs.get('case_type'),
        'reloadable': specs.get('reloadable'),
        'image_url': image_url,
        'tier': tier,
        'source': 'luckygunner_page',
    }


# ── Sportsman's Warehouse ───────────────────────────────────────────────────────
# SAP Hybris/Commerce Cloud. Clean "Specifications" table, but no UPC anywhere on
# the page (confirmed absent) — captures from here can never auto-cache directly,
# they'll always need a UPC added manually before Accept can cache them.
_SPORTSMAN_SPEC_LABEL_MAP = {
    'cartridge': 'caliber',
    'bullet type': 'bullet_type',
    'grains': 'weight_gr',
    'cartridge case': 'case_type',
    'muzzle velocity': 'factory_velocity_fps',
    'muzzle energy': 'muzzle_energy_ftlb',
    'pack quantity': 'rounds_per_box',
    'product line': 'product_line',
    'g1 ballistic coefficient': 'bc_g1',
    'primer type': 'primer_type',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
}


def parse_sportsmans_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')

    h1 = soup.find('h1', class_='product-name') or soup.find('h1')
    name = html.unescape(h1.get_text(strip=True)) if h1 else ''
    if not name and soup.title:
        name = soup.title.get_text(strip=True)

    brand_tag = soup.select_one('.product-details__brand a')
    raw_brand = brand_tag.get_text(strip=True) if brand_tag else ''

    mpn = None
    id_mpn_div = soup.find('div', class_='product-details__id-mpn')
    if id_mpn_div:
        text = id_mpn_div.get_text(' ', strip=True).replace('\xa0', ' ')
        m = re.search(r'MPN\s+(\S+)', text)
        if m:
            mpn = m.group(1)

    price = None
    price_tag = soup.select_one('.smw-product-price .price')
    if price_tag:
        m = re.search(r'[\d,]+\.\d{2}', price_tag.get_text())
        if m:
            price = float(m.group(0).replace(',', ''))
    if price is None:
        price = _extract_dom_price(soup)

    specs_host = soup.find('div', class_='product-classifications')
    specs_table = specs_host.find('table') if specs_host else None
    specs = _rows_to_specs(specs_table.find_all('tr'), _SPORTSMAN_SPEC_LABEL_MAP) if specs_table else {}
    tier = 'full_specs' if specs else 'title_only'

    caliber = normalize_caliber(specs.get('caliber')) or _parse_caliber(name)
    brand = _parse_brand(raw_brand, name) or raw_brand or None
    weight_gr = specs.get('weight_gr') or _parse_weight(name)
    rounds_per_box = specs.get('rounds_per_box')
    if rounds_per_box is None:
        rounds_per_box = _extra_rounds(name) or _parse_rounds(name)
    product_line = specs.get('product_line') or _parse_product_line(name)
    bullet_type = specs.get('bullet_type') or _parse_bullet_type(name) or product_line
    primer_type = specs.get('primer_type') or _parse_primer_type(name)
    bc_g1 = specs.get('bc_g1')
    if bc_g1 is None:
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        bc_g1 = bc_data.get('bc_g1')

    image_url = None
    img_tag = soup.find('img', class_='js-primary-image')
    if img_tag and img_tag.get('src'):
        src = img_tag['src']
        image_url = src if src.startswith('http') else urljoin('https://www.sportsmans.com', src)

    return {
        'title': name or None,
        'brand': brand,
        'caliber': caliber,
        'bullet_weight': weight_gr,
        'bullet_type': bullet_type,
        'product_line': product_line,
        'rounds_per_box': int(rounds_per_box) if rounds_per_box else None,
        'price': price,
        'upc': None,  # not exposed anywhere on Sportsman's Warehouse product pages
        'mpn': mpn,
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': specs.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': specs.get('muzzle_energy_ftlb'),
        'lead_free': specs.get('lead_free'),
        'case_type': specs.get('case_type'),
        'reloadable': specs.get('reloadable'),
        'image_url': image_url,
        'tier': tier,
        'source': 'sportsmans_page',
    }


# ── Bass Pro Shops / Cabela's ──────────────────────────────────────────────────────
# Same parent company, same platform, same product catalog — Next.js app with a
# __NEXT_DATA__ JSON blob carrying the full product record server-side. Far more
# reliable than scraping the obfuscated CSS-module-classed rendered HTML.
_BPC_ATTR_LABEL_MAP = {
    'cartridge or gauge': 'caliber',
    'grain': 'weight_gr',
    'velocity (fps)': 'factory_velocity_fps',
    'muzzle energy (ft-lb)': 'muzzle_energy_ftlb',
    'quantity': 'rounds_per_box',
    'bullet type': 'bullet_type',
    'primer type': 'primer_type',
    'case type': 'case_type',
    'reloadable': 'reloadable',
    'lead free': 'lead_free',
}


def parse_bassprocabelas_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')

    sku: dict = {}
    name = ''
    raw_brand = ''
    try:
        script = soup.find('script', id='__NEXT_DATA__')
        if script and script.string:
            data = json.loads(script.string)
            pd = data.get('props', {}).get('pageProps', {}).get('productDetails', {})
            sku_list = pd.get('skuDetails') or []
            if sku_list:
                sku = sku_list[0]
            name = pd.get('title') or sku.get('title') or ''
            raw_brand = pd.get('brand') or sku.get('brand') or ''
    except Exception:
        pass

    if not name and soup.title:
        name = soup.title.get_text(strip=True)
    name = html.unescape(name)

    def_attrs = sku.get('def_attrs') or {}
    if isinstance(def_attrs, str):
        try:
            def_attrs = json.loads(def_attrs)
        except Exception:
            def_attrs = {}
    specs = _pairs_to_specs(list(def_attrs.items()), _BPC_ATTR_LABEL_MAP)
    tier = 'full_specs' if specs else 'title_only'

    upc = re.sub(r'\D', '', str(sku.get('upc') or '')) or None
    mpn = sku.get('model_number')

    price = None
    for price_key in ('offerprice', 'listprice'):
        v = sku.get(price_key)
        if v:
            try:
                price = float(v)
                break
            except (TypeError, ValueError):
                pass

    caliber = normalize_caliber(specs.get('caliber')) or _parse_caliber(name)
    brand = _parse_brand(raw_brand, name) or raw_brand or None
    weight_gr = specs.get('weight_gr') or _parse_weight(name)
    rounds_per_box = specs.get('rounds_per_box')
    if rounds_per_box is None:
        rounds_per_box = _extra_rounds(name) or _parse_rounds(name)
    product_line = _parse_product_line(name)
    bullet_type = sku.get('bullet_type') or specs.get('bullet_type') or _parse_bullet_type(name) or product_line
    primer_type = specs.get('primer_type') or _parse_primer_type(name)
    bc_g1 = specs.get('bc_g1')
    if bc_g1 is None:
        bc_data = _lookup_bc(brand or '', product_line, weight_gr, caliber)
        bc_g1 = bc_data.get('bc_g1')

    image_url = sku.get('fullimage') or _extract_og_image(soup)

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
        'mpn': mpn,
        'primer_type': primer_type,
        'primer_model': _parse_primer_model(name),
        'bc_g1': bc_g1,
        'factory_velocity_fps': specs.get('factory_velocity_fps'),
        'muzzle_energy_ftlb': specs.get('muzzle_energy_ftlb'),
        'lead_free': specs.get('lead_free'),
        'case_type': specs.get('case_type'),
        'reloadable': specs.get('reloadable'),
        'image_url': image_url,
        'tier': tier,
        'source': 'bassprocabelas_page',
    }


def parse_product_html(html_text: str, source_url: Optional[str] = None) -> dict:
    """Dispatches to the right site-specific parser based on the captured page's URL."""
    host = urlparse(source_url).netloc.lower() if source_url else ''
    if 'targetsportsusa.com' in host:
        result = parse_targetsportsusa_html(html_text)
    elif 'academy.com' in host:
        result = parse_academy_html(html_text)
    elif 'palmettostatearmory.com' in host:
        result = parse_palmettostatearmory_html(html_text)
    elif 'luckygunner.com' in host:
        result = parse_luckygunner_html(html_text)
    elif 'sportsmans.com' in host:
        result = parse_sportsmans_html(html_text)
    elif 'basspro.com' in host or 'cabelas.com' in host:
        result = parse_bassprocabelas_html(html_text)
    else:
        result = parse_midway_html(html_text)

    # Fallback for sites that publish velocity but not muzzle energy (e.g. Bass Pro/
    # Cabela's) — one choke point for all parsers instead of duplicating in each.
    if result.get('muzzle_energy_ftlb') is None:
        result['muzzle_energy_ftlb'] = calc_muzzle_energy_ftlb(
            result.get('bullet_weight'), result.get('factory_velocity_fps')
        )
    return result


# ── Google search results (single-field capture, not a full product) ────────────────
# Same bookmarklet, different behavior when it's tapped on a google.* page instead of
# a retailer's: Google's AI Overview/featured snippet often answers a "<mpn> g1 bc"
# search directly, so this saves a click-through to a retailer site for just that one
# stubborn field. The target UPC travels in the URL fragment (#upc=...) that the
# Search UPC / Search Manufacturer # links set — Google ignores URL fragments
# entirely (never sent to its server, never affects the search), so this rides along
# for free without polluting the actual search query.
_GOOGLE_FIELD_PATTERNS = {
    'bc_g1': re.compile(
        r'(?:g1\s*bc|ballistic coefficient\s*\(?g1\)?|bc\s*\(g1\)|g1\s*ballistic coefficient)'
        r'[^0-9]{0,30}(0?\.\d{2,4})',
        re.IGNORECASE,
    ),
}
_GOOGLE_FIELD_BOUNDS = {
    'bc_g1': (0.05, 1.5),  # real small-arms G1 BCs all fall well within this range
}


def parse_google_search_html(html_text: str, source_url: Optional[str]) -> Optional[dict]:
    fragment = urlparse(source_url).fragment if source_url else ''
    m = re.search(r'upc=(\d+)', fragment)
    if not m:
        return None
    upc = m.group(1)

    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text(' ', strip=True)
    for field, pattern in _GOOGLE_FIELD_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        lo, hi = _GOOGLE_FIELD_BOUNDS[field]
        if not (lo < value < hi):
            continue
        return {'upc': upc, 'field': field, 'value': value}
    return None


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


@router.options("/capture-field")
async def capture_field_preflight():
    return Response(status_code=204, headers=_CORS_HEADERS)


@router.post("/capture-field")
async def capture_field(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Import-Token", "")
    if not token or token != _get_or_create_import_token(db):
        return JSONResponse(status_code=403, content={"detail": "Invalid import token"}, headers=_CORS_HEADERS)

    body = await request.json()
    html_text = body.get("html") or ""
    source_url = body.get("url") or ""
    if not html_text:
        return JSONResponse(status_code=400, content={"detail": "No HTML provided"}, headers=_CORS_HEADERS)
    if len(html_text) > 4_000_000:
        return JSONResponse(status_code=400, content={"detail": "Page too large"}, headers=_CORS_HEADERS)

    found = parse_google_search_html(html_text, source_url)
    if not found:
        return JSONResponse(
            status_code=404,
            content={"detail": "Couldn't find a usable answer on this page — try a different search"},
            headers=_CORS_HEADERS,
        )
    upc, field, value = found["upc"], found["field"], found["value"]

    # Same UPC still sitting incomplete in the Review queue — fill in the field there,
    # and promote straight to the cache (deleting the queue entry) if that was the last
    # thing missing, same "delete-and-cache" pattern as a fresh complete site capture.
    entry = db.query(_models.ScannerEntry).filter(
        _models.ScannerEntry.category == "ammo", _models.ScannerEntry.upc == upc,
    ).first()
    if entry:
        data = {}
        if entry.data_json:
            try:
                data = json.loads(entry.data_json)
            except Exception:
                pass
        data[field] = value
        if not missing_ammo_fields(entry.brand, entry.caliber, data):
            cache_ammo_capture(db, entry.upc, entry.title, entry.brand, entry.caliber, entry.image_path_1, data)
            db.delete(entry)
            db.commit()
            return JSONResponse(
                content={"ok": True, "complete": True, "destination": "cache", "field": field, "value": value},
                headers=_CORS_HEADERS,
            )
        entry.data_json = json.dumps(data)
        db.commit()
        return JSONResponse(
            content={"ok": True, "complete": False, "destination": "queue", "field": field, "value": value},
            headers=_CORS_HEADERS,
        )

    # No queue entry (already cached, or this is the Add Ammo form's scan-in-progress
    # case) — update the cache row directly if one exists for this UPC.
    cache_entry = db.query(_models.UpcCache).filter(_models.UpcCache.upc == _normalize_upc(upc)).first()
    if cache_entry:
        upsert_upc_cache(db, upc, prefer_existing=True, source_tier='site', **{field: value})
        return JSONResponse(
            content={"ok": True, "complete": True, "destination": "cache", "field": field, "value": value},
            headers=_CORS_HEADERS,
        )

    return JSONResponse(
        status_code=404,
        content={"detail": "No matching review entry or cache row for this UPC — capture the product first"},
        headers=_CORS_HEADERS,
    )


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
    title = result.get("title")
    brand = result.get("brand")
    caliber = result.get("caliber")

    # UPC already sitting in the review queue (e.g. a repeat tap of the bookmarklet on
    # the same product, or an earlier incomplete capture) — reuse/replace it instead of
    # piling up duplicates.
    existing_entry = db.query(_models.ScannerEntry).filter(
        _models.ScannerEntry.category == "ammo", _models.ScannerEntry.upc == upc,
    ).first() if upc else None

    # A UPC that's already complete in the cache (e.g. BC G1 was filled in earlier via a
    # Google-answer capture, or a richer site was captured first) must be recognized as
    # complete now even if *this particular* page alone doesn't carry every field —
    # otherwise re-capturing a site that structurally never has one of the fields (e.g.
    # MidwayUSA never has BC G1) re-queues an already-solved UPC as "incomplete" forever.
    existing_cache = db.query(_models.UpcCache).filter(
        _models.UpcCache.upc == upc,
    ).first() if upc else None
    check_data = dict(data)
    if existing_cache:
        for field in ("bullet_weight", "bc_g1", "factory_velocity_fps", "muzzle_energy_ftlb"):
            if check_data.get(field) is None:
                cache_field = "weight_gr" if field == "bullet_weight" else field
                cache_val = getattr(existing_cache, cache_field, None)
                if cache_val is not None:
                    check_data[field] = cache_val
    effective_brand = brand or (existing_cache.brand if existing_cache else None)
    effective_caliber = caliber or (existing_cache.caliber if existing_cache else None)

    # A capture this good doesn't need a human to Accept it — seed the cache directly
    # (the whole point of this feature, see project_midwayusa_import_architecture memory)
    # and clean up any stale incomplete queue entry for the same UPC now that we have a
    # complete one. Requires a UPC since UpcCache is keyed by it.
    can_cache_directly = bool(upc) and not missing_ammo_fields(effective_brand, effective_caliber, check_data)

    if can_cache_directly:
        if existing_entry:
            db.delete(existing_entry)
            db.commit()
        cache_ammo_capture(db, upc, title, brand, caliber, image_path, data)
        return JSONResponse(
            content={
                "ok": True, "id": None, "title": title, "tier": result.get("tier"),
                "updated": existing_entry is not None, "complete": True, "destination": "cache",
            },
            headers=_CORS_HEADERS,
        )

    if existing_entry:
        existing_entry.title = title
        existing_entry.brand = brand
        existing_entry.caliber = caliber
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
            title=title,
            brand=brand,
            caliber=caliber,
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
        content={
            "ok": True, "id": entry.id, "title": entry.title, "tier": result.get("tier"),
            "updated": updated, "complete": False, "destination": "queue",
        },
        headers=_CORS_HEADERS,
    )
