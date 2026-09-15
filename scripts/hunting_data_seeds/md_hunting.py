"""Seed Maryland 2026-27 hunting data, hand-extracted from the DNR's 2026-27
Guide to Hunting & Trapping.

Run once per deployment: `.venv/bin/python scripts/hunting_data_seeds/md_hunting.py`
(re-runnable — wipes and re-inserts Maryland's rows each time).
MD deer/sika are split into just 2 regions (Region A / Region B, boundary in
Washington County) plus a few named goose/duck zones for migratory birds —
much simpler than VA's per-county system.
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from database import SessionLocal, HuntingState, HuntingSeasonEntry, HuntingRegulationNote  # noqa: E402

db = SessionLocal()
existing = db.query(HuntingState).filter(HuntingState.name == "Maryland").first()
if existing:
    db.delete(existing)
    db.commit()

state = HuntingState(name="Maryland", abbreviation="MD", display_order=6)
db.add(state)
db.commit()
db.refresh(state)

YEAR = "2026-27"
SUNDAY_CAVEAT = "Sunday hunting for this species is only open in certain counties/locations with restricted hours — see the guide's Sunday hunting chart for your county."

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


# ============================== DEER ==============================
G = "Deer"
season(G, "White-tailed Deer", "Junior Deer Hunt Days", "2026-11-14", "2026-11-14", zone="Statewide (+ Sunday Nov.15 in certain counties)", bag="Region A: 1 antlered or 1 antlerless; Region B: 3 deer, max 1 antlered")
season(G, "White-tailed Deer", "Archery", "2026-09-11", "2026-10-21", weapon="Bow", bag="2 antlered total (all seasons combined) + antlerless per region rules")
season(G, "White-tailed Deer", "Archery", "2026-10-25", "2026-11-27", weapon="Bow", notes="Sunday only, certain counties.")
season(G, "White-tailed Deer", "Archery", "2026-12-14", "2026-12-18", weapon="Bow")
season(G, "White-tailed Deer", "Archery", "2027-01-03", "2027-01-07", weapon="Bow", notes="Sunday only, certain counties.")
season(G, "White-tailed Deer", "Archery", "2027-01-08", "2027-01-10", weapon="Bow", zone="Region A only")
season(G, "White-tailed Deer", "Archery", "2027-01-11", "2027-01-31", weapon="Bow")
season(G, "White-tailed Deer", "Archery — Primitive Deer Hunt Days", "2027-02-01", "2027-02-03", weapon="Longbow/Recurve/Flintlock/Sidelock Muzzleloader", notes="Counts toward the regular archery bag limit. Muzzleloading revolvers, draw-locks, and electronic sights prohibited.")
season(G, "White-tailed Deer", "Muzzleloader", "2026-10-22", "2026-10-24", weapon="Muzzleloader", bag="A 3rd antlered deer only via Bonus Antlered Deer Stamp, Region B only", notes="Bonus Antlered Deer Stamp NOT usable on these dates; only 1 total deer (antlered or antlerless) may be taken in Region A during this window.")
season(G, "White-tailed Deer", "Muzzleloader", "2026-12-19", "2027-01-02", weapon="Muzzleloader")
season(G, "White-tailed Deer", "Muzzleloader — Primitive Deer Hunt Days", "2027-02-01", "2027-02-03", weapon="Longbow/Recurve/Flintlock/Sidelock Muzzleloader")
season(G, "White-tailed Deer", "Firearms", "2026-11-28", "2026-12-12", weapon="Firearms/Air Gun")
season(G, "White-tailed Deer", "Firearms", "2027-01-08", "2027-01-10", weapon="Firearms/Air Gun", zone="Region B only")
season(G, "White-tailed Deer", "Antlerless — Region A Archery", "2026-09-11", "2026-10-21", weapon="Bow", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region A Archery", "2026-12-14", "2026-12-18", weapon="Bow", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region A Archery", "2027-01-11", "2027-01-31", weapon="Bow", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region A Muzzleloader", "2026-10-22", "2026-10-24", weapon="Muzzleloader", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region A Muzzleloader", "2026-12-26", "2027-01-02", weapon="Muzzleloader", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region A Firearms", "2026-12-05", "2026-12-12", weapon="Firearms", zone="Region A", bag="Up to 2 total antlerless, max 1/day")
season(G, "White-tailed Deer", "Antlerless — Region B Archery", "2026-09-11", "2026-10-21", weapon="Bow", zone="Region B", bag="15/season (unlimited in Suburban Deer Mgmt Zone: Anne Arundel, Baltimore, Howard, Montgomery, Prince George's)")
season(G, "White-tailed Deer", "Antlerless — Region B Archery", "2026-12-14", "2026-12-18", weapon="Bow", zone="Region B", bag="15/season (unlimited in Suburban Deer Mgmt Zone)")
season(G, "White-tailed Deer", "Antlerless — Region B Archery", "2027-01-11", "2027-01-31", weapon="Bow", zone="Region B", bag="15/season (unlimited in Suburban Deer Mgmt Zone)")
season(G, "White-tailed Deer", "Antlerless — Region B Muzzleloader", "2026-10-22", "2026-10-24", weapon="Muzzleloader", zone="Region B", bag="10/season")
season(G, "White-tailed Deer", "Antlerless — Region B Muzzleloader", "2026-10-26", "2026-10-31", weapon="Muzzleloader", zone="Region B", bag="10/season")
season(G, "White-tailed Deer", "Antlerless — Region B Muzzleloader", "2026-12-19", "2027-01-02", weapon="Muzzleloader", zone="Region B", bag="10/season")
season(G, "White-tailed Deer", "Antlerless — Region B Firearms", "2026-11-28", "2026-12-12", weapon="Firearms", zone="Region B", bag="10/season")
season(G, "White-tailed Deer", "Antlerless — Region B Firearms", "2027-01-08", "2027-01-10", weapon="Firearms", zone="Region B", bag="10/season")
season(G, "Sika Deer", "Archery", "2026-09-11", "2026-10-21", weapon="Bow", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Archery", "2026-12-14", "2026-12-18", weapon="Bow", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Archery", "2027-01-11", "2027-01-31", weapon="Bow", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Muzzleloader (Antlered or Antlerless)", "2026-10-22", "2026-10-24", weapon="Muzzleloader", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Muzzleloader (Antlered or Antlerless)", "2026-12-19", "2027-01-02", weapon="Muzzleloader", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Muzzleloader (Antlerless Only, Region B)", "2026-10-26", "2026-10-31", weapon="Muzzleloader", zone="Region B", bag="Counts toward the 3-deer sika limit")
season(G, "Sika Deer", "Firearms", "2026-11-28", "2026-12-12", weapon="Firearms", bag="3 deer, max 1 antlered")
season(G, "Sika Deer", "Firearms", "2027-01-08", "2027-01-10", weapon="Firearms", bag="3 deer, max 1 antlered")

note(G, "Two Deer Regions Only", "Maryland splits deer seasons into just 2 regions (A and B), divided by a line through Washington County (see the guide's map, p.18) — far simpler than most neighboring states' per-county or per-WMU systems.")
note(G, "Antlered Bag Limit & Antler Point Restriction", "Statewide limit: 2 antlered white-tailed deer/year max (1/day). A statewide Antler Point Restriction applies in some (not all) areas — one antlered deer in your yearly limit may be taken with no point restriction, but any ADDITIONAL antlered deer must have 3+ points on one antler. Junior hunters (16 and under) are exempt from the point restriction entirely.")
note(G, "Bonus Antlered Deer Stamp", "Lets a license holder take a 3rd antlered deer (with restrictions favoring Region B) — must be purchased before hunting for it, and can't be used during Oct.22-24 Muzzleloader dates. Not usable for sika deer.")
note(G, "Sika Deer Stamp", "An annual Sika Deer Stamp is required to hunt sika deer in any season — sika bag limits (3/season, max 1 antlered) are tracked independently of the white-tailed deer bag limit.")
note(G, "Sunday Hunting", f"Sunday deer hunting (both white-tailed and sika) is only open in certain counties on certain dates, with restricted hours in some — {SUNDAY_CAVEAT.replace('this species', 'deer')}")
note(G, "Public Land Antlerless Areas (Region A)", "Region A public lands open to antlerless white-tailed deer hunting include Billmeyer-Belle Grove WMA, Green Ridge State Forest, Savage River State Forest, Potomac State Forest, and several other named WMAs/state forests/parks — see guide p.21 for the full list.")

# ============================== BLACK BEAR ==============================
G = "Black Bear"
season(G, "Black Bear", "Firearms/Muzzleloader/Bow Season", "2026-10-26", "2026-10-31", zone="Allegany, Frederick, Garrett & Washington counties ONLY", bag="1 per permittee/subpermittee hunting team, and 1/person, for the season", notes="A Black Bear Hunting Permit (lottery-only, apply July 15-Aug.31) is required. No dogs, drones, or bait allowed. Shooting hours 1/2 hr before sunrise to 1/2 hr after sunset.")

note(G, "Lottery-Only Permit System", "Bear hunting requires a permit won through Maryland's Black Bear Lottery (apply July 15-Aug.31 each year, $15 non-refundable fee, one entry per applicant). A secondary lottery exists for Washington/Frederick counties specifically. Unsuccessful applicants earn a preference point; points reset to zero once you're selected.")
note(G, "Checking Requirements", "Harvested bears must be tagged immediately at the kill site and taken to an official bear checking station within 24 hours. The head and hide must stay together with proof of sex attached to one hindquarter if the carcass is quartered.")

# ============================== TURKEY ==============================
G = "Turkey"
season(G, "Wild Turkey", "Junior Turkey Hunt Days", "2027-04-17", "2027-04-17", bag="1 bearded turkey/day", notes="Also Sunday, April 18, 2027 in certain counties.")
season(G, "Wild Turkey", "Spring Season", "2027-04-19", "2027-05-24", bag="1 bearded bird/day, 2/season", notes="Includes Sundays in certain counties — see Sunday turkey hunting chart.")
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-08", zone="Allegany, Garrett & Washington counties (\"hunt area\" counties)", bag="Combined Fall+Winter limit: 1 turkey of either sex", notes="Includes Sundays in Allegany/Garrett/Washington.")
season(G, "Wild Turkey", "Winter Season", "2027-01-21", "2027-01-23", zone="Statewide", bag="Combined Fall+Winter limit: 1 turkey of either sex")

note(G, "Fall/Winter Share One Bag Limit", "The 2026 Fall Season and 2027 Winter Season share a single combined bag limit of 1 turkey of either sex — taking one closes out both seasons for you.")
note(G, "Legal Weapons Vary by Season", "Junior Hunt Days/Spring/Winter: shotgun (#4 shot or smaller), crossbow, vertical bow, or air gun (arrow/bolt only) — no rifles/handguns. Fall Season ONLY additionally allows rifles and handguns, plus shotguns firing a solid single projectile.")
note(G, "Sunday Turkey Hunting", "Sunday hunting is allowed April 18, 2027 (Junior Day) and all Sundays during an open turkey season, but only in specific counties (Calvert, Caroline, Carroll, Charles, Kent, Queen Anne's, Allegany, Cecil, Dorchester, Garrett, St. Mary's, Washington, Talbot, Somerset, Wicomico, Worcester) with varying private/public-land and shooting-hour restrictions — see the guide's Sunday turkey chart.")

# ============================== SMALL GAME ==============================
G = "Small Game"
season(G, "Eastern Cottontail Rabbit", "Regular Season", "2026-11-07", "2027-02-28", bag="4/day, 8 possession")
season(G, "Gray/Red (Piney)/Eastern Fox Squirrel", "Regular Season", "2026-09-05", "2027-02-28", bag="6/day, 12 possession")
season(G, "Delmarva Fox Squirrel", "Closed — Protected", "2026-09-05", "2027-02-28", bag="0", notes="May NOT be hunted in Maryland at all (protected species).")
season(G, "Bobwhite Quail", "Closed", "2026-11-07", "2027-01-15", zone="Allegany & Garrett counties; DNR land east of the Susquehanna River", bag="0")
season(G, "Bobwhite Quail", "Regular Season", "2026-11-07", "2027-01-15", zone="Private lands east of the Susquehanna + all lands west of it (except Allegany & Garrett)", bag="6/day, 12 possession")
season(G, "Ruffed Grouse", "Regular Season", "2026-10-03", "2026-12-31", bag="2/day, 4 possession")
season(G, "Ring-Necked Pheasant", "Regular Season", "2026-11-07", "2027-02-28", bag="2/day (either sex), 4 possession")
season(G, "Crow", "Regular Season", "2026-08-15", "2027-03-15", bag="No limit", weekday="Wednesday", notes="Hunting only Wed/Thu/Fri/Sat. This entry marks Wednesdays; also legal Thu/Fri/Sat.")

note(G, "Species Not Huntable", "Delmarva fox squirrel and snowshoe hare may NOT be hunted anywhere in Maryland.")
note(G, "Fluorescent Orange", "Required for all small game hunting except crow hunting.")
note(G, "Sunday Hunting", f"Cottontail rabbit, gray/fox/red squirrel, quail (where open), ruffed grouse, and pheasant may be hunted on Sundays only in Allegany, Cecil, Garrett, St. Mary's, Washington, Calvert, Caroline, Charles, Dorchester, Queen Anne's, Talbot, Somerset, Wicomico, and Worcester counties, with varying private/public-land and shooting-hour restrictions. {SUNDAY_CAVEAT.replace('this species', 'small game')}")
note(G, "First Day of Firearms Deer Season", "It's illegal to hunt any animal other than deer on the opening day of the Deer Firearms Season, except coyotes.")

# ============================== TRAPPING (Furbearer Hunting + Trapping) ==============================
G = "Trapping"
season(G, "Beaver", "Trapping Only", "2026-12-15", "2027-03-15", zone="All counties except Allegany & Garrett", bag="No limit")
season(G, "Beaver", "Trapping Only", "2026-12-01", "2027-03-15", zone="Allegany & Garrett counties", bag="No limit")
season(G, "Bobcat", "Closed", "2026-09-01", "2027-08-31", bag="0", notes="Bobcat may not be taken in Maryland at all.")
season(G, "Coyote", "Hunting (Firearms/Archery/Air Gun) — No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="May be hunted year-round, day and night, in all counties.")
season(G, "Coyote", "Trapping", "2026-11-14", "2027-02-28", zone="East of the Chesapeake Bay & Susquehanna River", bag="No limit")
season(G, "Coyote", "Trapping", "2026-10-31", "2027-02-15", zone="West of the Chesapeake Bay & Susquehanna River", bag="No limit")
season(G, "Fisher & Long-Tailed Weasel", "Hunting/Trapping", "2026-10-31", "2027-02-01", bag="4/day, 4/season")
season(G, "Red & Gray Fox", "Trapping/Hunting — No Closed Season", "2026-07-01", "2027-07-31", zone="Charles & Dorchester counties", bag="No limit")
season(G, "Red & Gray Fox", "Trapping/Hunting", "2026-11-14", "2027-02-28", zone="Caroline, Cecil, Kent, Queen Anne's, Somerset, Talbot, Wicomico & Worcester counties", bag="No limit")
season(G, "Red & Gray Fox", "Trapping/Hunting", "2026-10-31", "2027-02-15", zone="Allegany, Anne Arundel, Baltimore, Calvert, Carroll, Frederick, Garrett, Harford, Howard, Montgomery, Prince George's, St. Mary's & Washington counties", bag="No limit")
season(G, "Muskrat & Mink", "Trapping Only", "2026-11-14", "2027-02-15", zone="Allegany, Carroll, Frederick, Garrett, Howard & Washington counties", bag="No limit")
season(G, "Muskrat & Mink", "Trapping Only", "2027-01-01", "2027-03-15", zone="Anne Arundel, Calvert, Caroline, Charles, Dorchester, Montgomery, Prince George's, St. Mary's, Talbot & Wicomico counties", bag="No limit")
season(G, "Muskrat & Mink", "Trapping Only", "2026-12-15", "2027-03-15", zone="Baltimore, Cecil, Harford, Kent, Queen Anne's, Somerset & Worcester counties", bag="No limit")
season(G, "River Otter", "Trapping Only", "2026-12-15", "2027-03-15", zone="Most counties (except Allegany, Carroll, Frederick, Garrett, Howard, Montgomery & Washington)", bag="10/day, 10/season")
season(G, "River Otter", "Trapping Only", "2026-12-15", "2027-03-15", zone="Carroll, Frederick, Howard, Montgomery & Washington counties", bag="2/day, 2/season")
season(G, "River Otter", "Trapping Only", "2026-12-01", "2027-03-15", zone="Allegany & Garrett counties", bag="2/day, 2/season", notes="Trappers must submit the whole, skinned carcass of any river otter taken in Allegany/Garrett to the Western Regional Office.")
season(G, "Raccoon & Opossum", "Chase-Only (no kill)", "2026-08-01", "2026-10-14", bag="0")
season(G, "Raccoon & Opossum", "Chase-Only (no kill)", "2027-03-16", "2027-07-31", bag="0")
season(G, "Raccoon & Opossum", "Hunting (Firearms/Archery/Air Gun/Dogs)", "2026-10-15", "2027-03-15", bag="No limit", notes="Day and night, all counties.")
season(G, "Raccoon, Skunk & Opossum", "Trapping", "2026-11-14", "2027-03-15", zone="East of the Chesapeake Bay & Susquehanna River", bag="No limit")
season(G, "Raccoon, Skunk & Opossum", "Trapping", "2026-10-31", "2027-03-15", zone="West of the Chesapeake Bay & Susquehanna River", bag="No limit")
season(G, "Skunk", "Hunting (Firearms/Archery/Air Gun)", "2026-10-31", "2027-03-15", bag="No limit")
season(G, "Woodchuck", "No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="Unprotected species — no hunting license or furbearer permit required, but hunter orange is required. Hunting allowed on Sundays too.")
season(G, "Nutria", "Closed — Eradicated", "2026-07-01", "2027-06-30", bag="0", notes="Considered eradicated within Maryland.")

note(G, "Furbearer Permit Required", "A Furbearer Permit is required to hunt, chase, or trap any furbearer (coyote, fisher, gray fox, red fox, opossum, raccoon, skunk, beaver, mink, muskrat, river otter — bobcat may not be taken at all). Trapping specifically also requires a Certificate of Trapper Education (waived for apprentice-license holders or pre-Aug.2007 permit holders).")
note(G, "Species That May Only Be Trapped", "Beaver, long-tailed weasel, mink, muskrat, and river otter may NOT be shot/hunted — trapping only.")
note(G, "Gray Fox Registration", "Within 48 hours of harvesting a gray fox (hunting or trapping), you must register it via MD Outdoors, the MD Outdoors app, or by calling 410-260-8900.")
note(G, "Local Fox Rules", "In Charles & Dorchester counties, fox may be hunted/trapped/possessed year-round. In Cecil, Harford, Kent & Wicomico counties, it's illegal to kill a fox being pursued by dogs. Fox hunting with dogs is banned during the Deer Firearms Season (except unarmed chasing).")
note(G, "Sunday Furbearer Hunting", f"Coyote, fisher, fox, opossum, raccoon, and skunk may be hunted on Sundays only in specific counties with restrictions. {SUNDAY_CAVEAT.replace('this species', 'furbearers')}")

# ============================== MIGRATORY BIRDS ==============================
season("Migratory Birds", "September Teal", "Special Season", "2026-09-17", "2026-09-26", zone="Special Teal Zone (Eastern Shore counties + parts of Anne Arundel/Prince George's/Charles)", bag="6/day, 18 possession")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-10-10", "2026-10-17", zone="Eastern Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-11-14", "2026-11-27", zone="Eastern Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-12-15", "2027-01-30", zone="Eastern Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Black Duck", "Regular Season", "2026-11-14", "2026-11-27", zone="Eastern Duck Zone", bag="2/day (part of the 6-duck limit)")
season("Migratory Birds", "Black Duck", "Regular Season", "2026-12-15", "2027-01-30", zone="Eastern Duck Zone", bag="2/day (part of the 6-duck limit)")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-10-03", "2026-10-17", zone="Western Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-11-21", "2026-11-27", zone="Western Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Ducks & Coots", "Regular Season", "2026-12-15", "2027-01-30", zone="Western Duck Zone", bag="6 ducks + 15 coots/day, 18 duck possession")
season("Migratory Birds", "Black Duck", "Regular Season", "2026-11-21", "2026-11-27", zone="Western Duck Zone", bag="2/day (part of the 6-duck limit)")
season("Migratory Birds", "Black Duck", "Regular Season", "2026-12-15", "2027-01-30", zone="Western Duck Zone", bag="2/day (part of the 6-duck limit)")
season("Migratory Birds", "Sea Ducks (Scoter/Long-tailed/Eider)", "Regular Season", "2026-10-03", "2027-01-30", zone="Anywhere in MD (within the regular duck bag limit)", bag="Up to 4/day as part of the 6-duck limit")
season("Migratory Birds", "Youth/Veteran/Military Waterfowl Days", "Special Hunt", "2026-11-07", "2026-11-07", bag="Same species limits as regular season, e.g. 6 ducks/1 brant/2-5 Canada geese/15 coots/25 light geese")
season("Migratory Birds", "Youth/Veteran/Military Waterfowl Days", "Special Hunt", "2027-02-06", "2027-02-06", bag="Same species limits as regular season")
season("Migratory Birds", "Atlantic Brant", "Regular Season", "2026-12-28", "2027-01-30", bag="1/day, 3 possession")
season("Migratory Birds", "Canada Goose (Resident, Early)", "September Season", "2026-09-01", "2026-09-15", zone="Eastern Zone", bag="8/day, 24 possession")
season("Migratory Birds", "Canada Goose (Resident, Early)", "September Season", "2026-09-01", "2026-09-25", zone="Western Zone", bag="8/day, 24 possession")
season("Migratory Birds", "Canada Goose (Migratory, Atlantic Population)", "Regular Season", "2026-11-24", "2026-11-27", zone="Atlantic Population Hunt Zone", bag="2/day, 6 possession")
season("Migratory Birds", "Canada Goose (Migratory, Atlantic Population)", "Regular Season", "2026-12-15", "2027-01-30", zone="Atlantic Population Hunt Zone", bag="2/day, 6 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Southern MD)", "Regular Season", "2026-11-21", "2026-11-23", zone="Late Resident Southern Maryland Zone", bag="5/day, 15 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Southern MD)", "Regular Season", "2026-11-24", "2026-11-27", zone="Late Resident Southern Maryland Zone", bag="2/day, 6 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Southern MD)", "Regular Season", "2026-12-15", "2027-01-30", zone="Late Resident Southern Maryland Zone", bag="2/day, 6 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Southern MD)", "Regular Season", "2027-02-01", "2027-03-10", zone="Late Resident Southern Maryland Zone", bag="5/day, 15 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Western MD)", "Regular Season", "2026-11-21", "2026-11-27", zone="Late Resident Western Maryland Zone", bag="5/day, 15 possession")
season("Migratory Birds", "Canada Goose (Resident, Late — Western MD)", "Regular Season", "2026-12-15", "2027-03-10", zone="Late Resident Western Maryland Zone", bag="5/day, 15 possession")
season("Migratory Birds", "Light Goose (Snow/Ross's)", "Regular Season", "2026-11-07", "2026-11-27", zone="Statewide", bag="25/day, no possession limit")
season("Migratory Birds", "Light Goose (Snow/Ross's)", "Regular Season", "2026-11-30", "2027-02-06", zone="Statewide", bag="25/day, no possession limit")
season("Migratory Birds", "Light Goose (Snow/Ross's)", "Regular Season", "2027-02-08", "2027-03-10", zone="Eastern Zone only", bag="25/day, no possession limit")
season("Migratory Birds", "Light Goose", "Conservation Order", "2026-09-01", "2027-08-31", zone="Most counties (Sea Duck Zone excluded)", bag="No limit", notes="Exact dates TBD — check MD DNR's website in fall 2026. Requires a $5 Snow Goose Conservation Order Permit.")
season("Migratory Birds", "Mourning Dove", "Regular Season", "2026-09-01", "2026-10-17", bag="15/day, 45 possession", notes="Shooting hours noon-sunset for this segment only.")
season("Migratory Birds", "Mourning Dove", "Regular Season", "2026-10-24", "2026-11-27", bag="15/day, 45 possession")
season("Migratory Birds", "Mourning Dove", "Regular Season", "2026-12-19", "2027-01-09", bag="15/day, 45 possession")
season("Migratory Birds", "American Woodcock", "Regular Season", "2026-10-24", "2026-11-27", bag="3/day, 9 possession")
season("Migratory Birds", "American Woodcock", "Regular Season", "2027-01-11", "2027-01-27", bag="3/day, 9 possession")
season("Migratory Birds", "Clapper & King Rail", "Regular Season", "2026-09-01", "2026-11-20", bag="10/day (max 1 king), 30 possession (max 3 king)")
season("Migratory Birds", "Sora & Virginia Rail", "Regular Season", "2026-09-01", "2026-11-20", bag="25/day, 75 possession")
season("Migratory Birds", "Common Snipe", "Regular Season", "2026-09-26", "2027-01-28", bag="8/day, 24 possession")
season("Migratory Birds", "Mourning Dove (Falconry)", "Extended Falconry Season", "2027-01-09", "2027-01-28", bag="3/day, 9 possession")
season("Migratory Birds", "Rails (Falconry)", "Extended Falconry Season", "2026-11-20", "2027-01-01", bag="3/day, 9 possession")
season("Migratory Birds", "Woodcock (Falconry)", "Extended Falconry Season", "2026-10-01", "2026-10-24", bag="3/day, 9 possession")
season("Migratory Birds", "Woodcock (Falconry)", "Extended Falconry Season", "2027-02-01", "2027-03-10", bag="3/day, 9 possession")
season("Migratory Birds", "Ducks (Falconry)", "Extended Falconry Season", "2027-02-01", "2027-03-10", bag="3/day, 9 possession")
season("Migratory Birds", "Brant (Falconry)", "Extended Falconry Season", "2027-02-02", "2027-03-10", bag="3/day, 9 possession")

note("Migratory Birds", "No Sunday Migratory Bird Hunting", "Unlike deer/turkey/small game, migratory game birds may NEVER be hunted on Sundays in Maryland — no county exceptions.")
note("Migratory Birds", "No Open Season for Some Species", "There is no open season in Maryland for gallinules, harlequin ducks, moorhens, or swans (of any kind).")
note("Migratory Birds", "License Requirements", "All migratory bird hunters need: a hunting license (with exceptions), a Maryland Migratory Game Bird Stamp (free printed validation), and HIP certification. Waterfowl hunters 16+ also need a Federal Duck Stamp/E-Stamp. No physical federal stamp needs to be carried anymore if bought as an E-Stamp.")
note("Migratory Birds", "No Special Sea Duck Zone/Season", "Maryland's Sea Duck Zone still exists geographically, but sea ducks (scoters, long-tails, eiders) now share the same season dates and are part of the same 6-duck daily bag limit as the regular duck season — there's no separate sea-duck-only season anymore.")

db.commit()

for gt in ["Deer", "Black Bear", "Turkey", "Small Game", "Migratory Birds", "Trapping"]:
    n_seasons = db.query(HuntingSeasonEntry).filter(HuntingSeasonEntry.state_id == state.id, HuntingSeasonEntry.game_type == gt).count()
    n_notes = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type == gt).count()
    print(f"{gt}: {n_seasons} season entries, {n_notes} notes")

db.close()
print("Done.")
