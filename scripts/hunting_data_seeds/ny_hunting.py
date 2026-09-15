"""Seed New York 2026-27 hunting data, hand-extracted from the NY DEC's complete
84-page 2026-27 Hunting & Trapping Guide.

Run once per deployment: `.venv/bin/python scripts/hunting_data_seeds/ny_hunting.py`
(re-runnable — wipes and re-inserts New York's rows each time)."""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from database import SessionLocal, HuntingState, HuntingSeasonEntry, HuntingRegulationNote  # noqa: E402

db = SessionLocal()

existing = db.query(HuntingState).filter(HuntingState.name == "New York").first()
if existing:
    db.delete(existing)
    db.commit()

state = HuntingState(name="New York", abbreviation="NY", display_order=2)
db.add(state)
db.commit()
db.refresh(state)

YEAR = "2026-27"
MAP_CAVEAT = "Zone boundaries for this table are shown only as a colored WMU map graphic in the source PDF, not as extractable text — cross-check your WMU at dec.ny.gov before hunting/trapping."

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
# Northern Zone
season(G, "Deer", "Early Bowhunting", "2026-09-27", "2026-10-23", weapon="Bow", zone="Northern Zone (all WMUs)")
season(G, "Deer", "Regular Firearms", "2026-10-24", "2026-12-06", weapon="Firearms", zone="Northern Zone")
season(G, "Deer", "Late Bowhunting", "2026-12-07", "2026-12-13", weapon="Bow", zone="Northern Zone — WMUs 5A, 5G, 5J, 6A, 6C, 6G & 6H only")
season(G, "Deer", "Muzzleloader", "2026-10-17", "2026-10-23", weapon="Muzzleloader", zone="Northern Zone (most WMUs)", bag="Deer of either sex")
season(G, "Deer", "Muzzleloader — Late", "2026-12-07", "2026-12-13", weapon="Muzzleloader", zone="Northern Zone — WMUs 5A, 5G, 5J, 6A, 6C, 6G & 6H only", bag="Deer of either sex")
season(G, "Deer", "Muzzleloader", "2026-10-17", "2026-10-23", weapon="Muzzleloader", zone="Northern Zone — specific WMUs (check DEC season map, p.27)", bag="Antlered deer only", notes="The digest's season map shows some Northern Zone WMUs restricted to antlered-only during muzzleloader season, but the exact WMU list is only shown on the map graphic, not as text — verify your WMU at dec.ny.gov before hunting.")
# Southern Zone
season(G, "Deer", "Early Bowhunting", "2026-10-01", "2026-11-20", weapon="Bow", zone="Southern Zone")
season(G, "Deer", "Regular Firearms", "2026-11-21", "2026-12-13", weapon="Firearms", zone="Southern Zone")
season(G, "Deer", "Late Bowhunting", "2026-12-14", "2026-12-22", weapon="Bow", zone="Southern Zone")
season(G, "Deer", "Late Bowhunting", "2026-12-26", "2027-01-01", weapon="Bow", zone="Southern Zone")
season(G, "Deer", "Muzzleloader — Late", "2026-12-14", "2026-12-22", weapon="Muzzleloader", zone="Southern Zone", bag="Deer of either sex")
season(G, "Deer", "Muzzleloader — Late", "2026-12-26", "2027-01-01", weapon="Muzzleloader", zone="Southern Zone", bag="Deer of either sex")
# Westchester (3S)
season(G, "Deer", "Regular — Bowhunting Only", "2026-10-01", "2026-12-31", weapon="Bow", zone="Westchester County (WMU 3S)", notes="Regular firearms & muzzleloader deer hunting are CLOSED in Westchester County.")
# Suffolk (1C)
season(G, "Deer", "Early Antlerless Season", "2026-09-12", "2026-09-20", zone="Suffolk County (WMU 1C)", bag="Antlerless only", notes="Eligible tags: DMP and DMAP only.")
season(G, "Deer", "Regular — Bowhunting Only", "2026-10-01", "2027-01-31", weapon="Bow", zone="Suffolk County (WMU 1C)")
season(G, "Deer", "Special Firearms", "2027-01-03", "2027-01-31", weapon="Firearms", zone="Suffolk County (WMU 1C)", notes="Requires a special permit and a landowner's endorsement; may also need a town permit.")
# Youth
season(G, "Deer", "Youth Firearms Deer Season", "2026-10-10", "2026-10-12", weapon="Firearms", notes="See DEC's guide p.45 for full details/eligibility.")

note(G, "Legally Antlered Deer", "A legally antlered deer must have at least one antler 3\" or longer. Antlerless deer are does, fawns of either sex, and bucks with antlers under 3\".")
note(G, "Antler Point Restriction Program", "Mandatory in WMUs 3A, 3C, 3H, 3J, 3K, 4G, 4O, 4P, 4R, 4S & 4W: antlered bucks must have at least 1 antler with 3+ points, each ≥1\" long, to be legal. Hunters aged 12–16 are exempt and may take any buck with antlers 3\"+.")
note(G, "Bow & Crossbow", "Legal during both the bowhunting AND regular firearms seasons. A bowhunting/junior-bowhunting privilege is only required to hunt during the archery-only seasons — during regular season you just need proof of bowhunter-education eligibility. Barbed broadheads are illegal (blade-to-shaft angle under 90°, with a notch extending more than 2mm from the shaft counting as a barb). Mechanical-blade broadheads are legal only if the blades swing freely into a non-barbed position under gravity alone.")
note(G, "Muzzleloader Rules", "A muzzleloader privilege is required ONLY to hunt the dedicated Muzzleloader season — NOT needed to use a muzzleloader during the Regular firearms season or Long Island's January firearms season. Muzzleloaders may not be used at all in WMUs 3S (Westchester), 4J or 8C, and may only be used in WMU 1C (Suffolk) during the January firearms season.")
note(G, "Deer Management Permits (DMP)", "Needed to take an antlerless deer beyond your regular tag. Application deadline for limited-DMP WMUs: Oct. 1, 2026. $10 application fee (waived for juniors, junior bowhunters, and Lifetime License holders from before Oct. 1, 2009). Landowners (50+ acres in the WMU) and 40%+ disabled veterans get first-choice priority. DMPs are transferable to another hunter (see DEC's transfer procedure) but not resellable.")
note(G, "Earn-a-2nd-Buck", "Report a harvested antlerless deer on any valid antlerless tag (DMP, DMAP, early antlerless, etc.) and you're automatically issued a second Antlered Deer Tag, usable in any season with the right privileges — except the September antlerless season. DEC may ask for proof of the antlerless harvest (photo or head/skull, kept 7 days).")
note(G, "Tagging & Transport", "Tag the carcass immediately after harvest — physically for paper tags, or via the HuntFishNY app for e-tags. Deer/bear can be transported inside or outside a vehicle. Quartered meat must keep the carcass tag with it. If someone else transports your harvest, they need an extra hand-made tag with both your and their name/address/signature.")
note(G, "Suffolk & Westchester Counties", "Both counties run their own separate deer season structure instead of the Northern/Southern Zone seasons (see season entries above) — Westchester (WMU 3S) is bow-only, no firearms deer season at all; Suffolk (WMU 1C) is bow-only except a special-permit January firearms window. Hunting on State-managed land in either county requires its own DEC permit.")

# ============================== BLACK BEAR ==============================
G = "Black Bear"
season(G, "Black Bear", "Bowhunting", "2026-09-19", "2026-10-23", weapon="Bow", zone="Northern Zone")
season(G, "Black Bear", "Muzzleloading", "2026-10-17", "2026-10-23", weapon="Muzzleloader", zone="Northern Zone")
season(G, "Black Bear", "Regular Firearms", "2026-10-24", "2026-12-06", weapon="Firearms", zone="Northern Zone")
season(G, "Black Bear", "Early Firearms", "2026-09-12", "2026-09-27", weapon="Firearms", zone="Southern Zone")
season(G, "Black Bear", "Early Bowhunting", "2026-10-01", "2026-11-20", weapon="Bow", zone="Southern Zone")
season(G, "Black Bear", "Regular Firearms", "2026-11-21", "2026-12-13", weapon="Firearms", zone="Southern Zone")
season(G, "Black Bear", "Late Bowhunting", "2026-12-14", "2026-12-22", weapon="Bow", zone="Southern Zone")
season(G, "Black Bear", "Late Muzzleloading", "2026-12-14", "2026-12-22", weapon="Muzzleloader", zone="Southern Zone")
season(G, "Black Bear", "Regular — Bowhunting Only", "2026-10-01", "2026-12-31", weapon="Bow", zone="Westchester County (WMU 3S)", notes="Firearms/muzzleloader bear hunting is CLOSED in Westchester County.")
season(G, "Black Bear", "Youth Firearms Bear Season", "2026-10-10", "2026-10-12", weapon="Firearms", notes="See DEC's guide p.45 for full details/eligibility.")

note(G, "Bag Limit & Tag", "Resident and non-resident hunters both get a bear tag automatically with their hunting license — 1 bear per year.")
note(G, "Prohibited Methods", "No bait or dogs allowed for bear. In the Southern Zone specifically: may not shoot a cub or a bear that should be known to be a cub, shoot any bear out of a group of bears, or take a bear from its den. Up to 1.5 fl. oz. of liquid scent/lure is allowed, but not placed so it could be consumed as bait.")
note(G, "Harvest Reporting & Tooth Collection", "Bear harvests must be reported (same system as deer). NY's Bear Cooperator Program asks successful hunters to voluntarily submit a premolar tooth (DEC mails a collection packet) so DEC can age the bear — participants get a commemorative patch and a letter with their bear's age the following fall.")
note(G, "Allegany State Park", "Bear hunting inside Allegany State Park requires a separate park permit in addition to your bear tag.")

# ============================== SMALL GAME ==============================
G = "Small Game"
# Cottontail Rabbit — 3 unlabeled zones in source map
season(G, "Cottontail Rabbit", "Regular Season", "2026-10-01", "2027-03-21", bag="6", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Cottontail Rabbit", "Regular Season", "2026-10-01", "2027-02-28", bag="6", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Cottontail Rabbit", "Regular Season", "2026-11-01", "2027-02-28", bag="6", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
# Varying (Snowshoe) Hare
season(G, "Varying Hare (Snowshoe)", "Regular Season", "2026-10-01", "2027-03-21", bag="6", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Varying Hare (Snowshoe)", "Regular Season", "2026-12-14", "2027-02-28", bag="2", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Varying Hare (Snowshoe)", "Regular Season", "2027-01-01", "2027-01-31", bag="2", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Varying Hare (Snowshoe)", "Regular Season", "2026-10-01", "2027-03-21", bag="0", zone="Closed in this zone", notes="Not present/not huntable in this zone — no season.")
# Gray, Black & Fox Squirrel
season(G, "Gray/Black/Fox Squirrel", "Regular Season", "2026-09-01", "2027-02-28", bag="6 total, regardless of species", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Gray/Black/Fox Squirrel", "Regular Season", "2026-11-01", "2027-02-28", bag="6 total, regardless of species", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Red Squirrel", "No Closed Season", "2026-09-01", "2027-08-31", bag="No limit", notes="Unprotected species (like woodchuck, porcupine, chipmunk) — may be taken any time, no bag limit, but a hunting license is required to take it with a bow, crossbow, or firearm.")
season(G, "Woodchuck", "No Closed Season", "2026-09-01", "2027-08-31", bag="No limit", notes="Unprotected species — may be taken any time without limit; a hunting license is still required to take it with a bow, crossbow, or firearm.")

note(G, "Zone Maps Not Text-Extractable", f"Cottontail Rabbit, Varying Hare, and Squirrel season dates are all split by regional zones shown as a colored WMU map in this guide (not the same simple Northern/Southern Zone split as Deer). {MAP_CAVEAT} Rows here preserve every date/bag-limit combination from the source table so you can match yours once you know your zone.")
note(G, "Falconry", "Licensed falconers (Falconry License + hunting license) may take small game Oct. 1–Mar. 31 statewide, with common crow restricted to the open firearms crow season, and pheasant (either sex) legal anywhere in the state under a Falconry License. In WMU 2A, ALL pheasant hunting is by falconry only.")
note(G, "Air Guns & Crossbows", "Air guns may be used on squirrels, rabbits, hares, ruffed grouse, and huntable furbearers (raccoon, coyote, etc.) — NOT on waterfowl, pheasant, turkey, or big game. Crossbows may not be possessed afield in the Northern Zone when small-game hunting (except coyote) with or accompanied by a dog.")
note(G, "Dogs", "Dogs may be used for small game generally, except: not for spring wild turkey, and in the Northern Zone not while hunting small game (except coyote) with the aid of a dog or accompanied by a dog without a current dog-training/hunting exception. Training on raccoon/fox/coyote/bobcat: Jul.1–Apr.15. Training on other small game: Aug.15–Apr.15.")
note(G, "Rabbit Disease (RHDV2) Precautions", "Rabbit hemorrhagic disease virus 2 is highly lethal to rabbits/hares and very hardy on surfaces (3 months). Wear disposable gloves handling carcasses, dispose of them properly, disinfect gear after out-of-state travel, and don't bring rabbit/hare carcasses from other states into NY.")
note(G, "Protected Reptiles & Amphibians", "Only 2 reptile/amphibian hunting seasons exist: frogs (Jun.15–Sept.30, no limit, statewide except leopard frogs excluded from WMUs 1A/1C/2A) and snapping turtles (Jul.15–Sept.30, 12\"+ shell, 5/day, 30/season, statewide). All native snakes, lizards and salamanders are fully protected — no possession ever. No other turtle species may be taken.")

# ============================== UPLAND BIRDS ==============================
G = "Upland Birds"
season(G, "Ruffed Grouse", "Regular Season", "2026-09-20", "2027-02-28", bag="4", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Ruffed Grouse", "Regular Season", "2026-10-01", "2027-02-28", bag="4", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Ruffed Grouse", "Regular Season", "2026-09-20", "2027-02-28", bag="0", zone="Closed in this zone")
season(G, "Pheasant", "Regular Season", "2026-10-01", "2027-02-28", weapon="Shotgun/bow/crossbow (no rifle/handgun)", bag="2/day", zone=f"Zone (see DEC map) — {MAP_CAVEAT}", notes="Youth Hunt Sept. 26-27 in this zone.")
season(G, "Pheasant", "Regular Season", "2026-10-17", "2027-02-28", weapon="Shotgun/bow/crossbow (no rifle/handgun)", bag="2/day", zone=f"Zone (see DEC map) — {MAP_CAVEAT}", notes="Youth Hunt Oct. 10-11 in this zone.")
season(G, "Pheasant", "Regular Season", "2026-10-17", "2026-12-31", weapon="Shotgun/bow/crossbow (no rifle/handgun)", bag="2/day", zone=f"Zone (see DEC map) — {MAP_CAVEAT}", notes="Youth Hunt Oct. 10-11 in this zone.")
season(G, "Pheasant", "Regular Season", "2026-11-01", "2026-12-31", weapon="Shotgun/bow/crossbow (no rifle/handgun)", bag="2/day (4/day in some areas), season 30", zone=f"Zone (see DEC map) — {MAP_CAVEAT}", notes="Youth Hunt Oct. 24-25 in this zone. In WMU 2A hunting is by falconry only.")
season(G, "Bobwhite Quail", "Regular Season", "2026-10-01", "2027-02-28", bag="4/day, 10 possession", zone="Ulster, Sullivan, Dutchess, Orange, Putnam, Rockland, Westchester, New York, Bronx, Suffolk, Nassau, Kings, Richmond & Queens counties")
season(G, "Bobwhite Quail", "Regular Season", "2026-11-01", "2026-12-31", bag="6/day, 40 possession", zone="Ulster, Sullivan, Dutchess, Orange, Putnam, Rockland, Westchester, New York, Bronx, Suffolk, Nassau, Kings, Richmond & Queens counties")
season(G, "Bobwhite Quail", "Regular Season", "2026-10-01", "2027-02-28", bag="0", zone="Rest of the state", notes="No open quail season outside the listed downstate counties.")

# ============================== TURKEY ==============================
G = "Turkey"
season(G, "Wild Turkey", "Fall Season", "2026-10-01", "2026-10-14", bag="1 bird of either sex", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Wild Turkey", "Fall Season", "2026-10-17", "2026-10-30", bag="1 bird of either sex", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Wild Turkey", "Fall Season", "2026-11-21", "2026-12-04", bag="1 bird of either sex", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Wild Turkey", "Fall Season", "2026-10-01", "2026-10-14", bag="0", zone="Closed in this zone")
season(G, "Wild Turkey", "Spring Season", "2027-05-01", "2027-05-31", bag="2 bearded birds, max 1/day", zone="Statewide")
season(G, "Wild Turkey", "Spring Youth Hunt", "2027-04-24", "2027-04-25", bag="1 bearded bird (counts toward the 2-bird spring limit)", zone="Statewide (same open areas as regular spring season)")

note(G, "Permit & Tags", "You may buy only one turkey permit per year, which includes 3 carcass tags: 2 for spring, 1 for fall.")
note(G, "Legal Weapons", "Shotgun or handgun with shot no larger than #2, no smaller than #9. Muzzleloading shotgun allowed. Bow/crossbow allowed (crossbow: hunter 14+, and NOT legal for turkey in Westchester or Suffolk counties). No rifle, air gun, or a handgun firing a bullet.")
note(G, "Fall vs Spring Rules", "Fall: either-sex bird, dogs allowed, no bait, no electronic calls to locate/hunt turkeys (decoys OK, live decoys not OK). Spring: bearded birds only, max 2/season (1/day), NO dogs allowed.")
note(G, "Save-a-Leg (Fall)", "If you harvest a turkey in fall season, save one of its legs — you'll get instructions on how DEC wants it submitted for age-structure data.")

# ============================== MIGRATORY BIRDS ==============================
G = "Migratory Birds"
# Woodcock/Crow/Snipe/Rails/Gallinules — clean labeled table
season(G, "American Woodcock", "Regular Season", "2026-10-01", "2026-11-14", bag="3/day, 9 possession", zone="Upstate New York (north of the Bronx-Westchester line)", weekday="!Sunday")
season(G, "American Woodcock", "Regular Season", "2026-10-01", "2026-11-14", bag="3/day, 9 possession", zone="Long Island (WMUs 1A & 1C)", weekday="!Sunday")
season(G, "Common Crow", "Regular Season", "2026-09-01", "2027-03-31", bag="No limit", zone="Upstate New York (north of the Bronx-Westchester line)", weekday="!Sunday")
season(G, "Common Crow", "Regular Season", "2026-09-01", "2027-03-31", bag="No limit", zone="Long Island (WMUs 1A & 1C)", weekday="!Sunday")
season(G, "Wilson's Snipe", "Regular Season", "2026-09-01", "2026-11-09", bag="8/day, 24 possession", zone="Upstate New York (north of the Bronx-Westchester line)", weekday="!Sunday")
season(G, "Virginia & Sora Rail", "Regular Season", "2026-09-01", "2026-11-09", bag="8/day, 24 possession", zone="Upstate New York (north of the Bronx-Westchester line)", weekday="!Sunday")
season(G, "Gallinule (Moorhen)", "Regular Season", "2026-09-01", "2026-11-09", bag="8/day, 24 possession", zone="Upstate New York (north of the Bronx-Westchester line)", weekday="!Sunday")
season(G, "Clapper & King Rail", "Regular Season", "2026-09-01", "2026-11-09", bag="0", zone="Statewide", notes="Closed statewide — no open season for Clapper or King Rail.")

# Ducks/Coots/Scaup/Snow Geese/Brant per waterfowl zone
season(G, "Ducks & Coots", "Regular Season", "2026-10-10", "2026-11-29", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Northeast Zone", weekday="!Sunday")
season(G, "Ducks & Coots", "Regular Season", "2026-12-12", "2026-12-20", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Northeast Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-11-19", "2026-11-29", bag="2/day", zone="Northeast Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-12-12", "2026-12-20", bag="2/day", zone="Northeast Zone", weekday="!Sunday")
season(G, "Snow Geese", "Regular Season", "2026-10-01", "2026-12-31", bag="25/day", zone="Northeast Zone", weekday="!Sunday")
season(G, "Snow Geese", "Conservation Order", "2027-02-26", "2027-03-10", bag="25/day, no possession limit", zone="Northeast Zone", weekday="!Sunday", notes="Pending regulatory changes — verify at dec.ny.gov before hunting.")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-08", bag="1/day, 3 possession", zone="Northeast Zone", weekday="!Sunday")

season(G, "Ducks & Coots", "Regular Season", "2026-10-10", "2026-11-01", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Lake Champlain Zone", weekday="!Sunday")
season(G, "Ducks & Coots", "Regular Season", "2026-11-21", "2026-12-27", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Lake Champlain Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-12-08", "2026-12-27", bag="2/day", zone="Lake Champlain Zone", weekday="!Sunday")
season(G, "Snow Geese", "Regular Season", "2026-10-01", "2026-12-31", bag="25/day", zone="Lake Champlain Zone", weekday="!Sunday")
season(G, "Snow Geese", "Conservation Order", "2027-02-26", "2027-03-10", bag="25/day, no possession limit", zone="Lake Champlain Zone", weekday="!Sunday", notes="Pending regulatory changes; federal law requires the same dates as Vermont's Lake Champlain zone.")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-08", bag="1/day, 3 possession", zone="Lake Champlain Zone", weekday="!Sunday")

season(G, "Ducks & Coots", "Regular Season", "2026-10-10", "2026-11-01", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Western Zone", weekday="!Sunday")
season(G, "Ducks & Coots", "Regular Season", "2026-12-05", "2027-01-10", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Western Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-12-22", "2027-01-10", bag="2/day", zone="Western Zone", weekday="!Sunday")
season(G, "Snow Geese", "Regular Season", "2026-11-24", "2027-03-10", bag="25/day", zone="Western Zone", weekday="!Sunday")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-08", bag="1/day, 3 possession", zone="Western Zone", weekday="!Sunday")

season(G, "Ducks & Coots", "Regular Season", "2026-10-10", "2026-10-18", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Southeast Zone", weekday="!Sunday")
season(G, "Ducks & Coots", "Regular Season", "2026-11-07", "2026-12-27", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Southeast Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-12-08", "2026-12-27", bag="2/day", zone="Southeast Zone", weekday="!Sunday")
season(G, "Snow Geese", "Regular Season", "2026-11-24", "2027-03-10", bag="25/day", zone="Southeast Zone", weekday="!Sunday")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-08", bag="1/day, 3 possession", zone="Southeast Zone", weekday="!Sunday")

season(G, "Ducks & Coots", "Regular Season", "2026-11-07", "2026-11-08", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Long Island Zone", weekday="!Sunday", notes="Also Dec. 21-Jan. 19 (2nd segment).")
season(G, "Ducks & Coots", "Regular Season", "2026-12-21", "2027-01-19", bag="6 ducks/15 coots daily (see species sub-limits)", zone="Long Island Zone", weekday="!Sunday")
season(G, "Scaup", "Regular Season", "2026-12-21", "2027-01-19", bag="2/day", zone="Long Island Zone", weekday="!Sunday")
season(G, "Snow Geese", "Regular Season", "2026-11-24", "2027-03-10", bag="25/day", zone="Long Island Zone", weekday="!Sunday")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-08", bag="1/day, 3 possession", zone="Long Island Zone", weekday="!Sunday")

# Canada Goose (9 named goose hunting areas)
season(G, "Canada Goose", "Early Season", "2026-09-01", "2026-09-25", bag="15/day", zone="Northeast Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-10-24", "2026-11-29", bag="3/day", zone="Northeast Goose Hunting Area", weekday="!Sunday", notes="Also Dec. 12-Dec. 19 (2nd segment of the same 3/day regular season).")
season(G, "Canada Goose", "Regular Season", "2026-12-12", "2026-12-19", bag="3/day", zone="Northeast Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-11-07", "2026-12-21", bag="3/day", zone="West Central Goose Hunting Area", weekday="!Sunday", notes="No listed early Sept. season for this area in the source table — verify at dec.ny.gov.")
season(G, "Canada Goose", "Early Season", "2026-09-01", "2026-09-25", bag="15/day", zone="East Central Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-10-24", "2026-11-20", bag="3/day", zone="East Central Goose Hunting Area", weekday="!Sunday", notes="Also Dec. 5-Dec. 21 (2nd segment of the same 3/day regular season).")
season(G, "Canada Goose", "Regular Season", "2026-12-05", "2026-12-21", bag="3/day", zone="East Central Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Early Season", "2026-09-01", "2026-09-25", bag="15/day", zone="Hudson Valley Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-11-07", "2026-12-21", bag="3/day", zone="Hudson Valley Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Early Season", "2026-09-01", "2026-09-25", bag="15/day", zone="South Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-10-24", "2027-01-11", bag="5/day", zone="South Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-11-07", "2027-02-21", bag="8/day", zone="Western Long Island Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Early Season", "2026-09-08", "2026-09-30", bag="15/day", zone="Central Long Island Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-11-21", "2026-11-29", bag="3/day", zone="Central Long Island Goose Hunting Area", weekday="!Sunday", notes="Also Dec. 5-Feb. 3 (2nd segment of the same 3/day regular season).")
season(G, "Canada Goose", "Regular Season", "2026-12-05", "2027-02-03", bag="3/day", zone="Central Long Island Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Early Season", "2026-09-08", "2026-09-30", bag="15/day", zone="Eastern Long Island Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-11-21", "2026-11-29", bag="2/day", zone="Eastern Long Island Goose Hunting Area", weekday="!Sunday", notes="Also Dec. 5-Jan. 24 (2nd segment of the same 2/day regular season).")
season(G, "Canada Goose", "Regular Season", "2026-12-05", "2027-01-24", bag="2/day", zone="Eastern Long Island Goose Hunting Area", weekday="!Sunday")
season(G, "Canada Goose", "Regular Season", "2026-09-01", "2027-03-10", bag="0", zone="New York City Goose Hunting Area (WMU 2A)", notes="Closed entirely — no Canada goose season in NYC.")

note(G, "License Requirements", "All migratory bird hunters need a NYS hunting license + annual HIP (Harvest Information Program) registration. Waterfowl hunters 16+ also need a federal duck stamp (physical, signed in ink, or e-stamp). Duck stamp NOT required for coot, rails, gallinules, woodcock, or snipe, or for minors 12-15 hunting migratory waterfowl.")
note(G, "Mourning Dove Has No NY Season", "Mourning doves are federally classified as migratory game birds, but New York State has never established a hunting season for them — they cannot be legally hunted in NY at all, despite being legal in NJ/PA/DE/MD/VA.")
note(G, "Non-Toxic Shot", "Required for every migratory game bird EXCEPT woodcock, everywhere in NY. Only USFWS-approved non-toxic shot types are legal (steel, bismuth-tin, tungsten variants, etc.) for waterfowl, snipe, rails, and gallinules.")
note(G, "Hunting Hours", "Woodcock: sunrise to sunset. All other migratory birds: 1/2 hour before sunrise to sunset (Canada geese may run to 1/2 hr after sunset during the Sept. season when other waterfowl seasons are closed; snow geese similarly during the Jan.15-Apr.15 conservation-order window).")
note(G, "Bag Limit Details — Ducks", "The daily 6-duck limit includes all mergansers and sea ducks, with species sub-caps: max 4 mallards (2 hens), 3 wood ducks, 2 black ducks, 3 pintail, 1 scaup (2 during the specific higher-limit weeks listed per zone), 2 redheads, 2 canvasbacks, or 4 sea ducks (max 3 scoters/long-tails/eiders, max 1 female eider). No harlequin ducks may be taken. Possession limit is 3x the daily limit for all species except snow geese (no possession limit).")
note(G, "Canada Goose Zones", "NY splits Canada goose into 9 named 'Goose Hunting Areas' that mostly mirror the 5 waterfowl zones but split further downstate (Hudson Valley, South, and 3 Long Island sub-areas, plus NYC which is fully closed). Exact area boundaries are long road-based descriptions — check dec.ny.gov's zone-boundary page for your specific WMU/county before hunting.")

# ============================== TRAPPING ==============================
G = "Trapping"
# Furbearer HUNTING (not trapping) — bobcat, mink, muskrat, weasel/raccoon/fox, coyote
season(G, "Bobcat", "Hunting", "2026-10-25", "2027-02-15", bag="No limit", zone=f"Zone (see DEC map) — {MAP_CAVEAT}", notes="Hunting hours: after sunrise on opening day; any hour day or night the rest of the season. Must be tagged & sealed if taken.")
season(G, "Bobcat", "Hunting", "2026-10-25", "2026-11-20", bag="No limit", zone=f"Zone (see DEC map) — {MAP_CAVEAT}")
season(G, "Bobcat", "Hunting", "2026-10-25", "2027-02-15", bag="0", zone="Closed in this zone")
season(G, "Weasel, Raccoon & Fox", "Hunting", "2026-10-01", "2027-03-28", bag="No limit", zone="Statewide except Long Island & New York City", notes="Any hour day or night (except weasel, which is sunrise-to-sunset only).")
season(G, "Weasel, Raccoon & Fox", "Hunting", "2026-11-01", "2027-02-25", bag="No limit", zone="Long Island & New York City")
season(G, "Coyote", "Hunting", "2026-10-25", "2027-02-15", bag="No limit", zone="Statewide", notes="May be hunted day or night. Not from a motor vehicle, ATV, or snowmobile.")
season(G, "Mink", "Hunting (firearm ≤.22 cal only)", "2026-10-25", "2027-02-15", bag="No limit", zone="Southern Zone, during the open trapping season only", notes="Mink may NOT be hunted with a firearm in the Northern Zone.")
season(G, "Muskrat", "Hunting (firearm ≤.22 cal only)", "2026-10-25", "2027-02-15", bag="No limit", zone="Lake Champlain only, during the open trapping season only")

# TRAPPING proper
season(G, "Fisher & Marten", "Trapping", "2026-12-01", "2026-12-31", bag="Fisher & marten (season limit of 6 marten)", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Fisher & Marten", "Trapping", "2026-11-15", "2026-12-31", bag="Fisher only, no bag limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Fisher & Marten", "Trapping", "2026-11-26", "2026-12-10", bag="Fisher only, no bag limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Fisher & Marten", "Trapping", "2026-12-05", "2026-12-10", bag="Fisher only, no bag limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Fisher & Marten", "Trapping", "2026-12-01", "2026-12-31", bag="0", zone="Closed in this zone", notes="Fisher and marten trapping is closed in some areas of the Northern Zone (body-gripping traps there may not be set with bait/lure while the season is closed).")
season(G, "Mink & Muskrat", "Trapping", "2026-11-01", "2027-04-15", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Mink & Muskrat", "Trapping", "2026-11-10", "2027-04-07", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Bobcat", "Trapping", "2026-10-25", "2027-02-15", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}", notes="Must be tagged & sealed if taken.")
season(G, "Bobcat", "Trapping", "2026-10-25", "2026-11-20", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Bobcat", "Trapping", "2026-10-25", "2027-02-15", bag="0", zone="Closed in this zone")
season(G, "Beaver", "Trapping", "2026-11-01", "2027-04-07", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Beaver", "Trapping", "2026-11-10", "2027-04-07", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "Beaver", "Trapping", "2026-11-01", "2027-04-07", bag="0", zone="Closed in this zone")
season(G, "River Otter", "Trapping", "2026-11-01", "2027-04-07", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}", notes="Must be tagged & sealed if taken.")
season(G, "River Otter", "Trapping", "2026-11-10", "2027-02-28", bag="No limit", zone=f"Zone (see DEC trapping map) — {MAP_CAVEAT}")
season(G, "River Otter", "Trapping", "2026-11-01", "2027-04-07", bag="0", zone="Closed in this zone")

note(G, "Raccoon/Fox/Skunk/Opossum/Weasel Trapping Dates Not Extracted", "The trapping-season table for this species group (separate from their hunting dates above) had a PDF text-layout issue that made it unreadable during extraction — check dec.ny.gov or the guide's page 65 map directly before trapping these species; their dates are likely similar to, but not necessarily identical to, the hunting dates already seeded above.")
note(G, "Fisher/Marten Season Expanded This Year", "DEC recently surveyed over 7,000 trappers and expanded fisher trapping into more of central/western NY with later season dates to better align with peak pelt quality — if you trapped fisher in past years, don't assume last year's dates or zone still apply.")
note(G, "Bobcat Rules", "Bobcat may be hunted anywhere in the state with an open season, using a call (including electronic), bow, crossbow, or firearm. Any harvested bobcat must be tagged and sealed.")
note(G, "Furtaker License Required", "A trapping license is required to trap any furbearer. Hunting most furbearers (raccoon, fox, coyote, bobcat, etc.) can be done with a general hunting license instead — trapping-specific rules (body-gripping trap size/height/bait restrictions, tending requirements) only apply when trapping, not hunting.")
note(G, "Body-Gripping Trap Rules", "Traps under 5.5\" may be set any way. Traps 5.5\"-6\" without bait must sit under 8\" off the ground. Traps 5.5\"-7.5\" WITH bait/lure need one of: 4+ feet off the ground, OR a recessed/covered box/container meeting specific dimensions (see guide p.63-64 for exact specs). Traps over 6\" may never be set on land within 100 ft of a public trail (except on WMAs) without bait restrictions.")

# ============================== GENERAL / STATEWIDE ==============================
note(None, "Fluorescent Orange", "250 sq. in. of solid fluorescent orange OR pink worn above the waist, visible from all directions; OR patterned fluorescent orange/pink that's at least 50% fluorescent orange/pink by area, same coverage; OR a hat/cap that's at least 50% solid fluorescent orange or pink exterior.")
note(None, "Hunting Hours", "Both Deer and Bear seasons run 30 minutes before sunrise to 30 minutes after sunset statewide.")

db.commit()

for gt in ["Deer", "Black Bear", "Small Game", "Upland Birds", "Turkey", "Migratory Birds", "Trapping"]:
    n_seasons = db.query(HuntingSeasonEntry).filter(HuntingSeasonEntry.state_id == state.id, HuntingSeasonEntry.game_type == gt).count()
    n_notes = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type == gt).count()
    print(f"{gt}: {n_seasons} season entries, {n_notes} notes")
n_general = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type.is_(None)).count()
print(f"General: {n_general} notes")

db.close()
print("Done.")
