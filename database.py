from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

import os as _os
_os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite:///./data/reloading.db"

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
    bc_g7 = Column(Float, nullable=True)
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
    bc_g7        = Column(Float,  nullable=True)
    rounds_per_box = Column(Integer, nullable=True)
    primer_type  = Column(String, nullable=True)
    primer_model = Column(String, nullable=True)
    powder_name  = Column(String, nullable=True)
    image_path   = Column(String, nullable=True)
    ammo_category = Column(String, nullable=True)
    updated_at   = Column(String, nullable=True)


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

    if 'upc_cache' in inspector.get_table_names():
        _add_col('upc_cache', 'ammo_category', 'ammo_category VARCHAR')

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