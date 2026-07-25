import math

def calculate_shot_metrics(velocity_string: str):
    """
    Takes a string like "2750, 2762, 2748" 
    Returns a dict with (avg_velocity, extreme_spread, standard_deviation)
    """
    if not velocity_string or not velocity_string.strip():
        return {"avg": 0.0, "es": 0.0, "sd": 0.0}
    
    try:
        # Convert the comma-separated string into a clean list of floats
        velocities = [float(v.strip()) for v in velocity_string.split(",") if v.strip()]
    except ValueError:
        # Handle cases where user typed a typo or non-number
        return {"avg": 0.0, "es": 0.0, "sd": 0.0}
        
    n = len(velocities)
    if n == 0:
        return {"avg": 0.0, "es": 0.0, "sd": 0.0}
    if n == 1:
        return {"avg": velocities[0], "es": 0.0, "sd": 0.0}

    # 1. Calculate Average (Mean)
    avg_vel = sum(velocities) / n
    
    # 2. Calculate Extreme Spread (Max - Min)
    extreme_spread = max(velocities) - min(velocities)
    
    # 3. Calculate Sample Standard Deviation
    variance_sum = sum((v - avg_vel) ** 2 for v in velocities)
    standard_dev = math.sqrt(variance_sum / (n - 1))
    
    return {
        "avg": round(avg_vel, 1),
        "es": round(extreme_spread, 1),
        "sd": round(standard_dev, 1)
    }


# 1 MOA subtends ~1.047" at 100 yards, 1 MRAD subtends ~3.6" at 100 yards — both scale linearly
# with distance.
_MOA_INCHES_AT_100YD = 1.047
_MRAD_INCHES_AT_100YD = 3.6


def calculate_group_geometry(shots, poa=None, pixels_per_inch=None, distance_yards=None):
    """
    shots: list of {"x": float, "y": float} in a shared pixel space (image is y-down, x-right).
    poa: {"x": float, "y": float} or None — Point of Aim, same pixel space.
    pixels_per_inch: calibration scale in that same pixel space.
    distance_yards: needed for MOA/MRAD/offset conversion; those fields stay None without it.

    Returns extreme-spread/width/height (inches), MOA/MRAD group size, and — when poa is given —
    elevation/windage offset between the group's centroid and the POA, in inches and MOA.
    Positive elevation_offset_in = group center is HIGH of POA (dial DOWN to correct).
    Positive windage_offset_in = group center is RIGHT of POA (dial LEFT to correct).
    """
    empty = {
        "extreme_spread_in": 0.0, "width_in": 0.0, "height_in": 0.0,
        "moa": None, "mrad": None, "max_pair": None, "center": None,
        "elevation_offset_in": None, "windage_offset_in": None,
        "elevation_offset_moa": None, "windage_offset_moa": None,
    }
    if not shots or len(shots) < 2 or not pixels_per_inch:
        return empty

    max_dist, max_pair = 0.0, (0, 1)
    for i in range(len(shots)):
        for j in range(i + 1, len(shots)):
            d = math.hypot(shots[j]["x"] - shots[i]["x"], shots[j]["y"] - shots[i]["y"])
            if d > max_dist:
                max_dist, max_pair = d, (i, j)

    xs = [s["x"] for s in shots]
    ys = [s["y"] for s in shots]
    width_in = (max(xs) - min(xs)) / pixels_per_inch
    height_in = (max(ys) - min(ys)) / pixels_per_inch
    extreme_spread_in = max_dist / pixels_per_inch
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)

    def in_to_moa(inches):
        if inches is None or not distance_yards:
            return None
        return round(inches / (_MOA_INCHES_AT_100YD * distance_yards / 100), 3)

    def in_to_mrad(inches):
        if inches is None or not distance_yards:
            return None
        return round(inches / (_MRAD_INCHES_AT_100YD * distance_yards / 100), 3)

    elev_in = wind_in = elev_moa = wind_moa = None
    if poa is not None:
        elev_in = (poa["y"] - cy) / pixels_per_inch
        wind_in = (cx - poa["x"]) / pixels_per_inch
        elev_moa, wind_moa = in_to_moa(elev_in), in_to_moa(wind_in)

    return {
        "extreme_spread_in": round(extreme_spread_in, 3),
        "width_in": round(width_in, 3),
        "height_in": round(height_in, 3),
        "moa": in_to_moa(extreme_spread_in),
        "mrad": in_to_mrad(extreme_spread_in),
        "max_pair": max_pair,
        "center": {"x": cx, "y": cy},
        "elevation_offset_in": round(elev_in, 3) if elev_in is not None else None,
        "windage_offset_in": round(wind_in, 3) if wind_in is not None else None,
        "elevation_offset_moa": elev_moa,
        "windage_offset_moa": wind_moa,
    }