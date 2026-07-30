from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from paths import DATA_DIR

_db_dir = Path(DATA_DIR) / "data"
_db_dir.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{(_db_dir / 'reloading.db').as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Kept for backward-compat with existing DB rows; not exposed in new UI
class Furniture(Base):
    __tablename__ = "furniture"
    id = Column(Integer, primary_key=True, index=True)
    firearm_id = Column(Integer, ForeignKey("firearms.id"), nullable=True)
    barrel_id = Column(Integer, ForeignKey("barrels.id"), nullable=True)
    type = Column(String)
    material = Column(String)
    price_paid = Column(Float, default=0.0)
    brand = Column(String, nullable=True)
    image_path = Column(String, nullable=True)

class Scope(Base):
    __tablename__ = "scopes"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    model = Column(String)
    magnification = Column(String, nullable=True)
    units = Column(String, default="MOA")
    price_paid = Column(Float, default=0.0)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False)
    is_sold = Column(Boolean, default=False)
    price_sold = Column(Float, nullable=True)
    quantity = Column(Integer, default=1)

    firearms = relationship("Firearm", back_populates="scope")
    barrels = relationship("Barrel", back_populates="scope")

class Accessory(Base):
    __tablename__ = "accessories"
    id = Column(Integer, primary_key=True, index=True)
    firearm_id = Column(Integer, ForeignKey("firearms.id"), nullable=True)
    barrel_id = Column(Integer, ForeignKey("barrels.id"), nullable=True)
    name = Column(String)
    price_paid = Column(Float, default=0.0)

# Thompson Center receiver (Encore / Contender) — tracked separately from barrels
class TCReceiver(Base):
    __tablename__ = "tc_receivers"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String)           # "Encore" or "Contender"
    serial_number = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    price_paid = Column(Float, default=0.0)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    is_sold = Column(Boolean, default=False)
    price_sold = Column(Float, nullable=True)
    is_deleted = Column(Boolean, default=False)

class Firearm(Base):
    __tablename__ = "firearms"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    model = Column(String)
    frame_type = Column(String, default="Rifle")
    serial_number = Column(String, nullable=True)
    price_paid = Column(Float, default=0.0)
    image_path_1 = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    scope_id = Column(Integer, ForeignKey("scopes.id"), nullable=True)
    is_sold = Column(Boolean, default=False)
    price_sold = Column(Float, nullable=True)
    is_deleted = Column(Boolean, default=False)

    scope = relationship("Scope", back_populates="firearms")
    barrels = relationship("Barrel", back_populates="firearm", cascade="all, delete-orphan")
    accessories = relationship("Accessory", foreign_keys=[Accessory.firearm_id])

class Barrel(Base):
    __tablename__ = "barrels"
    id = Column(Integer, primary_key=True, index=True)
    # nullable so TC barrels can exist without a parent Firearm
    firearm_id = Column(Integer, ForeignKey("firearms.id"), nullable=True)
    name = Column(String, nullable=True)
    caliber = Column(String)
    twist_rate = Column(String, nullable=True)
    price_paid = Column(Float, default=0.0)
    scope_id = Column(Integer, ForeignKey("scopes.id"), nullable=True)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    # TC-specific fields (null for regular rifle barrels)
    tc_platform = Column(String, nullable=True)     # "Encore" or "Contender"
    barrel_length = Column(String, nullable=True)
    hardware_color = Column(String, nullable=True)
    is_threaded = Column(Boolean, default=False)
    has_muzzle_brake = Column(Boolean, default=False)
    is_sold = Column(Boolean, default=False)
    price_sold = Column(Float, nullable=True)
    is_deleted = Column(Boolean, default=False)

    firearm = relationship("Firearm", back_populates="barrels")
    scope = relationship("Scope", back_populates="barrels")
    accessories = relationship("Accessory", foreign_keys=[Accessory.barrel_id])
    shot_strings = relationship("ShotString", back_populates="barrel")

# --- RELOADING COMPONENT INVENTORY ---

class CasingInventory(Base):
    __tablename__ = "casing_inventory"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    caliber = Column(String)
    quantity = Column(Integer, default=0)
    times_fired = Column(Integer, default=0)   # 0 = new, 1 = once fired, etc.
    price_paid = Column(Float, default=0.0)
    notes = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    upc = Column(String, nullable=True)

class PowderInventory(Base):
    __tablename__ = "powder_inventory"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    name = Column(String)               # e.g., "H4350", "Varget"
    weight_lbs = Column(Float, default=0.0)  # pounds on hand
    price_paid = Column(Float, default=0.0)
    notes = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    upc = Column(String, nullable=True)
    is_muzzleloader = Column(Boolean, default=False)
    pellet_mode = Column(Boolean, default=False)

class PrimerInventory(Base):
    __tablename__ = "primer_inventory"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    model = Column(String, nullable=True)  # e.g., "210M", "BR2", "41"
    primer_type = Column(String)        # "Large Rifle", "Small Rifle Magnum", etc.
    quantity = Column(Integer, default=0)
    price_paid = Column(Float, default=0.0)   # per 1000
    notes = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    upc = Column(String, nullable=True)
    is_muzzleloader = Column(Boolean, default=False)

class BulletInventory(Base):
    __tablename__ = "bullet_inventory"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    product_line = Column(String, nullable=True)  # "ELD-M", "MatchKing", "Hybrid"
    caliber = Column(String)
    weight_gr = Column(Float)
    bullet_type = Column(String, nullable=True)   # "BTHP", "Hybrid", "FMJ"
    bc_g1 = Column(Float, nullable=True)
    # Manufacturer's own catalog/part number (e.g. Hornady "22601", Barnes "30271", Sierra
    # "#1234") — unlike upc (the retail box barcode), this identifies the bullet model itself
    # and, when both the owned bullet and the reload-data source have one, lets the reload data
    # matcher confirm the exact product instead of guessing off brand/weight/model text.
    sku = Column(String, nullable=True)
    quantity = Column(Integer, default=0)
    qty_sealed = Column(Integer, default=0)
    qty_open = Column(Integer, default=0)
    price_paid = Column(Float, default=0.0)       # per box/unit price
    notes = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    upc = Column(String, nullable=True)
    is_muzzleloader = Column(Boolean, default=False)
    datasheet_path = Column(String, nullable=True)

    load_data_sets = relationship("LoadData", back_populates="bullet", cascade="all, delete-orphan")
    ladder_tests = relationship("LadderTest", back_populates="bullet", cascade="all, delete-orphan")


class LoadData(Base):
    __tablename__ = "load_data"
    id = Column(Integer, primary_key=True, index=True)
    bullet_id = Column(Integer, ForeignKey("bullet_inventory.id"), nullable=False)
    source = Column(String, nullable=True)
    caliber = Column(String, nullable=True)
    coal = Column(Float, nullable=True)
    primer = Column(String, nullable=True)
    case_type = Column(String, nullable=True)
    case_capacity_gr = Column(Float, nullable=True)
    barrel_length = Column(String, nullable=True)
    barrel_twist = Column(String, nullable=True)
    barrel_desc = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    bullet = relationship("BulletInventory", back_populates="load_data_sets")
    entries = relationship("LoadDataEntry", back_populates="load_data", cascade="all, delete-orphan")


class LoadDataEntry(Base):
    __tablename__ = "load_data_entries"
    id = Column(Integer, primary_key=True, index=True)
    load_data_id = Column(Integer, ForeignKey("load_data.id"), nullable=False)
    powder_name = Column(String, nullable=False)
    charge_min = Column(Float, nullable=True)
    charge_max = Column(Float, nullable=True)
    velocity_min = Column(Integer, nullable=True)
    velocity_max = Column(Integer, nullable=True)
    load_density_min = Column(Float, nullable=True)
    load_density_max = Column(Float, nullable=True)
    is_max_load = Column(Boolean, default=False)
    is_most_accurate = Column(Boolean, default=False)

    load_data = relationship("LoadData", back_populates="entries")


class ReloadDataSource(Base):
    # One row per Hodgdon "Reloading Data Center" PDF upload (one caliber per PDF).
    # Standalone reference library, deliberately not FK'd to BulletInventory/PowderInventory —
    # this data covers loads for bullets/powders the user may never own, unlike LoadData above,
    # which is scoped to a specific owned bullet. See project memory on the multi-site importer's
    # BC-guessing bugs for why in-stock matching (done at query time in routers/reload_data.py)
    # is exact brand+name only, never a fuzzy/weight-only guess.
    __tablename__ = "reload_data_sources"
    id = Column(Integer, primary_key=True, index=True)
    manufacturer = Column(String, nullable=False, default="Hodgdon")  # Hodgdon/Nosler/Speer/Sierra/Barnes/Hornady
    caliber = Column(String, nullable=False, index=True)   # normalized via routers.barcode.normalize_caliber
    # Nosler/Speer files are scoped to one bullet weight (and Speer to one specific bullet model) —
    # part of the replace-on-reupload key so re-uploading one weight doesn't wipe out others for the
    # same caliber. Null for Hodgdon/Sierra/Barnes/Hornady, whose files/chapters span many weights.
    scope_bullet_weight_gr = Column(Float, nullable=True)
    scope_bullet_model = Column(String, nullable=True)
    twist = Column(String, nullable=True)
    barrel_length = Column(String, nullable=True)
    trim_length = Column(String, nullable=True)
    max_saami_oal = Column(String, nullable=True)  # Nosler "MAXIMUM SAAMI O.A.C.L." / Speer "Max Cart. OAL"
    max_case_length = Column(String, nullable=True)  # Speer's "Max Case Length"
    rcbs_shell_holder = Column(String, nullable=True)  # Speer's "RCBS Shell Holder"
    test_firearm = Column(String, nullable=True)  # Speer's "Test Firearm"
    data_as_of = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    source_file_path = Column(String, nullable=True)
    case_diagram_path = Column(String, nullable=True)  # cropped/extracted case-dimension diagram image
    uploaded_at = Column(String, nullable=True)
    # Flags a real discrepancy/anomaly in the manufacturer's own published data (as opposed to a
    # transcription-side concern) — e.g. a duplicate row the book itself prints twice with
    # different numbers. Surfaced prominently in the UI so it isn't missed, and exists so the user
    # has something to point to when following up with the manufacturer.
    data_note = Column(String, nullable=True)

    loads = relationship("ReloadDataLoad", back_populates="source", cascade="all, delete-orphan")


class ReloadDataLoad(Base):
    __tablename__ = "reload_data_loads"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("reload_data_sources.id"), nullable=False)
    bullet_weight_gr = Column(Float, nullable=True)
    bullet_brand = Column(String, nullable=True)
    bullet_model = Column(String, nullable=True)
    bullet_code = Column(String, nullable=True)  # Nosler's short model code, e.g. "AB", "CC", "RDF"
    bullet_style = Column(String, nullable=True)  # bullet profile, e.g. "HPBT", "Spitzer", "FB Tipped"
    bullet_dia = Column(String, nullable=True)
    bullet_bc = Column(Float, nullable=True)  # G1 ballistic coefficient
    bullet_bc_g7 = Column(Float, nullable=True)  # G7 ballistic coefficient (Hornady's long-range bullets only)
    bullet_sd = Column(Float, nullable=True)  # sectional density
    case_brand = Column(String, nullable=True)
    primer_display = Column(String, nullable=True)
    # Row-level overrides for Sierra, whose single caliber file can contain more than one
    # "Test Specifications" section (different case brass tested at a different twist, etc.) —
    # null for every other manufacturer, which falls back to the source-level column of the
    # same name (see _load_dict).
    twist = Column(String, nullable=True)
    barrel_length = Column(String, nullable=True)
    trim_length = Column(String, nullable=True)
    test_firearm = Column(String, nullable=True)
    powder_brand = Column(String, nullable=True)
    powder_name = Column(String, nullable=True)
    coal = Column(String, nullable=True)
    is_recommended = Column(Boolean, nullable=True)  # Nosler "*" / Lyman bold row = most accurate load tested
    is_max_load = Column(Boolean, nullable=True)  # Hornady's red highlight = maximum load, use with caution
    is_reduced_load = Column(Boolean, nullable=True)  # Lyman's "**" powder-name prefix = reduced load
    start_charge_gr = Column(Float, nullable=True)
    start_velocity_fps = Column(Integer, nullable=True)
    start_pressure = Column(Integer, nullable=True)
    start_pressure_unit = Column(String, nullable=True)
    start_density_pct = Column(Float, nullable=True)
    start_is_compressed = Column(Boolean, default=False)
    max_charge_gr = Column(Float, nullable=True)
    max_velocity_fps = Column(Integer, nullable=True)
    max_pressure = Column(Integer, nullable=True)
    max_pressure_unit = Column(String, nullable=True)
    max_density_pct = Column(Float, nullable=True)
    max_is_compressed = Column(Boolean, default=False)

    source = relationship("ReloadDataSource", back_populates="loads")


class LadderTest(Base):
    __tablename__ = "ladder_tests"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    caliber = Column(String, nullable=True)
    bullet_id = Column(Integer, ForeignKey("bullet_inventory.id"), nullable=False)
    powder_name = Column(String, nullable=False)
    primer = Column(String, nullable=True)
    case_type = Column(String, nullable=True)
    coal = Column(Float, nullable=True)
    date_started = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(String, nullable=True)
    charge_start = Column(Float, nullable=True)
    charge_end = Column(Float, nullable=True)
    charge_increment = Column(Float, nullable=True)
    barrel_id = Column(Integer, ForeignKey("barrels.id"), nullable=True)
    platform_id = Column(Integer, ForeignKey("test_platforms.id"), nullable=True)
    powder_inv_id = Column(Integer, ForeignKey("powder_inventory.id"), nullable=True)
    primer_inv_id = Column(Integer, ForeignKey("primer_inventory.id"), nullable=True)
    casing_inv_id = Column(Integer, ForeignKey("casing_inventory.id"), nullable=True)
    rounds_per_step = Column(Integer, nullable=True)

    bullet = relationship("BulletInventory", back_populates="ladder_tests")
    barrel = relationship("Barrel")
    platform = relationship("TestPlatform", back_populates="ladder_tests")
    steps = relationship("LadderTestStep", back_populates="ladder_test",
                          cascade="all, delete-orphan", order_by="LadderTestStep.charge_weight")


class TestPlatform(Base):
    __tablename__ = "test_platforms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    caliber = Column(String, nullable=True)
    barrel_length = Column(String, nullable=True)
    barrel_twist = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(String, nullable=True)

    ladder_tests = relationship("LadderTest", back_populates="platform")


class LadderTestStep(Base):
    __tablename__ = "ladder_test_steps"
    id = Column(Integer, primary_key=True, index=True)
    ladder_test_id = Column(Integer, ForeignKey("ladder_tests.id"), nullable=False)
    charge_weight = Column(Float, nullable=False)
    velocities = Column(String, nullable=True)
    rounds_fired = Column(Integer, nullable=True)
    avg_velocity = Column(Float, nullable=True)
    extreme_spread = Column(Float, nullable=True)
    standard_deviation = Column(Float, nullable=True)
    is_winner = Column(Boolean, default=False)
    date_shot = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    ladder_test = relationship("LadderTest", back_populates="steps")


# --- AMMUNITION & PERFORMANCE LOGS ---
class Ammo(Base):
    __tablename__ = "ammo"
    id = Column(Integer, primary_key=True, index=True)
    is_handload = Column(Boolean, default=False)
    brand = Column(String)
    caliber = Column(String, nullable=True)
    line_or_powder = Column(String)
    bullet_weight = Column(Float)
    bullet_type = Column(String)
    bullet_bc = Column(Float, nullable=True)
    charge_weight = Column(Float, nullable=True)
    coal = Column(Float, nullable=True)
    qty_sealed = Column(Integer, default=0)
    qty_open = Column(Integer, default=0)
    price_paid = Column(Float, default=0.0)
    rounds_per_box = Column(Integer, default=20)
    image_path = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    ammo_category = Column(String, nullable=True)
    shell_size = Column(String, nullable=True)
    shot_size = Column(String, nullable=True)
    upc = Column(String, nullable=True)
    factory_velocity_fps = Column(Float, nullable=True)
    muzzle_energy_ftlb = Column(Float, nullable=True)
    lead_free = Column(Boolean, nullable=True)
    case_type = Column(String, nullable=True)
    reloadable = Column(Boolean, nullable=True)

    shot_strings = relationship("ShotString", back_populates="ammo")
    purchase_log = relationship("AmmoPurchaseLog", back_populates="ammo", order_by="AmmoPurchaseLog.date")

class ShotString(Base):
    __tablename__ = "shot_strings"
    id = Column(Integer, primary_key=True, index=True)
    barrel_id = Column(Integer, ForeignKey("barrels.id"))
    ammo_id = Column(Integer, ForeignKey("ammo.id"))
    date_shot = Column(String)
    
    # Raw data from the chronograph
    velocities = Column(String, nullable=True) # e.g., "3010,2995,3005"
    rounds_fired = Column(Integer, nullable=True)
    
    # --- NEW: Automated Math Columns ---
    avg_velocity = Column(Float, nullable=True)
    extreme_spread = Column(Float, nullable=True)
    standard_deviation = Column(Float, nullable=True)
    
    # Group Tracking
    target_image_path = Column(String, nullable=True)
    group_size_inches = Column(Float, nullable=True)
    group_size_moa = Column(Float, nullable=True)

    # Raw shot geometry — persisted so a session's group math can be recomputed/reopened later,
    # not just archived as a flattened picture. Coordinates live in the ORIGINAL upload canvas's
    # own pixel space (image_width/image_height), never the possibly-thumbnailed stored image's
    # space (see dependencies.save_uploaded_file's 1200x1200 thumbnail) and never crop-relative.
    shots_json = Column(String, nullable=True)  # JSON [{"x":px,"y":py,"velocity":fps|null}, ...]
    poa_x = Column(Float, nullable=True)  # Point of Aim, same pixel space; null if not marked
    poa_y = Column(Float, nullable=True)
    pixels_per_inch = Column(Float, nullable=True)  # calibration scale locked at save time
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    distance_yards = Column(Float, nullable=True)

    # Computed geometry stats (mirrors avg_velocity/extreme_spread/standard_deviation above)
    group_width_inches = Column(Float, nullable=True)
    group_height_inches = Column(Float, nullable=True)
    group_size_mrad = Column(Float, nullable=True)
    elevation_offset_inches = Column(Float, nullable=True)  # + = group center HIGH of POA (dial DOWN)
    windage_offset_inches = Column(Float, nullable=True)  # + = group center RIGHT of POA (dial LEFT)
    elevation_offset_moa = Column(Float, nullable=True)
    windage_offset_moa = Column(Float, nullable=True)

    barrel = relationship("Barrel", back_populates="shot_strings")
    ammo = relationship("Ammo", back_populates="shot_strings")

class UpcCache(Base):
    __tablename__ = "upc_cache"
    upc          = Column(String, primary_key=True)
    title        = Column(String, nullable=True)
    product_type = Column(String, nullable=True)
    brand        = Column(String, nullable=True)
    product_line = Column(String, nullable=True)
    caliber      = Column(String, nullable=True)
    weight_gr    = Column(Float,  nullable=True)
    bullet_type  = Column(String, nullable=True)
    bc_g1        = Column(Float,  nullable=True)
    rounds_per_box = Column(Integer, nullable=True)
    primer_type  = Column(String, nullable=True)
    primer_model = Column(String, nullable=True)
    powder_name  = Column(String, nullable=True)
    mpn          = Column(String, nullable=True)
    image_path   = Column(String, nullable=True)
    ammo_category = Column(String, nullable=True)
    factory_velocity_fps = Column(Float, nullable=True)
    muzzle_energy_ftlb = Column(Float, nullable=True)
    lead_free    = Column(Boolean, nullable=True)
    case_type    = Column(String, nullable=True)
    reloadable   = Column(Boolean, nullable=True)
    updated_at   = Column(String, nullable=True)
    # Which kind of source last had "full write" rights on this row: 'site' (a
    # bookmarklet capture of an actual retailer page — structured, reliable) or 'api'
    # (the generic external UPC lookup — aggregated third-party data, prone to typos
    # and thin records). A 'site' write may freely overwrite a row that isn't already
    # 'site'-tier; once a row is 'site'-tier, further writes (from any source) only
    # fill gaps, never overwrite. See upsert_upc_cache() in routers/barcode.py.
    source_tier  = Column(String, nullable=True)


class LookupValue(Base):
    __tablename__ = "lookup_values"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)

class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(String, nullable=False)

    user = relationship("User", back_populates="sessions")

class UserPreference(Base):
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False, default="true")

    user = relationship("User", back_populates="preferences")

class Wishlist(Base):
    __tablename__ = "wishlist"
    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String, default="Other")   # Rifle, Handgun, Shotgun, TC System, TC Barrel, Optic, Other
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    caliber = Column(String, nullable=True)
    priority = Column(String, default="Medium")   # Low, Medium, High
    est_price = Column(Float, nullable=True)
    notes = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    url = Column(String, nullable=True)
    created_at = Column(String, nullable=True)

class AmmoPurchaseLog(Base):
    __tablename__ = "ammo_purchase_log"
    id = Column(Integer, primary_key=True, index=True)
    ammo_id = Column(Integer, ForeignKey("ammo.id"), nullable=False)
    date = Column(String, nullable=False)   # ISO date YYYY-MM-DD
    qty_sealed = Column(Integer, default=0)
    qty_open = Column(Integer, default=0)
    price_per_box = Column(Float, nullable=True)

    ammo = relationship("Ammo", back_populates="purchase_log")

class ScannerEntry(Base):
    __tablename__ = "scanner_entries"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, default="ammo")    # ammo, firearm, optic, component, tc_barrel
    upc = Column(String, nullable=True)
    title = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    caliber = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    image_path_1 = Column(String, nullable=True)
    image_path_2 = Column(String, nullable=True)
    image_path_3 = Column(String, nullable=True)
    data_json = Column(String, nullable=True)    # JSON for category-specific fields
    created_at = Column(String, nullable=True)
    is_reviewed = Column(Boolean, default=False)
    source_url = Column(String, nullable=True)    # retailer page this was imported from, if any

def init_db():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text, inspect as sa_inspect
    inspector = sa_inspect(engine)

    def _add_col(table, col, ddl):
        existing = [c['name'] for c in inspector.get_columns(table)]
        if col not in existing:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
                conn.commit()

    if 'ammo' in inspector.get_table_names():
        _add_col('ammo', 'caliber', 'caliber VARCHAR')
        _add_col('ammo', 'bullet_bc', 'bullet_bc FLOAT')
        _add_col('ammo', 'qty_sealed', 'qty_sealed INTEGER DEFAULT 0')
        _add_col('ammo', 'qty_open', 'qty_open INTEGER DEFAULT 0')
        _add_col('ammo', 'price_paid', 'price_paid FLOAT DEFAULT 0.0')
        _add_col('ammo', 'rounds_per_box', 'rounds_per_box INTEGER DEFAULT 20')
        _add_col('ammo', 'ammo_category', 'ammo_category VARCHAR')
        _add_col('ammo', 'shell_size', 'shell_size VARCHAR')
        _add_col('ammo', 'shot_size', 'shot_size VARCHAR')
        _add_col('ammo', 'upc', 'upc VARCHAR')
        _add_col('ammo', 'factory_velocity_fps', 'factory_velocity_fps FLOAT')
        _add_col('ammo', 'muzzle_energy_ftlb', 'muzzle_energy_ftlb FLOAT')
        _add_col('ammo', 'lead_free', 'lead_free BOOLEAN')
        _add_col('ammo', 'case_type', 'case_type VARCHAR')
        _add_col('ammo', 'reloadable', 'reloadable BOOLEAN')

    if 'upc_cache' in inspector.get_table_names():
        _add_col('upc_cache', 'ammo_category', 'ammo_category VARCHAR')
        _add_col('upc_cache', 'factory_velocity_fps', 'factory_velocity_fps FLOAT')
        _add_col('upc_cache', 'muzzle_energy_ftlb', 'muzzle_energy_ftlb FLOAT')
        _add_col('upc_cache', 'lead_free', 'lead_free BOOLEAN')
        _add_col('upc_cache', 'case_type', 'case_type VARCHAR')
        _add_col('upc_cache', 'reloadable', 'reloadable BOOLEAN')
        _add_col('upc_cache', 'mpn', 'mpn VARCHAR')
        _add_col('upc_cache', 'source_tier', 'source_tier VARCHAR')

    for tbl, col in [
        ('casing_inventory', 'image_path'),
        ('casing_inventory', 'image_path_2'),
        ('powder_inventory', 'image_path'),
        ('powder_inventory', 'image_path_2'),
        ('primer_inventory', 'model'),
        ('primer_inventory', 'image_path'),
        ('primer_inventory', 'image_path_2'),
        ('bullet_inventory', 'image_path'),
        ('bullet_inventory', 'image_path_2'),
        ('ammo', 'image_path_2'),
    ]:
        if tbl in inspector.get_table_names():
            _add_col(tbl, col, f'{col} VARCHAR')

    if 'firearms' in inspector.get_table_names():
        _add_col('firearms', 'image_path_2', 'image_path_2 VARCHAR')
        _add_col('firearms', 'serial_number', 'serial_number VARCHAR')

    if 'barrels' in inspector.get_table_names():
        _add_col('barrels', 'tc_platform',    'tc_platform VARCHAR')
        _add_col('barrels', 'barrel_length',  'barrel_length VARCHAR')
        _add_col('barrels', 'hardware_color', 'hardware_color VARCHAR')
        _add_col('barrels', 'is_threaded',    'is_threaded BOOLEAN DEFAULT FALSE')
        _add_col('barrels', 'has_muzzle_brake', 'has_muzzle_brake BOOLEAN DEFAULT FALSE')
        _add_col('barrels', 'image_path_2',   'image_path_2 VARCHAR')
        _add_col('barrels', 'is_sold',        'is_sold BOOLEAN DEFAULT FALSE')
        _add_col('barrels', 'price_sold',     'price_sold FLOAT')
        _add_col('barrels', 'is_deleted',     'is_deleted BOOLEAN DEFAULT FALSE')

    if 'bullet_inventory' in inspector.get_table_names():
        _add_col('bullet_inventory', 'qty_sealed', 'qty_sealed INTEGER DEFAULT 0')
        _add_col('bullet_inventory', 'qty_open', 'qty_open INTEGER DEFAULT 0')
        _add_col('bullet_inventory', 'upc', 'upc VARCHAR')
        _add_col('bullet_inventory', 'is_muzzleloader', 'is_muzzleloader BOOLEAN DEFAULT FALSE')
        _add_col('bullet_inventory', 'datasheet_path', 'datasheet_path VARCHAR')
        _add_col('bullet_inventory', 'sku', 'sku VARCHAR')

    for tbl in ('casing_inventory', 'powder_inventory', 'primer_inventory'):
        if tbl in inspector.get_table_names():
            _add_col(tbl, 'upc', 'upc VARCHAR')

    for tbl in ('powder_inventory', 'primer_inventory'):
        if tbl in inspector.get_table_names():
            _add_col(tbl, 'is_muzzleloader', 'is_muzzleloader BOOLEAN DEFAULT FALSE')

    if 'powder_inventory' in inspector.get_table_names():
        _add_col('powder_inventory', 'pellet_mode', 'pellet_mode BOOLEAN DEFAULT FALSE')

    if 'shot_strings' in inspector.get_table_names():
        _add_col('shot_strings', 'rounds_fired', 'rounds_fired INTEGER')
        # v1.17 Range Session overhaul (persisted shot geometry, POA/ATZ) — these were added to
        # the ShotString model but this migration list was never updated to match, so on any
        # database that already had a shot_strings table (i.e. anything but a brand new install,
        # where create_all() alone would've covered it), every query against this table started
        # failing with "no such column" the moment the v1.17 code shipped — Range Session data
        # wasn't actually lost, it just became unreadable until these columns exist.
        _add_col('shot_strings', 'shots_json', 'shots_json VARCHAR')
        _add_col('shot_strings', 'poa_x', 'poa_x FLOAT')
        _add_col('shot_strings', 'poa_y', 'poa_y FLOAT')
        _add_col('shot_strings', 'pixels_per_inch', 'pixels_per_inch FLOAT')
        _add_col('shot_strings', 'image_width', 'image_width INTEGER')
        _add_col('shot_strings', 'image_height', 'image_height INTEGER')
        _add_col('shot_strings', 'distance_yards', 'distance_yards FLOAT')
        _add_col('shot_strings', 'group_width_inches', 'group_width_inches FLOAT')
        _add_col('shot_strings', 'group_height_inches', 'group_height_inches FLOAT')
        _add_col('shot_strings', 'group_size_mrad', 'group_size_mrad FLOAT')
        _add_col('shot_strings', 'elevation_offset_inches', 'elevation_offset_inches FLOAT')
        _add_col('shot_strings', 'windage_offset_inches', 'windage_offset_inches FLOAT')
        _add_col('shot_strings', 'elevation_offset_moa', 'elevation_offset_moa FLOAT')
        _add_col('shot_strings', 'windage_offset_moa', 'windage_offset_moa FLOAT')

    if 'reload_data_sources' in inspector.get_table_names():
        # These predate the multi-manufacturer expansion (v1.14-v1.17) and were missing from
        # this auto-migration list on any DB whose reload_data_sources table was created before
        # that work landed — same bug class as the shot_strings gap above. A hand-patch covering
        # everything except data_note had been applied directly on prod as a stopgap; this
        # folds that fix back into the repo so it's no longer server-specific.
        _add_col('reload_data_sources', 'manufacturer',           "manufacturer VARCHAR NOT NULL DEFAULT 'Hodgdon'")
        _add_col('reload_data_sources', 'scope_bullet_weight_gr', 'scope_bullet_weight_gr FLOAT')
        _add_col('reload_data_sources', 'scope_bullet_model',     'scope_bullet_model VARCHAR')
        _add_col('reload_data_sources', 'max_saami_oal',          'max_saami_oal VARCHAR')
        _add_col('reload_data_sources', 'max_case_length',        'max_case_length VARCHAR')
        _add_col('reload_data_sources', 'rcbs_shell_holder',      'rcbs_shell_holder VARCHAR')
        _add_col('reload_data_sources', 'test_firearm',           'test_firearm VARCHAR')
        _add_col('reload_data_sources', 'case_diagram_path',      'case_diagram_path VARCHAR')
        _add_col('reload_data_sources', 'data_note',              'data_note VARCHAR')

    if 'reload_data_loads' in inspector.get_table_names():
        _add_col('reload_data_loads', 'bullet_code',     'bullet_code VARCHAR')
        _add_col('reload_data_loads', 'bullet_style',    'bullet_style VARCHAR')
        _add_col('reload_data_loads', 'bullet_bc',       'bullet_bc FLOAT')
        _add_col('reload_data_loads', 'bullet_bc_g7',    'bullet_bc_g7 FLOAT')
        _add_col('reload_data_loads', 'bullet_sd',       'bullet_sd FLOAT')
        _add_col('reload_data_loads', 'is_recommended',  'is_recommended BOOLEAN')
        _add_col('reload_data_loads', 'is_max_load',     'is_max_load BOOLEAN')
        _add_col('reload_data_loads', 'is_reduced_load', 'is_reduced_load BOOLEAN')
        _add_col('reload_data_loads', 'twist',           'twist VARCHAR')
        _add_col('reload_data_loads', 'barrel_length',   'barrel_length VARCHAR')
        _add_col('reload_data_loads', 'trim_length',     'trim_length VARCHAR')
        _add_col('reload_data_loads', 'test_firearm',    'test_firearm VARCHAR')

    if 'scopes' in inspector.get_table_names():
        _add_col('scopes', 'magnification', 'magnification VARCHAR')
        _add_col('scopes', 'image_path_2',  'image_path_2 VARCHAR')
        _add_col('scopes', 'quantity',      'quantity INTEGER DEFAULT 1')

    if 'tc_receivers' in inspector.get_table_names():
        _add_col('tc_receivers', 'notes',        'notes VARCHAR')
        _add_col('tc_receivers', 'image_path_2', 'image_path_2 VARCHAR')
        _add_col('tc_receivers', 'is_deleted',   'is_deleted BOOLEAN DEFAULT FALSE')

    if 'firearms' in inspector.get_table_names():
        _add_col('firearms', 'is_deleted', 'is_deleted BOOLEAN DEFAULT FALSE')

    if 'scopes' in inspector.get_table_names():
        _add_col('scopes', 'is_deleted', 'is_deleted BOOLEAN DEFAULT FALSE')
        _add_col('scopes', 'is_sold',    'is_sold BOOLEAN DEFAULT FALSE')
        _add_col('scopes', 'price_sold', 'price_sold FLOAT')

    if 'scanner_entries' in inspector.get_table_names():
        _add_col('scanner_entries', 'source_url', 'source_url VARCHAR')

    if 'ladder_tests' in inspector.get_table_names():
        _add_col('ladder_tests', 'charge_start',     'charge_start FLOAT')
        _add_col('ladder_tests', 'charge_end',       'charge_end FLOAT')
        _add_col('ladder_tests', 'charge_increment', 'charge_increment FLOAT')
        _add_col('ladder_tests', 'barrel_id',        'barrel_id INTEGER')
        _add_col('ladder_tests', 'platform_id',      'platform_id INTEGER')
        _add_col('ladder_tests', 'powder_inv_id',    'powder_inv_id INTEGER')
        _add_col('ladder_tests', 'primer_inv_id',    'primer_inv_id INTEGER')
        _add_col('ladder_tests', 'casing_inv_id',    'casing_inv_id INTEGER')
        _add_col('ladder_tests', 'rounds_per_step',  'rounds_per_step INTEGER')

    # Seed default threshold settings if they don't exist
    _defaults = {
        'low_stock_powder_lbs': '0.5',
        'low_stock_primers':    '200',
        'low_stock_bullets':    '100',
        'low_stock_casings':    '50',
    }
    db = SessionLocal()
    try:
        for key, val in _defaults.items():
            if not db.query(Setting).filter(Setting.key == key).first():
                db.add(Setting(key=key, value=val))
        db.commit()
    finally:
        db.close()