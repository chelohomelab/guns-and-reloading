"""Seed Delaware 2026-27 hunting data, hand-extracted from DNREC's 2026/2027
Delaware Hunting and Trapping Guide (static/temp/Delaware-hunting-26-27.pdf).
Delaware's seasons are almost entirely statewide — much simpler than NJ/PA/NY/VA.
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from database import SessionLocal, HuntingState, HuntingSeasonEntry, HuntingRegulationNote

db = SessionLocal()
existing = db.query(HuntingState).filter(HuntingState.name == "Delaware").first()
if existing:
    db.delete(existing)
    db.commit()

state = HuntingState(name="Delaware", abbreviation="DE", display_order=5)
db.add(state)
db.commit()
db.refresh(state)

YEAR = "2026-27"
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
season(G, "Deer", "Archery", "2026-09-01", "2027-01-31", weapon="Bow", notes="Requires 400 sq. in. hunter orange when it's also legal to hunt deer with a firearm/muzzleloader.")
season(G, "Deer", "Crossbow", "2026-09-01", "2027-01-31", weapon="Crossbow", notes="Requires 400 sq. in. hunter orange when it's also legal to hunt deer with a firearm/muzzleloader.")
season(G, "Deer", "Muzzleloader", "2026-10-09", "2026-10-18", weapon="Muzzleloader")
season(G, "Deer", "Muzzleloader", "2027-01-25", "2027-01-31", weapon="Muzzleloader")
season(G, "Deer", "General Firearm", "2026-11-13", "2026-11-22", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery")
season(G, "Deer", "General Firearm", "2027-01-16", "2027-01-24", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery")
season(G, "Deer", "Special Antlerless", "2026-10-02", "2026-10-04", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery", bag="Antlerless only (bow/crossbow may still take antlered)")
season(G, "Deer", "Special Antlerless", "2026-10-23", "2026-10-25", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery", bag="Antlerless only (bow/crossbow may still take antlered)")
season(G, "Deer", "Special Antlerless", "2026-10-30", "2026-10-31", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery", bag="Antlerless only (bow/crossbow may still take antlered)")
season(G, "Deer", "Special Antlerless", "2026-12-12", "2026-12-20", weapon="Shotgun/Muzzleloader/Handgun/Straight-Walled Pistol-Caliber Rifle/Archery", bag="Antlerless only (bow/crossbow may still take antlered)")
season(G, "Deer", "Handgun & Straight-Walled Pistol-Caliber Rifle", "2027-01-02", "2027-01-10", weapon="Handgun/Straight-Walled Pistol-Caliber Rifle", zone="Statewide except WMZ 1A & 1B (closed)")
season(G, "Deer", "Youth & Non-Ambulatory Hunt", "2026-09-26", "2026-09-27", weapon="Bow/Muzzleloader/Shotgun/Handgun/Straight-Walled Pistol-Caliber Rifle")
season(G, "Deer", "Youth & Non-Ambulatory Hunt", "2026-11-07", "2026-11-08", weapon="Bow/Muzzleloader/Shotgun/Handgun/Straight-Walled Pistol-Caliber Rifle")

note(G, "Bag Limit", "Only 2 antlered deer per license year (July 1-June 30) across ALL methods/seasons combined. No limit on antlerless deer as long as you have an antlerless tag in possession before taking each additional one.")
note(G, "Hunter Orange", "400 sq. in. of hunter orange on head/chest/back is required during firearm seasons, and for archery/crossbow hunters when a firearm/muzzleloader season is concurrently open.")

# ============================== SMALL GAME ==============================
G = "Small Game"
season(G, "Gray Squirrel", "Regular Season", "2026-09-15", "2027-02-28", bag="6/day, 12 possession", notes="Closed during the Nov. General Firearm Deer season. South of the C&D Canal: shotguns, .17-.22 rimfire, .17 pellet, and muzzleloaders up to .36 cal. North of the C&D Canal: shotguns only. When overlapping a deer firearms season, wear 400 sq in hunter orange.")
season(G, "Delmarva Fox Squirrel", "Closed — Endangered Species", "2026-09-15", "2027-02-28", bag="0", notes="Fox squirrels may NOT be taken even with a valid hunting license — they're on the state Endangered Species list. Only gray squirrels are legal. Look closely before shooting.")
season(G, "Cottontail Rabbit", "Regular Season", "2026-11-23", "2027-02-28", bag="4/day, 8 possession", notes="Shotguns, compound/recurve/longbow. 400 sq in hunter orange required when hunting during any deer firearms season.")
season(G, "Groundhog", "No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="Unprotected species — longbow, crossbow, shotgun, muzzleloader, handgun, rimfire/centerfire rifle all legal. No hunting license required to hunt groundhogs.")
season(G, "Ring-Necked Pheasant", "Regular Season", "2026-11-23", "2027-02-28", bag="2/day, 4 possession (males only)", notes="Shotguns and longbows. 400 sq in hunter orange required when hunting during any deer firearms season.")
season(G, "Bobwhite Quail", "Closed — Wild Quail", "2026-11-23", "2027-02-28", bag="No limit", notes="Wild quail hunting is unlawful. Only pen-raised, released birds may be hunted, and only under a Division permit.")
season(G, "Bullfrog / Green Frog", "Regular Season", "2026-05-01", "2026-09-30", bag="24/day, 48 possession (aggregate)", notes="Valid hunting or fishing license required. Hand, hook, spear, or gig permitted.")
season(G, "Snapping Turtle", "Regular Season", "2026-06-15", "2027-05-15", bag="No limit", notes="11\" minimum shell length. Free Snapping Turtle Permit Number required at trapping license purchase. Mandatory harvest report due by July 30.")
season(G, "Diamondback Terrapin", "Closed", "2026-09-01", "2027-08-31", bag="0")

note(G, "Hunting Hours", "Upland game (except raccoon, opossum, and frogs): 1/2 hr before sunrise to 1/2 hr after sunset. Raccoons, opossums, and frogs may be hunted at night.")
note(G, "Possession Limit Rule", "No one may possess more than 2x the daily bag limit at any one time. Game already processed/stored for consumption at your permanent residence doesn't count against the possession limit.")

# ============================== TURKEY ==============================
G = "Turkey"
season(G, "Wild Turkey", "Spring Season", "2027-04-10", "2027-05-09", bag="1 bearded bird per season")
season(G, "Wild Turkey", "Youth & Non-Ambulatory Hunt", "2027-04-03", "2027-04-04", bag="1 bearded bird per season (counts toward season limit)", notes="Hunting hours 1/2 hr before sunrise to 1pm.")

note(G, "No Fall Season", "Delaware does not have a fall wild turkey season — spring is the only turkey hunting opportunity.")
note(G, "Mandatory Hunter Education", "All first-time DE turkey hunters age 13+ must complete a Division-approved turkey education course before hunting, on both public and private land. Public-land hunters must also complete it before applying for a public-land permit.")
note(G, "Legal Weapons", "Shotguns (10/12/16/20/28/.410 ga, including muzzleloading smoothbore, shot #4 or smaller, all shot types incl. TSS legal) and longbow/compound/crossbow (min. 7/8\" broadhead width). No rifles or handguns for turkey.")
note(G, "Public Land Permits", "A permit is required to hunt turkey on State Wildlife Areas, National Wildlife Refuges, or State Forest land — apply via lottery, one permit per hunter per season across all three land types combined.")

# ============================== MIGRATORY BIRDS ==============================
G = "Migratory Birds"
season(G, "Ducks", "Regular Season", "2026-10-31", "2026-11-07", bag="6/day, 18 possession")
season(G, "Ducks", "Regular Season", "2026-11-25", "2026-11-29", bag="6/day, 18 possession")
season(G, "Ducks", "Regular Season", "2026-12-16", "2027-01-31", bag="6/day, 18 possession")
season(G, "September Teal", "Regular Season", "2026-09-05", "2026-09-13", zone="Special Teal Zone (south of C&D Canal, north of Rt. 9 in Lewes, east of Rts. 13/113/113A/1)", bag="6/day, 18 possession")
season(G, "Coots", "Regular Season", "2026-10-31", "2026-11-07", bag="15/day, 45 possession")
season(G, "Coots", "Regular Season", "2026-11-25", "2026-11-29", bag="15/day, 45 possession")
season(G, "Coots", "Regular Season", "2026-12-16", "2027-01-31", bag="15/day, 45 possession")
season(G, "Mergansers", "Regular Season", "2026-10-31", "2026-11-07", bag="5/day, 15 possession")
season(G, "Mergansers", "Regular Season", "2026-11-25", "2026-11-29", bag="5/day, 15 possession")
season(G, "Mergansers", "Regular Season", "2026-12-16", "2027-01-31", bag="5/day, 15 possession")
season(G, "Youth/Veteran/Active Military Waterfowl Hunt", "Special Hunt", "2026-10-24", "2026-10-24", bag="Same as each species' regular-season limit", notes="Youth must be under 16.")
season(G, "Youth/Veteran/Active Military Waterfowl Hunt", "Special Hunt", "2027-02-07", "2027-02-07", bag="Same as each species' regular-season limit")
season(G, "Canada Goose (Resident)", "Outside Sept. Teal Zone", "2026-09-01", "2026-09-25", bag="15/day, 45 possession")
season(G, "Canada Goose (Resident)", "Inside Sept. Teal Zone", "2026-09-01", "2026-09-13", bag="15/day, 15 possession", zone="Special Teal Zone")
season(G, "Canada Goose (Resident)", "Inside Sept. Teal Zone", "2026-09-14", "2026-09-25", bag="15/day, 15 possession", zone="Special Teal Zone")
season(G, "Canada Goose (Migratory, incl. White-Fronted)", "Regular Season", "2026-11-25", "2026-11-29", bag="2/day, 6 possession")
season(G, "Canada Goose (Migratory, incl. White-Fronted)", "Regular Season", "2026-12-23", "2027-01-31", bag="2/day, 6 possession")
season(G, "Atlantic Brant", "Regular Season", "2026-12-19", "2027-01-02", bag="1/day, 3 possession")
season(G, "Atlantic Brant", "Regular Season", "2027-01-16", "2027-01-30", bag="1/day, 3 possession")
season(G, "Snow Goose (incl. Ross's)", "Regular Season", "2026-11-25", "2027-01-31", bag="25/day, no possession limit")
season(G, "Snow Goose (incl. Ross's)", "Regular Season", "2027-02-01", "2027-02-06", bag="25/day, no possession limit")
season(G, "Snow Goose (incl. Ross's)", "Regular Season", "2027-02-08", "2027-03-10", bag="25/day, no possession limit")
season(G, "Snow Goose", "Conservation Order", "2026-11-25", "2027-03-10", bag="No limit", notes="Only when the regular season is open and no other waterfowl seasons are open. Requires free annual online registration. Potentially suspended — check dnrec.delaware.gov after July 2026.")
season(G, "Tundra Swan", "Permit Hunt", "2026-11-08", "2027-01-31", bag="1 per season", notes="By special permit ONLY.")
season(G, "Mute Swan", "Any Open Waterfowl Season", "2026-09-01", "2027-03-10", bag="No limit", notes="Closed during the Snow Goose Conservation Order.")
season(G, "Trumpeter Swan", "Closed", "2026-09-01", "2027-08-31", bag="0")
season(G, "Mourning Dove", "Regular Season", "2026-09-01", "2026-09-27", bag="15/day, 45 possession", notes="September hunters on State Wildlife Areas must use non-toxic shot.")
season(G, "Mourning Dove", "Regular Season", "2026-11-23", "2026-11-29", bag="15/day, 45 possession")
season(G, "Mourning Dove", "Regular Season", "2026-12-07", "2027-01-31", bag="15/day, 45 possession")
season(G, "King & Clapper Rail", "Regular Season", "2026-09-01", "2026-11-09", bag="10/day, 30 possession (singly or aggregate)")
season(G, "Sora & Virginia Rail", "Regular Season", "2026-09-01", "2026-11-09", bag="25/day, 75 possession (singly or aggregate)")
season(G, "American Woodcock", "Regular Season", "2026-11-23", "2026-12-06", bag="3/day, 9 possession")
season(G, "American Woodcock", "Regular Season", "2026-12-25", "2027-01-24", bag="3/day, 9 possession")
season(G, "Common Snipe", "Regular Season", "2026-09-29", "2026-12-06", bag="8/day, 24 possession")
season(G, "Common Snipe", "Regular Season", "2026-12-25", "2027-01-31", bag="8/day, 24 possession")
season(G, "Moorhen & Gallinule", "Regular Season", "2026-09-01", "2026-11-09", bag="15/day, 45 possession")
season(G, "Crow", "Regular Season", "2026-07-03", "2027-03-26", bag="No limit", weekday="Friday", notes="Hunting only Fri/Sat/Sun. This entry marks Fridays; also legal Sat/Sun. Also open Jun.24-27, 2027.")

note(G, "Bag Limit Details — Ducks", "The 6-duck daily limit (excluding mergansers/coots) may include up to: 4 mallards (2 hens), 2 black ducks, 3 pintail, 2 canvasback, 3 wood ducks, 2 redheads, 1 scaup (2/day Jan.12-31), 6 teal/shovelers/gadwall/wigeon/goldeneye/ring-necked/bufflehead/ruddy ducks, 1 mottled duck, 1 fulvous whistling-duck, or 4 total sea ducks (max 3 scoters, 3 eiders [1 hen], 3 long-tailed ducks). Possession limit is 3x daily. Harlequin ducks remain closed. Sea ducks now share the same season/limits as regular ducks — there's no separate sea duck zone/season anymore.")
note(G, "License Requirements", "Same core migratory-bird license requirements as other states apply (HIP registration, federal duck stamp for 16+) — Sunday hunting is now permitted for all gamebirds including turkey and migratory birds in Delaware.")
note(G, "Crippled Waterfowl From a Boat", "Shooting crippled waterfowl from a motorboat under power is allowed in the area at least 800 yards seaward from the Delaware Bay or Atlantic Ocean shore, between the Port Mahon/Elbow Cross Navigation Light line and the Delaware-Maryland line.")

# ============================== TRAPPING (Furbearer Hunting + Trapping) ==============================
G = "Trapping"
season(G, "Muskrat, Mink & River Otter", "Trapping", "2026-12-01", "2027-03-10", bag="No limit", notes="In New Castle County, on embanked meadows, the season may run through Mar. 20. Season may be extended if Feb. weather criteria are met (see DNREC).")
season(G, "Raccoon, Opossum & Nutria", "Trapping", "2026-12-01", "2027-03-10", bag="No limit")
season(G, "Beaver", "Trapping", "2026-12-01", "2027-03-20", bag="No limit")
season(G, "Red Fox & Coyote", "Trapping", "2026-11-01", "2027-03-10", bag="No limit")
season(G, "Groundhog", "Trapping — No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="No trapping license required to trap groundhogs.")
season(G, "Raccoon", "Hunting", "2026-11-01", "2027-02-28", bag="No limit", notes="Special zone exists where raccoon season is open all year, including during deer seasons — see DNREC for the zone boundary.")
season(G, "Raccoon", "Chase-Only (no harvest)", "2026-08-01", "2026-10-31", bag="0", notes="Chase only, closed during the Oct. muzzleloader deer season.")
season(G, "Opossum", "Hunting", "2026-11-01", "2027-02-28", bag="No limit")
season(G, "Opossum", "Chase-Only (no harvest)", "2027-03-01", "2027-03-31", bag="0")
season(G, "Red Fox", "Hunting", "2026-11-01", "2027-02-28", bag="No limit", notes="Legal with compound/recurve/longbow/crossbow/shotgun/muzzleloading rifle/rimfire/centerfire rifle up to .25 cal. NOT legal with handguns or straight-walled pistol-caliber rifles.")
season(G, "Red Fox", "Chase-Only (no harvest)", "2026-10-01", "2027-04-30", bag="0", notes="Closed during deer shotgun, muzzleloader, and antlerless seasons Oct.-Dec. On private land only Tue/Wed/Thu during Jan. deer seasons, with landowner authorization.")
season(G, "Coyote", "Hunting — No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="Legal with compound/recurve/longbow/crossbow/shotgun/muzzleloading rifle/rimfire/centerfire rifle up to .25 cal. NOT legal with handguns or straight-walled pistol-caliber rifles.")
season(G, "Beaver", "Hunting", "2026-12-01", "2027-03-20", bag="No limit", notes="Legal with shotgun, compound, recurve, or longbow.")

note(G, "Dispatching Trapped Animals", "A .17-.22 rimfire firearm may be used to dispatch furbearers caught in a trap. There is no daily or possession limit for legally trapped furbearers.")
note(G, "Trap Tending & Marking", "Traps (except those for muskrat) must be tagged with the trapper's license number or name/address. Traps must be visited at least once every 24 hours (except muskrat traps). Written landowner permission is required to set traps on private property.")
note(G, "Nighttime & Electronic Calls", "Only raccoons and opossums may be hunted at night with the aid of a light. Electronic calls may be used to hunt raccoons, opossums, red fox, and coyotes.")
note(G, "Foothold Trap & Cable Restraint Specs", "Foothold traps: max 6.5\" jaw spread above the waterline, 7.75\" below; jaws above the waterline need padding/offset or minimum 5/16\" thickness (narrow exception for small coil/long-spring traps); no toothed/serrated jaws. Cable restraints (snares) must be stranded steel cable, min. 5/64\" diameter, with specific additional requirements — see DNREC's full trapping regulations.")

db.commit()

for gt in ["Deer", "Small Game", "Turkey", "Migratory Birds", "Trapping"]:
    n_seasons = db.query(HuntingSeasonEntry).filter(HuntingSeasonEntry.state_id == state.id, HuntingSeasonEntry.game_type == gt).count()
    n_notes = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type == gt).count()
    print(f"{gt}: {n_seasons} season entries, {n_notes} notes")

db.close()
print("Done.")
