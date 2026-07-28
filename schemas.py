from pydantic import BaseModel
from typing import Optional


class SoldPayload(BaseModel):
    is_sold: bool
    price_sold: float = 0.0


class FirearmPatchPayload(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    caliber: Optional[str] = None
    scope_optic: Optional[str] = None
    price_paid: Optional[float] = None
    serial_number: Optional[str] = None


class ScopeMountPayload(BaseModel):
    mount_type: Optional[str] = None  # "firearm", "barrel", or null to unmount
    mount_id: Optional[int] = None


class AmmoPatchPayload(BaseModel):
    brand: Optional[str] = None
    caliber: Optional[str] = None
    bullet_type: Optional[str] = None
    bullet_weight: Optional[float] = None
    bullet_bc: Optional[float] = None
    line_or_powder: Optional[str] = None
    charge_weight: Optional[float] = None
    coal: Optional[float] = None
    qty_sealed: Optional[int] = None
    qty_open: Optional[int] = None
    price_paid: Optional[float] = None
    rounds_per_box: Optional[int] = None
    ammo_category: Optional[str] = None
    shell_size: Optional[str] = None
    shot_size: Optional[str] = None
    upc: Optional[str] = None
    factory_velocity_fps: Optional[float] = None
    muzzle_energy_ftlb: Optional[float] = None
    lead_free: Optional[bool] = None
    case_type: Optional[str] = None
    reloadable: Optional[bool] = None


class PowderPatch(BaseModel):
    brand: Optional[str] = None
    name: Optional[str] = None
    weight_lbs: Optional[float] = None
    price_paid: Optional[float] = None
    notes: Optional[str] = None
    is_muzzleloader: Optional[bool] = None
    pellet_mode: Optional[bool] = None


class PrimerPatch(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    primer_type: Optional[str] = None
    quantity: Optional[int] = None
    price_paid: Optional[float] = None
    notes: Optional[str] = None
    is_muzzleloader: Optional[bool] = None


class BulletComponentPatch(BaseModel):
    brand: Optional[str] = None
    product_line: Optional[str] = None
    caliber: Optional[str] = None
    weight_gr: Optional[float] = None
    bullet_type: Optional[str] = None
    bc_g1: Optional[float] = None
    sku: Optional[str] = None
    quantity: Optional[int] = None
    price_paid: Optional[float] = None
    notes: Optional[str] = None
    is_muzzleloader: Optional[bool] = None


class CasingPatch(BaseModel):
    brand: Optional[str] = None
    caliber: Optional[str] = None
    quantity: Optional[int] = None
    times_fired: Optional[int] = None
    price_paid: Optional[float] = None
    notes: Optional[str] = None


class DeductPayload(BaseModel):
    powder_inv_id: Optional[int] = None
    primer_inv_id: Optional[int] = None
    bullet_inv_id: Optional[int] = None
    casing_inv_id: Optional[int] = None
    rounds_loaded: int = 0
    powder_charge_gr: Optional[float] = None


class LoadDataPatch(BaseModel):
    source: Optional[str] = None
    caliber: Optional[str] = None
    coal: Optional[float] = None
    primer: Optional[str] = None
    case_type: Optional[str] = None
    case_capacity_gr: Optional[float] = None
    barrel_length: Optional[str] = None
    barrel_twist: Optional[str] = None
    barrel_desc: Optional[str] = None
    notes: Optional[str] = None


class LoadDataEntryPayload(BaseModel):
    powder_name: str
    charge_min: Optional[float] = None
    charge_max: Optional[float] = None
    velocity_min: Optional[int] = None
    velocity_max: Optional[int] = None
    load_density_min: Optional[float] = None
    load_density_max: Optional[float] = None
    is_max_load: Optional[bool] = False
    is_most_accurate: Optional[bool] = False


class LadderTestPayload(BaseModel):
    name: str
    caliber: Optional[str] = None
    bullet_id: int
    powder_name: str
    primer: Optional[str] = None
    case_type: Optional[str] = None
    coal: Optional[float] = None
    date_started: Optional[str] = None
    notes: Optional[str] = None
    charge_start: Optional[float] = None
    charge_end: Optional[float] = None
    charge_increment: Optional[float] = None
    barrel_id: Optional[int] = None
    platform_id: Optional[int] = None
    powder_inv_id: Optional[int] = None
    primer_inv_id: Optional[int] = None
    casing_inv_id: Optional[int] = None
    rounds_per_step: Optional[int] = None


class LadderTestPatch(BaseModel):
    name: Optional[str] = None
    caliber: Optional[str] = None
    bullet_id: Optional[int] = None
    powder_name: Optional[str] = None
    primer: Optional[str] = None
    case_type: Optional[str] = None
    coal: Optional[float] = None
    date_started: Optional[str] = None
    notes: Optional[str] = None
    charge_start: Optional[float] = None
    charge_end: Optional[float] = None
    charge_increment: Optional[float] = None
    barrel_id: Optional[int] = None
    platform_id: Optional[int] = None
    powder_inv_id: Optional[int] = None
    primer_inv_id: Optional[int] = None
    casing_inv_id: Optional[int] = None
    rounds_per_step: Optional[int] = None


class TestPlatformPayload(BaseModel):
    name: str
    caliber: Optional[str] = None
    barrel_length: Optional[str] = None
    barrel_twist: Optional[str] = None
    notes: Optional[str] = None


class LadderTestStepPayload(BaseModel):
    charge_weight: float
    velocities_csv: Optional[str] = None
    rounds_fired: Optional[int] = None
    date_shot: Optional[str] = None
    notes: Optional[str] = None


class LadderTestStepPatch(BaseModel):
    charge_weight: Optional[float] = None
    velocities_csv: Optional[str] = None
    rounds_fired: Optional[int] = None
    date_shot: Optional[str] = None
    notes: Optional[str] = None


class SettingsPatch(BaseModel):
    low_stock_powder_lbs: Optional[str] = None
    low_stock_primers: Optional[str] = None
    low_stock_bullets: Optional[str] = None
    low_stock_casings: Optional[str] = None


class AdminUserPatch(BaseModel):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class ScopePatchPayload(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    magnification: Optional[str] = None
    units: Optional[str] = None
    price_paid: Optional[float] = None
    quantity: Optional[int] = None


class TCReceiverPatchPayload(BaseModel):
    platform: Optional[str] = None
    serial_number: Optional[str] = None
    notes: Optional[str] = None
    price_paid: Optional[float] = None


class TCBarrelPatchPayload(BaseModel):
    caliber: Optional[str] = None
    twist_rate: Optional[str] = None
    barrel_length: Optional[str] = None
    hardware_color: Optional[str] = None
    is_threaded: Optional[bool] = None
    has_muzzle_brake: Optional[bool] = None
    price_paid: Optional[float] = None


class UseRoundsPayload(BaseModel):
    rounds: int


class WishlistPatchPayload(BaseModel):
    item_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    caliber: Optional[str] = None
    priority: Optional[str] = None
    est_price: Optional[float] = None
    notes: Optional[str] = None
    url: Optional[str] = None
