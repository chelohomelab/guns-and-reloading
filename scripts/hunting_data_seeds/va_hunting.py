"""Seed Virginia 2026-27 hunting data, hand-extracted from the DWR's 2026-27
Hunting, Trapping, and Migratory Game Bird Seasons guide.

Run once per deployment: `.venv/bin/python scripts/hunting_data_seeds/va_hunting.py`
(re-runnable — wipes and re-inserts Virginia's rows each time).

NOTE ON SCOPE: Virginia's Bear/Deer/Turkey seasons are split by individual COUNTY
(not by a handful of zones like NJ/PA), often with 5-10+ distinct county groups per
weapon/season, each listing 20-40 county names. Transcribing every county name for
every sub-variant would make the calendar unusable, so zone_or_area below uses
SHORT REGIONAL labels (e.g. "Most counties east of the Blue Ridge") that capture the
real geographic pattern without the full county list — check dwr.virginia.gov for
your exact county before hunting Bear/Deer/Turkey. Elk/Small Game/Furbearer/Trapping/
Migratory Birds are mostly statewide or cleanly zoned and are seeded at full fidelity.
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from database import SessionLocal, HuntingState, HuntingSeasonEntry, HuntingRegulationNote  # noqa: E402

db = SessionLocal()
existing = db.query(HuntingState).filter(HuntingState.name == "Virginia").first()
if existing:
    db.delete(existing)
    db.commit()

state = HuntingState(name="Virginia", abbreviation="VA", display_order=4)
db.add(state)
db.commit()
db.refresh(state)

YEAR = "2026-27"
COUNTY_CAVEAT = "Exact counties vary within this region — check dwr.virginia.gov/hunting for your specific county before hunting."

_season_order = {}


def season(game_type, species, season_label, start, end, weapon=None, zone="Statewide",
           bag=None, notes=None, weekday=None):
    order = _season_order.get(game_type, 0)
    _season_order[game_type] = order + 1
    db.add(HuntingSeasonEntry(
        state_id=state.id, season_year_label=YEAR, game_type=game_type,
        species=species, season_label=season_label, weapon=weapon,
        zone_or_area=zone, start_date=start, end_date=end,
        weekday_filter=weekday, bag_limit=bag, notes=notes,
        display_order=order,
    ))


_note_order = {}


def note(game_type, title, body):
    order = _note_order.get(game_type, 0)
    _note_order[game_type] = order + 1
    db.add(HuntingRegulationNote(
        state_id=state.id, game_type=game_type, title=title, body=body,
        display_order=order,
    ))


# ============================== BLACK BEAR ==============================
G = "Black Bear"
season(G, "Black Bear", "Youth & Apprentice Weekend", "2026-10-10", "2026-10-11", zone="Statewide")
season(G, "Black Bear", "Early Firearms", "2026-09-28", "2026-09-30", zone=f"SW VA counties (Buchanan, Dickenson, Lee, Russell, Scott, Washington, Wise) — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Archery", "2026-10-03", "2026-11-13", weapon="Bow", zone=f"Most counties east of the Blue Ridge — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Archery", "2026-10-17", "2026-11-13", weapon="Bow", zone=f"Most counties west of the Blue Ridge — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Muzzleloader", "2026-11-07", "2026-11-13", weapon="Muzzleloader", zone=f"Most counties east of the Blue Ridge — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Muzzleloader", "2026-11-10", "2026-11-13", weapon="Muzzleloader", zone=f"Most counties west of the Blue Ridge — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Firearms", "2026-11-23", "2027-01-02", weapon="Firearms", zone=f"Group A counties (mostly SW/central VA) — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Firearms", "2026-11-27", "2026-11-29", weapon="Firearms", zone=f"Group B counties (mostly west of Blue Ridge) — {COUNTY_CAVEAT}", notes="Also Dec. 21-Jan. 2 (2nd segment).")
season(G, "Black Bear", "Firearms", "2026-11-30", "2027-01-02", weapon="Firearms", zone=f"Group C counties (mostly SE/Southside VA) — {COUNTY_CAVEAT}")
season(G, "Black Bear", "Firearms", "2026-10-01", "2027-01-02", weapon="Firearms", zone="Cities of Chesapeake, Suffolk & Virginia Beach")
season(G, "Black Bear", "Firearms", "2026-10-01", "2027-01-02", weapon="Firearms", bag="0", zone="Accomack & Northampton counties — closed")
season(G, "Black Bear", "Hound Training/Chase", "2026-08-01", "2026-09-26", zone=f"Most counties (see guide p.10 for the full list) — {COUNTY_CAVEAT}", notes="NO bear may be taken during this season — training/chasing only. Hours 4am-10pm.")
season(G, "Black Bear", "Hound Training/Chase", "2026-11-30", "2026-12-19", zone=f"Some counties, excluding Sundays — {COUNTY_CAVEAT}", notes="NO bear may be taken during this season. Hours 4am-10pm.")
season(G, "Black Bear", "Hound Training/Chase", "2026-08-08", "2026-08-22", zone="Cavalier WMA only", notes="NO bear may be taken during this season.")

note(G, "Bag Limit", "One bear per license year, minimum 100 lbs live weight or 75 lbs dressed weight. Females with cubs may NOT be harvested — cubs can be 30-50 lbs by fall, so watch carefully before shooting.")
note(G, "County-Level Detail Required", f"VA's bear seasons are set by individual county (and public vs. private land), not by a few simple zones — the digest lists 5-10+ distinct county groups per weapon. Zones above are compressed regional summaries; {COUNTY_CAVEAT}")
note(G, "Dogs Restrictions", "Dogs may not be used to hunt bear on Sundays within 200 yards of a place of worship, during archery/muzzleloader season (except specific youth weekends), on most WMAs, or in specific named counties during firearms season — see dwr.virginia.gov for the full list.")

# ============================== DEER ==============================
G = "Deer"
season(G, "Deer", "Early Archery", "2026-10-03", "2026-11-13", weapon="Bow", zone="Statewide", bag="Either-sex full season")
season(G, "Deer", "Late Archery", "2026-12-13", "2027-01-02", weapon="Bow", zone=f"Henry & Patrick counties + most counties west of the Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex full season")
season(G, "Deer", "Late Archery", "2026-11-29", "2027-01-02", weapon="Bow", zone=f"Far SW VA counties + National Forest/DWR lands west of Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex full season")
season(G, "Deer", "Late Archery", "2026-12-01", "2027-01-02", weapon="Bow", zone="Cities of Chesapeake, Suffolk & Virginia Beach", bag="Either-sex full season")
season(G, "Deer", "Urban Archery", "2026-09-05", "2026-10-02", weapon="Bow", zone=f"Many incorporated cities/towns + some counties (Chesterfield, Fairfax, James City, Prince William, Roanoke, Stafford, York, etc.) — {COUNTY_CAVEAT}", bag="Antlerless only")
season(G, "Deer", "Urban Archery", "2027-01-03", "2027-03-28", weapon="Bow", zone=f"Same urban areas as above — {COUNTY_CAVEAT}", bag="Antlerless only")
season(G, "Deer", "NOVA Late Archery", "2027-03-29", "2027-04-25", weapon="Bow", zone="Arlington, Fairfax, Loudoun & Prince William counties (except DWR-owned lands)", bag="Antlerless only")

season(G, "Deer", "Early Muzzleloader", "2026-10-31", "2026-11-13", weapon="Muzzleloader", zone=f"Most areas east of the Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex full season")
season(G, "Deer", "Early Muzzleloader", "2026-10-31", "2026-11-13", weapon="Muzzleloader", zone=f"State Forest/Park/DWR lands & Philpott Reservoir — {COUNTY_CAVEAT}", bag="Either-sex Nov. 7 only")
season(G, "Deer", "Early Muzzleloader", "2026-10-31", "2026-11-13", weapon="Muzzleloader", zone=f"Most private lands west of the Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex full season")
season(G, "Deer", "Early Muzzleloader", "2026-10-31", "2026-11-13", weapon="Muzzleloader", zone=f"National Forest/DWR lands west of the Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex Nov. 7 only")
season(G, "Deer", "Late Muzzleloader", "2026-12-12", "2027-01-02", weapon="Muzzleloader", zone="Henry & Patrick counties + Federal/DWR lands in Franklin County", bag="Either-sex full season")
season(G, "Deer", "Late Muzzleloader", "2026-12-12", "2027-01-02", weapon="Muzzleloader", zone="Cities of Chesapeake, Suffolk & Virginia Beach", bag="Either-sex Dec. 28-Jan. 2 & Jan. 2")
season(G, "Deer", "Late Muzzleloader", "2026-12-12", "2027-01-02", weapon="Muzzleloader", zone=f"Most private/public lands west of the Blue Ridge — {COUNTY_CAVEAT}", bag="Either-sex varies by area — see notes", notes="Full-season either-sex in some counties, Dec.28-Jan.2 or Jan.2-only in others; check your county.")

season(G, "Deer", "Youth & Apprentice Weekend", "2026-09-26", "2026-09-27", weapon="Firearms", zone="Statewide", bag="Either-sex both days", notes="Deer hunting with dogs prohibited this weekend.")
season(G, "Deer", "Early Antlerless (Firearms)", "2026-09-05", "2026-10-02", weapon="Firearms", zone=f"Arlington, Fairfax, Loudoun, Prince William + several private-land counties — {COUNTY_CAVEAT}", bag="Antlerless only", notes="Dogs may not be used during this season.")
season(G, "Deer", "Firearms (Private Land)", "2026-11-14", "2026-12-12", weapon="Firearms", zone=f"Group A private-land counties (mostly SW VA) — {COUNTY_CAVEAT}", bag="Either-sex on specific days only — see notes", notes="Either-sex days vary by county group: single days, weekends, or full-season depending on the specific county — see guide p.16.")
season(G, "Deer", "Firearms (Private Land)", "2026-11-14", "2027-01-02", weapon="Firearms", zone=f"Largest group of private-land counties statewide — {COUNTY_CAVEAT}", bag="Either-sex full season")
season(G, "Deer", "Firearms (Private Land)", "2026-10-01", "2026-11-30", weapon="Firearms", zone="Cities of Chesapeake, Suffolk (east of Dismal Swamp line) & Virginia Beach", bag="Either-sex full season")
season(G, "Deer", "Late Antlerless (Firearms)", "2027-01-03", "2027-03-28", weapon="Firearms", zone=f"Arlington, Fairfax, Loudoun, Prince William + several private-land counties — {COUNTY_CAVEAT}", bag="Antlerless only", notes="Dogs may not be used during this season.")
season(G, "Deer", "Late Antlerless (Firearms)", "2027-01-03", "2027-01-31", weapon="Firearms", zone="Private lands in Bedford County", bag="Antlerless only")
season(G, "Deer", "Firearms (Public Land / WMAs & National Forest)", "2026-09-26", "2026-09-27", weapon="Firearms", zone="All DWR/National Forest public land", bag="Either-sex both days")
season(G, "Deer", "Firearms (Public Land / WMAs & National Forest)", "2026-10-01", "2027-01-02", weapon="Firearms", zone=f"Varies by specific WMA/National Forest tract — {COUNTY_CAVEAT} See guide p.17-18 for the exact either-sex days at each named WMA/State Forest.", bag="1 deer/day max on DWR land; either-sex days vary by property")

note(G, "Earn-A-Buck (EAB)", "In many counties (both east and west of the Blue Ridge — see guide p.14), you must harvest at least 1 antlerless deer on private land before taking a 2nd antlered buck there, and 2 antlerless deer before a 3rd buck. Rules also apply per-city/town. Check dwr.virginia.gov for whether EAB applies to your specific county.")
note(G, "Antler Point Restrictions", "In Alleghany, Bath, Highland, or Rockbridge counties: if you kill 2 antlered bucks in a license year, at least one must have 4+ antler points (1\"+ long) on one side.")
note(G, "County-Level Detail Required", f"Deer season dates/either-sex days vary by INDIVIDUAL county and by public vs. private land — the source guide lists 8-12+ distinct county/land groups per weapon. Zones above are compressed regional summaries; {COUNTY_CAVEAT}")
note(G, "CWD Precautions", "It's illegal to feed deer year-round within 25 miles of any known CWD-positive deer, anywhere in Virginia. Don't transport deer carcass parts out of a CWD Disease Management Area (DMA) — only meat, cleaned skull caps/antlers, hides, and a few other parts may leave a DMA.")

# ============================== ELK ==============================
G = "Elk"
season(G, "Elk", "Lottery Hunt", "2026-09-01", "2027-06-30", zone="Buchanan, Dickenson & Wise counties ONLY", notes="Elk hunting in these 3 counties is by lottery draw only — apply each February-March at dwr.virginia.gov. Exact season dates depend on the license drawn.")
season(G, "Elk", "Incidental Take During Deer Season", "2026-10-03", "2027-03-28", zone="Everywhere in Virginia EXCEPT Buchanan, Dickenson & Wise counties", bag="Any elk (bull, cow, or calf)", notes="Outside the 3 lottery counties, any elk may be taken incidentally on any day of an OPEN deer season (archery, muzzleloader, or firearms) with a regular deer license — no separate elk tag/lottery needed. Dates shown span the full archery-through-firearms deer season window; your actual legal days depend on which deer season is open in your specific county.")

note(G, "Two Very Different Systems", "Virginia's elk hunting works two ways: (1) a lottery-draw hunt in Buchanan/Dickenson/Wise counties (apply Feb-Mar), or (2) incidental take anywhere else in the state during any open deer season using your regular deer license — no elk tag needed outside the 3 lottery counties.")

# ============================== TURKEY ==============================
G = "Turkey"
season(G, "Wild Turkey", "Archery", "2026-10-03", "2026-11-13", weapon="Bow", zone="Statewide except where firearms turkey season is closed", bag="1/day, max 3/year (only 1 beardless)")
season(G, "Wild Turkey", "Fall Youth & Apprentice Weekend", "2026-10-10", "2026-10-11", zone="Statewide", bag="1 either-sex per weekend")
season(G, "Wild Turkey", "Fall Firearms", "2026-10-17", "2026-11-26", zone=f"Group A counties (mostly Shenandoah Valley/west) — {COUNTY_CAVEAT}", bag="1/day, max 3/year (only 1 beardless)", notes="Dates: Oct.17-30 and Nov.26.")
season(G, "Wild Turkey", "Fall Firearms", "2026-10-17", "2027-01-23", zone=f"Group B counties (mostly north/northern-Piedmont) — {COUNTY_CAVEAT}", bag="1/day, max 3/year (only 1 beardless)", notes="Dates: Oct.17-30, Nov.25-26, Nov.30-Dec.26, and Jan.9-23.")
season(G, "Wild Turkey", "Fall Firearms", "2026-10-17", "2026-12-12", zone=f"Group C counties (mostly eastern/Tidewater) — {COUNTY_CAVEAT}", bag="1/day, max 3/year (only 1 beardless)", notes="Dates: Oct.17-30, Nov.25-26, and Nov.30-Dec.12.")
season(G, "Wild Turkey", "Fall Firearms", "2026-10-17", "2027-01-23", zone=f"Group D counties (mostly Southside/central VA) — {COUNTY_CAVEAT}", bag="1/day, max 3/year (only 1 beardless)", notes="Dates: Oct.17-30, Nov.25-26, Nov.30-Dec.12, and Jan.9-23.")
season(G, "Wild Turkey", "Fall Firearms", "2026-10-17", "2027-01-23", zone="Arlington County & cities of Chesapeake, Norfolk, Portsmouth, Virginia Beach", bag="0", notes="Closed to fall firearms turkey.")
season(G, "Wild Turkey", "Spring Youth & Apprentice Weekend", "2027-04-03", "2027-04-04", zone="Statewide", bag="1 bearded bird per weekend")
season(G, "Wild Turkey", "Spring", "2027-04-10", "2027-04-25", zone="Statewide", bag="1 bearded bird, max 3/year", notes="Hunting hours 1/2 hr before sunrise until noon only.")
season(G, "Wild Turkey", "Spring", "2027-04-26", "2027-05-15", zone="Statewide", bag="1 bearded bird, max 3/year", notes="Hunting hours 1/2 hr before sunrise to sunset.")

note(G, "County-Level Detail Required", f"Fall firearms turkey season dates vary by county group. {COUNTY_CAVEAT}")

# ============================== SMALL GAME ==============================
G = "Small Game"
season(G, "Crow", "Regular Season", "2026-08-15", "2027-03-19", bag="No limit", weekday="Monday", notes="Hunting only allowed Mon/Wed/Fri/Sat. This entry marks Mondays; also legal Wed/Fri/Sat.")
season(G, "Groundhog", "Continuous Open Season", "2026-07-01", "2027-06-30", zone="Private lands", bag="No limit")
season(G, "Groundhog", "Open Season", "2026-09-01", "2027-03-10", zone="National Forest & DWR lands", bag="No limit")
season(G, "Groundhog", "Spring DWR Season", "2027-04-10", "2027-05-15", zone="DWR lands open to spring squirrel hunting only", bag="No limit")
season(G, "Groundhog", "Spring DWR Season", "2027-06-05", "2027-06-19", zone="DWR lands open to spring squirrel hunting only (not National Forest)", bag="No limit")
season(G, "Ruffed Grouse", "Regular Season", "2026-10-24", "2027-02-13", zone="West of I-95", bag="3/day")
season(G, "Ruffed Grouse", "Regular Season", "2026-10-24", "2027-02-13", zone="East of I-95", bag="0", notes="Closed east of I-95.")
season(G, "Bobwhite Quail", "Regular Season", "2026-11-07", "2027-01-31", zone="Statewide except public lands west of the Blue Ridge & Flippo-Gentry WMA (Sussex Co.)", bag="6/day")
season(G, "Ring-Necked Pheasant", "Regular Season", "2026-11-07", "2027-01-31", zone="Statewide", bag="No limit")
season(G, "Cottontail Rabbit", "Regular Season", "2026-10-31", "2027-02-28", zone="Statewide", bag="6/day")
season(G, "Gray & Red Squirrel", "Fall Season", "2026-09-05", "2027-02-28", zone="Statewide unless otherwise posted, plus listed WMAs", bag="6/day (all squirrel species combined)")
season(G, "Fox Squirrel", "Fall Season", "2026-09-05", "2027-01-31", zone=f"Counties west of the Blue Ridge + Albemarle, Bedford, Culpeper, Fauquier, Franklin, Greene, Henry, Loudoun, Madison, Orange, Patrick, Prince William & Rappahannock — {COUNTY_CAVEAT} Closed on National Forest lands.", bag="6/day (all squirrel species combined)")
season(G, "Gray, Red & Fox Squirrel", "Spring Season", "2027-06-05", "2027-06-19", zone="Specific listed WMAs only (see guide p.24 for the full list)", bag="6/day (all squirrel species combined)")

note(G, "Species Covered", "Crow, Groundhog (woodchuck), Ruffed Grouse, Bobwhite Quail, Ring-Necked Pheasant, Cottontail Rabbit, and Gray/Red/Fox Squirrel.")
note(G, "Crow Hunting Days", "During the season, crow hunting is only permitted Friday, Saturday, and Sunday (changed this year from the previous Mon/Wed/Fri/Sat rule).")
note(G, "Rabbit Disease (RHDV2)", "Rabbit hemorrhagic disease virus 2 is present as a risk in the region — see dwr.virginia.gov for current precautions before handling wild rabbit carcasses.")

# ============================== TRAPPING (Furbearer Hunting + Trapping combined) ==============================
G = "Trapping"
# Hunting
season(G, "Bobcat", "Hunting — Archery", "2026-10-03", "2026-10-31", weapon="Bow", zone="Statewide", bag="2 per hunting party per 24-hr period", notes="All hunted bobcats must be reported within 24 hrs via DWR's electronic system. CITES tag may be required.")
season(G, "Bobcat", "Hunting — Firearms", "2026-11-01", "2027-02-28", weapon="Firearms", zone="Statewide", bag="2 per hunting party per 24-hr period")
season(G, "Coyote", "Hunting — Continuous Open Season", "2026-07-01", "2027-06-30", zone="Statewide", bag="No limit", notes="On National Forest/DWR lands, coyote hunting is restricted to Sept.1-Mar.10 and Apr.10-May15 (plus Jun.5-19 on some DWR lands unless posted).")
season(G, "Red Fox", "Hunting", "2026-11-01", "2027-02-28", zone="Statewide except Albemarle, Clarke, Culpeper, Fauquier (except Quantico), Loudoun, Louisa & Rappahannock counties", bag="No limit")
season(G, "Gray Fox", "Hunting", "2027-01-01", "2027-02-28", zone="Statewide except Albemarle, Clarke, Culpeper, Fauquier (except Quantico), Loudoun, Louisa & Rappahannock counties", bag="1 per hunting party per 24-hr period", notes="All harvested gray foxes must be reported within 24 hrs.")
season(G, "Fox", "Chase-Only (no firearm)", "2026-11-01", "2027-02-28", zone="Statewide, with exceptions (closed Mar.1-Oct.31 & during firearms deer season on National Forest and certain WMAs)")
season(G, "Opossum", "Hunting", "2026-10-15", "2027-03-10", zone="Statewide", bag="No limit")
season(G, "Raccoon", "Hunting", "2026-10-15", "2027-03-10", zone="East of the Blue Ridge", bag="2 per hunter per 24-hr period", notes="Lights allowed if not attached to/cast from a vehicle.")
season(G, "Raccoon", "Hunting", "2026-10-15", "2027-03-10", zone="West of the Blue Ridge", bag="2 per hunting party per 24-hr period")
season(G, "Raccoon", "Chase-Only (no firearm)", "2026-07-01", "2027-06-30", zone="DWR lands west of the Blue Ridge & National Forest (bear-chase-eligible lands, Aug.1-Sep.26)")
season(G, "Striped Skunk", "Hunting — Continuous Open Season", "2026-07-01", "2027-06-30", zone="Statewide except National Forest & DWR lands", bag="No limit")
season(G, "Striped Skunk", "Hunting", "2026-09-01", "2027-03-10", zone="National Forest & DWR lands", bag="No limit", notes="Also Apr.10-May.15 and Jun.5-19 on DWR lands unless posted.")
season(G, "Fisher", "Hunting", "2026-07-01", "2027-06-30", bag="0", zone="Statewide — closed", notes="Report verifiable sightings at dwr.virginia.gov/report-rare-animals.")
season(G, "Spotted Skunk", "Hunting", "2026-07-01", "2027-06-30", bag="0", zone="Statewide — closed", notes="Pelts may not be sold. Report verifiable sightings.")
# Trapping
season(G, "Beaver", "Trapping", "2026-12-01", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "Bobcat", "Trapping", "2026-11-15", "2027-02-28", zone="Statewide", bag="No limit", notes="Must be reported within 24 hrs electronically; CITES tag may be required.")
season(G, "Coyote", "Trapping — Continuous Open Season", "2026-07-01", "2027-06-30", zone="Statewide", bag="No limit")
season(G, "Red Fox & Gray Fox", "Trapping", "2026-11-15", "2027-02-28", zone="Statewide except Clarke, Fauquier, Loudoun & Rappahannock counties", bag="No limit", notes="All trapped gray foxes must be reported within 24 hrs.")
season(G, "Mink", "Trapping", "2026-12-01", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "Muskrat", "Trapping", "2026-12-01", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "Nutria", "Trapping — Continuous Open Season", "2026-07-01", "2027-06-30", zone="Statewide", bag="No limit", notes="Report verifiable sightings at cmi.vt.edu/ReportNutria.")
season(G, "Opossum", "Trapping", "2026-11-15", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "River Otter", "Trapping", "2026-12-01", "2027-02-28", zone="Counties west of the Blue Ridge", bag="4 per trapper")
season(G, "River Otter", "Trapping", "2026-12-01", "2027-02-28", zone="Counties east of the Blue Ridge", bag="No season bag limit")
season(G, "Raccoon", "Trapping", "2026-11-15", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "Striped Skunk", "Trapping — Continuous Open Season", "2026-07-01", "2027-06-30", zone="Statewide", bag="No limit")
season(G, "Weasel", "Trapping", "2026-12-01", "2027-02-28", zone="Statewide", bag="No limit")
season(G, "Cottontail Rabbit", "Box-Trapping", "2026-10-15", "2027-01-31", zone="Statewide", bag="No limit", notes="Box traps only, landowner permission required. Live box-trapped rabbits may not be moved outside the county of capture. No license required to box-trap rabbits.")
season(G, "Fisher", "Trapping", "2026-07-01", "2027-06-30", bag="0", zone="Statewide — closed", notes="Report verifiable sightings at dwr.virginia.gov/report-rare-animals.")
season(G, "Spotted Skunk", "Trapping", "2026-07-01", "2027-06-30", bag="0", zone="Statewide — continuously closed", notes="Pelts may not be sold.")

note(G, "License Types", "Hunting most furbearers just needs a general hunting license. Trapping any furbearer needs a trapping license. Some species (bobcat, otter) may also need CITES tagging for pelt sale/export — see dwr.virginia.gov for details.")
note(G, "Local Continuous-Open-Season Exceptions", "Certain localities and private lands have continuous open seasons for several furbearer species beyond what's listed above — check the full regulations online before assuming a species is out of season on your specific property.")

# ============================== MIGRATORY BIRDS ==============================
season("Migratory Birds", "Mourning/White-Winged Dove", "Regular Season", "2026-09-05", "2026-10-24", bag="15/day, 45 possession")
season("Migratory Birds", "Mourning/White-Winged Dove", "Regular Season", "2026-11-21", "2026-11-29", bag="15/day, 45 possession")
season("Migratory Birds", "Mourning/White-Winged Dove", "Regular Season", "2026-12-19", "2027-01-18", bag="15/day, 45 possession")
season("Migratory Birds", "Clapper & King Rail / Sora & Virginia Rail / Gallinule", "Regular Season", "2026-09-05", "2026-10-24", bag="Clapper 10/30, Sora/Virginia 25/75, Gallinule 15/45, King 1/3")
season("Migratory Birds", "Clapper & King Rail / Sora & Virginia Rail / Gallinule", "Regular Season", "2026-11-10", "2026-11-29", bag="Clapper 10/30, Sora/Virginia 25/75, Gallinule 15/45, King 1/3")
season("Migratory Birds", "American Woodcock", "Regular Season", "2026-11-11", "2026-12-01", bag="3/day, 9 possession")
season("Migratory Birds", "American Woodcock", "Regular Season", "2026-12-26", "2027-01-18", bag="3/day, 9 possession")
season("Migratory Birds", "Wilson's Snipe", "Regular Season", "2026-09-28", "2026-11-29", bag="8/day, 24 possession")
season("Migratory Birds", "Wilson's Snipe", "Regular Season", "2026-12-19", "2027-01-31", bag="8/day, 24 possession")
season("Migratory Birds", "September Teal", "Regular Season", "2026-09-19", "2026-09-27", zone="East of I-95", bag="6/day (any combination blue-winged/green-winged teal)")
season("Migratory Birds", "September Teal", "Regular Season", "2026-09-22", "2026-09-27", zone="West of I-95", bag="6/day (any combination blue-winged/green-winged teal)")
season("Migratory Birds", "Mergansers", "Regular Season", "2026-10-09", "2026-10-12", bag="5/day, 15 possession")
season("Migratory Birds", "Mergansers", "Regular Season", "2026-11-18", "2026-11-29", bag="5/day, 15 possession")
season("Migratory Birds", "Mergansers", "Regular Season", "2026-12-19", "2027-01-31", bag="5/day, 15 possession")
season("Migratory Birds", "Ducks", "Regular Season", "2026-10-09", "2026-10-12", bag="6/day, 3x possession", notes="Black duck closed this segment.")
season("Migratory Birds", "Ducks", "Regular Season", "2026-11-18", "2026-11-29", bag="6/day, 3x possession")
season("Migratory Birds", "Ducks", "Regular Season", "2026-12-19", "2027-01-31", bag="6/day, 3x possession")
season("Migratory Birds", "Coots", "Regular Season", "2026-10-09", "2026-10-12", bag="15/day, 45 possession")
season("Migratory Birds", "Coots", "Regular Season", "2026-11-18", "2026-11-29", bag="15/day, 45 possession")
season("Migratory Birds", "Coots", "Regular Season", "2026-12-19", "2027-01-31", bag="15/day, 45 possession")
season("Migratory Birds", "Canada Goose", "Atlantic Population Zone Regular Season", "2026-11-24", "2026-11-29", zone="Atlantic Population Zone", bag="2/day, 6 possession", notes="Also Dec.24-Jan.31 (2nd segment). Includes white-fronted geese.")
season("Migratory Birds", "Canada Goose", "Atlantic Population Zone Regular Season", "2026-12-24", "2027-01-31", zone="Atlantic Population Zone", bag="2/day, 6 possession")
season("Migratory Birds", "Canada Goose", "Resident Population Zone Regular Season", "2026-11-18", "2026-11-29", zone="Resident Population Zone", bag="5/day, 15 possession", notes="Also Dec.19-Feb.21 (2nd segment). Includes white-fronted geese.")
season("Migratory Birds", "Canada Goose", "Resident Population Zone Regular Season", "2026-12-19", "2027-02-21", zone="Resident Population Zone", bag="5/day, 15 possession")
season("Migratory Birds", "Canada Goose", "September Season", "2026-09-01", "2026-09-25", zone="Statewide (East/West of I-95 have slightly different shooting hours)", bag="10/day, 30 possession", notes="Not permitted on Amelia & Dick Cross WMAs.")
season("Migratory Birds", "Light Goose (Snow/Ross's)", "Regular Season", "2026-11-25", "2027-03-10", bag="25/day, no possession limit")
season("Migratory Birds", "Light Goose (Snow/Ross's)", "Conservation Order", "2026-12-04", "2027-03-10", bag="No limit", notes="Registration required online or by phone before hunting; exact 2026 start date determined in September 2026.")
season("Migratory Birds", "Atlantic Brant", "Regular Season", "2026-12-19", "2026-12-31", bag="1/day, 3 possession")
season("Migratory Birds", "Atlantic Brant", "Regular Season", "2027-01-15", "2027-01-31", bag="1/day, 3 possession")
season("Migratory Birds", "Tundra Swan", "Permit Hunt", "2026-11-15", "2027-01-31", zone="Counties/portions east of I-95 and south of the Prince William/Stafford county line at Chopawamsic Creek (Quantico)", bag="1 per permit, per season", notes="Requires applying for and receiving a tundra swan hunt permit before hunting.")

note("Migratory Birds", "License Requirements", "All migratory bird hunters (licensed or exempt) need annual HIP registration (new each July 1). Federal duck stamp required for waterfowl hunters 16+. Virginia also requires its own state Migratory Waterfowl Conservation Stamp for waterfowl hunters 16+.")
note("Migratory Birds", "Non-Toxic Shot", "Required for rails, gallinules, snipe, and all waterfowl/mergansers/coots.")
note("Migratory Birds", "Youth & Veterans/Military Waterfowl Days", "Oct. 24, 2026 and Feb. 6, 2027 — open to youth 15 and under, military veterans, and active-duty Armed Forces/National Guard/Reserve members, with the normal per-species daily bag limit.")

db.commit()

for gt in ["Black Bear", "Deer", "Elk", "Turkey", "Small Game", "Migratory Birds", "Trapping"]:
    n_seasons = db.query(HuntingSeasonEntry).filter(HuntingSeasonEntry.state_id == state.id, HuntingSeasonEntry.game_type == gt).count()
    n_notes = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type == gt).count()
    print(f"{gt}: {n_seasons} season entries, {n_notes} notes")

db.close()
print("Done.")
