"""Seed New Jersey 2026-27 hunting data (Regulation Set High for deer), hand-extracted
from the NJ Fish & Wildlife 2026-27 Hunting & Trapping Digest.

Run once per deployment: `.venv/bin/python scripts/hunting_data_seeds/nj_hunting.py`
(re-runnable — wipes and re-inserts New Jersey's rows each time)."""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

import database as models  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402

init_db()
db = SessionLocal()

# Wipe any partial prior NJ data from this session so the script is re-runnable.
existing = db.query(models.HuntingState).filter(models.HuntingState.name == "New Jersey").first()
if existing:
    db.delete(existing)
    db.commit()

nj = models.HuntingState(name="New Jersey", abbreviation="NJ", display_order=0)
db.add(nj)
db.commit()
db.refresh(nj)

Y = "2026-27"

def season(game_type, season_label, start, end, weapon=None, species=None, zone=None,
           bag=None, notes=None, weekday=None, order=0):
    db.add(models.HuntingSeasonEntry(
        state_id=nj.id, season_year_label=Y, game_type=game_type, species=species,
        season_label=season_label, weapon=weapon, zone_or_area=zone,
        start_date=start, end_date=end, weekday_filter=weekday, bag_limit=bag, notes=notes,
        display_order=order,
    ))

def note(game_type, title, body, order=0):
    db.add(models.HuntingRegulationNote(state_id=nj.id, game_type=game_type, title=title, body=body, display_order=order))

# ============================== DEER (Regulation Set High) ==============================
RS = "Regulation Set High (zones 7,8,9,10,11,12,13,14,15,17,19,36,41,42,48,49,50,51)"

season("Deer", "Fall Bow", "2026-09-12", "2026-10-30", weapon="Bow", zone=RS,
       bag="Unlimited antlerless + 1 antlered (2 at a time)",
       notes="First deer must be antlerless Sep 12–Oct 2 (does not apply to youth license holders); either sex Oct 3–30.", order=1)
season("Deer", "Youth Archery Day", "2026-09-26", "2026-09-26", weapon="Bow", zone=RS,
       bag="1 deer, either sex", notes="Youth only (age 10–16); must be accompanied by a licensed, non-hunting adult 21+. Antler point restrictions and Earn-A-Buck do not apply.", order=2)
season("Deer", "Permit Bow", "2026-10-31", "2026-12-24", weapon="Bow", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)",
       notes="Requires zone-specific Antlerless Permit; Antlered Buck Permit must be purchased by Oct 31, 11:59pm to hunt bucks.", order=3)
season("Deer", "Permit Bow", "2026-12-26", "2026-12-31", weapon="Bow", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", order=3)
season("Deer", "Youth Firearm Day", "2026-11-21", "2026-11-21", weapon="Firearm", zone=RS,
       bag="1 deer, either sex", notes="Youth only; accompanied by licensed, non-hunting adult 21+. Rifle Permit required if using a muzzleloader.", order=4)
season("Deer", "Six-Day Firearm", "2026-12-07", "2026-12-12", weapon="Shotgun/Muzzleloader",
       bag="2 antlered bucks (only 1 at a time)",
       notes="Bow may also be used if hunter holds an All-Around license, or both Firearm AND Bow licenses. Bowhunters in tree stands are required to wear hunter orange this season.", weekday="!Sunday", order=5)
# Permit Muzzleloader (High) — precise antlerless-only vs either-sex windows, incl. the
# Nov 26 (Thanksgiving) and Dec 2-6 closures that a single date-range would silently hide.
season("Deer", "Permit Muzzleloader", "2026-11-23", "2026-11-25", weapon="Muzzleloader", zone=RS,
       bag="Antlerless only", notes="Requires a valid Rifle Permit.", weekday="!Sunday", order=6)
season("Deer", "Permit Muzzleloader", "2026-11-27", "2026-11-27", weapon="Muzzleloader", zone=RS,
       bag="Antlerless only", notes="Requires a valid Rifle Permit.", order=6)
season("Deer", "Permit Muzzleloader", "2026-11-30", "2026-12-01", weapon="Muzzleloader", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", notes="Requires a valid Rifle Permit.", order=6)
season("Deer", "Permit Muzzleloader", "2026-12-07", "2026-12-12", weapon="Muzzleloader", zone=RS,
       bag="Antlerless only", notes="Requires a valid Rifle Permit.", weekday="!Sunday", order=6)
season("Deer", "Permit Muzzleloader", "2026-12-14", "2026-12-24", weapon="Muzzleloader", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", notes="Requires a valid Rifle Permit.", weekday="!Sunday", order=6)
season("Deer", "Permit Muzzleloader", "2026-12-26", "2026-12-31", weapon="Muzzleloader", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", notes="Requires a valid Rifle Permit.", order=6)
season("Deer", "Permit Muzzleloader", "2027-01-01", "2027-02-20", weapon="Muzzleloader", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", notes="Requires a valid Rifle Permit.", weekday="!Sunday", order=6)
# Permit Shotgun (High) — same antlerless-only windows as Muzzleloader, but its either-sex
# window is narrower (Dec 14-18 only, then closed until Jan 1).
season("Deer", "Permit Shotgun", "2026-11-23", "2026-11-25", weapon="Shotgun", zone=RS,
       bag="Antlerless only", weekday="!Sunday", order=7)
season("Deer", "Permit Shotgun", "2026-11-27", "2026-11-27", weapon="Shotgun", zone=RS,
       bag="Antlerless only", order=7)
season("Deer", "Permit Shotgun", "2026-12-07", "2026-12-12", weapon="Shotgun", zone=RS,
       bag="Antlerless only", weekday="!Sunday", order=7)
season("Deer", "Permit Shotgun", "2026-12-14", "2026-12-18", weapon="Shotgun", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", weekday="!Sunday", order=7)
season("Deer", "Permit Shotgun", "2027-01-01", "2027-02-20", weapon="Shotgun", zone=RS,
       bag="Unlimited antlerless + 1 antlered w/ Buck Permit (2 at a time)", weekday="!Sunday", order=7)
season("Deer", "Winter Bow", "2027-01-01", "2027-02-20", weapon="Bow", zone=RS,
       bag="Unlimited antlerless + 1 antlered", order=8)
season("Deer", "Sunday exception", "2026-09-12", "2027-02-20", weapon="Crossbow ONLY",
       zone="Private land only", weekday="Sunday",
       notes="NJ prohibits firearm/muzzleloader/shotgun hunting on Sundays. Archery is the only legal method on Sundays, and only on private land (and WMAs, per general regs).", order=9)

note("Deer", "What You Need to Deer Hunt", "A hunting license is required for all seasons. Permit Bow, Muzzleloader, and Shotgun seasons additionally require a zone-specific (or Multi-Zone) Antlerless Permit, plus an Antlered Buck Permit if you want to take a buck. Muzzleloader hunting also requires a Rifle Permit. Deer permits go on sale Sept 14, 2026.")
note("Deer", "Legal Hunting Hours", "Half hour before sunrise to half hour after sunset.")
note("Deer", "Harvest Reporting", "All deer must be reported via the Automated Harvest Report System (855-448-6865 or online) by 10pm the day of harvest — you'll get a Confirmation Number that must stay with the deer/parts. A Deer Transportation Tag must be filled out and attached before moving the deer.")
note("Deer", "Antler Point Restriction", "Zones 3, 9, 13, 27, 28, 29, 30, 31, 34, 35, 47, 63, 67 require any antlered deer to have at least 3 points on one side. Zone 9 and 13 (in Regulation Set High) are subject to this rule. Does not apply to youth hunters.")
note("Deer", "Weapons Legal by Season", "Bow: long/recurve/compound/crossbow, min. 35 lb draw (75 lb for crossbow), broadhead min. 3/4\" wide. Muzzleloader: single-shot rifle ≥.44 cal or smoothbore 20–10ga, black powder only. Shotgun: 20–10ga, max 3 shells, slugs or buckshot #4 fine to #000. Rimfire/centerfire rifles are NOT legal for deer.")

# ============================== BLACK BEAR ==============================
season("Black Bear", "Segment A", "2026-10-12", "2026-10-17", weapon="Bow", species="Black Bear",
       bag="One bear, >75 lbs live weight",
       notes="Firearm hunters must wear 200 sq. in. hunter orange while bear hunting.", order=1)
season("Black Bear", "Segment A", "2026-10-15", "2026-10-17", weapon="Muzzleloader", species="Black Bear",
       bag="One bear, >75 lbs live weight",
       notes="Requires a valid Rifle Permit. Single-barrel, single-shot flintlock/percussion/in-line, not less than .44 cal. Only one muzzleloader may be in possession while bear hunting. Muzzleloader also legal all of Segment B.", order=1)
season("Black Bear", "Segment B", "2026-12-07", "2026-12-12", weapon="Shotgun/Muzzleloader",
       bag="1 bear >75 lbs live weight (max 2/season, 1 per segment)",
       notes="A possible Segment B Extension (Dec 16–19, 2026) may be announced Dec 14, 2026 — check NJDEP Fish & Wildlife's site.", order=2)

note("Black Bear", "What You Need to Bear Hunt", "A valid archery/firearm/all-around license AND a Black Bear Hunting Permit (zone-specific) are required. Permits sold in two windows: Sept 14–Oct 17, and Nov 2 onward. Apprentice License holders may NOT hunt bear.")
note("Black Bear", "Mandatory Bear Check", "Every harvested bear must be tagged immediately and brought to a designated Black Bear Check Station the day it's taken (Segment A: 9am–9pm; Segment B: noon–7pm). No Automated Harvest Report System for bears — physical check-in is required.")
note("Black Bear", "Minimum Size / Baiting", "Bears under 75 lbs live weight, or adults with cubs under 75 lbs, may not be harvested. No hunting weapon may be possessed within 300 ft of a baited area while bear hunting. Dogs may not be used to pursue bears.")

# ============================== TURKEY ==============================
season("Turkey", "Spring Gobbler Season", "2027-04-24", "2027-05-28", weapon="Shotgun or Bow",
       species="Wild Turkey", bag="1 male turkey per permit (no bearded hens)",
       notes="Permits are assigned by lottery to a specific Hunting Period (Y for youth, or A/B/C/D/E) and Turkey Hunting Area. Hours vary: most periods run sunrise-to-noon, Period D and the tail of Period Y run to sunset. No Sunday hunting. Fanning/reaping and stalking are illegal.", order=1)

note("Turkey", "Fall Season Closed", "The Fall Either-Sex Wild Turkey season is closed statewide for 2026 due to population declines from habitat loss and predation.")
note("Turkey", "Permits & Lottery", "A turkey permit (Lottery 1 + leftover Lottery 2) is required alongside a hunting license, tied to a specific Hunting Area and Period. Youth are guaranteed one Period Y permit. Harvest must be reported by 10pm the day of harvest.")

# ============================== UPLAND BIRDS ==============================
season("Upland Birds", "Bobwhite Quail (stocked)", "2026-11-07", "2027-01-31", weapon="Shotgun",
       species="Bobwhite Quail", zone="Greenwood Forest WMA & Peaslee WMA only",
       bag="4 quail", notes="Closed Dec 7–12 & 16. Wild bobwhite quail season is closed statewide.", order=1)
season("Upland Birds", "Chukar / Hungarian Partridge / Pheasant", "2026-11-07", "2027-02-15", weapon="Shotgun",
       bag="7 partridge, 2 pheasant", notes="Closed Dec 7–12 & 16.", order=2)
season("Upland Birds", "Youth Upland Bird Day", "2026-10-31", "2026-10-31", weapon="Shotgun", species="Pheasant",
       bag="2 pheasant", notes="Youth only, under adult supervision. Mentored AM hunt requires pre-registration.", order=3)
season("Upland Birds", "Youth Pheasant Days", "2026-11-02", "2026-11-06", weapon="Shotgun", species="Pheasant",
       bag="2 pheasant", notes="Youth only, under adult supervision.", order=4)
season("Upland Birds", "Crow (fall window)", "2026-08-10", "2026-11-28", weapon="Shotgun", species="Crow",
       bag="No limit", order=5)
season("Upland Birds", "Crow (winter window)", "2026-12-14", "2027-03-20", weapon="Shotgun", species="Crow",
       bag="No limit", notes="Monday, Thursday, Friday, and Saturday ONLY during this window.", order=6)

note("Upland Birds", "Ruffed Grouse Closed", "Ruffed grouse season is closed statewide — young-forest habitat has declined too far to support a season.")
note("Upland Birds", "Pheasant & Quail Stamp", "Required (age 16+) to hunt or possess pheasant/quail on any of the designated stocked WMAs, in addition to your hunting license.")

# ============================== SMALL GAME ==============================
season("Small Game", "Squirrel / Rabbit / Hare", "2026-09-26", "2027-02-20", weapon="Air Gun/Bow/Muzzleloader/Shotgun",
       bag="5 squirrel, 1 hare or jackrabbit, 4 cottontail (daily)", notes="Closed Dec 7–12 & 16.", weekday="!Sunday", order=1)
season("Small Game", "Opossum & Raccoon (night)", "2026-10-01", "2027-03-01", weapon="Air Gun/.22 Rifle/Shotgun",
       bag="No limit", notes="Night hours (1hr after sunset–1hr before sunrise). Closed Dec 7–12 & 16. Sunday hunting allowed only 12:01am–1hr before sunrise.", order=2)
season("Small Game", "Woodchuck (shotgun/bow/airgun)", "2026-03-02", "2027-02-20", weapon="Air Gun/Bow/Shotgun",
       bag="No limit", notes="Closed Dec 7–12 & 16. Rifle use for woodchuck is prohibited on all WMAs/Parks/Forests/Rec Areas year-round.", weekday="!Sunday", order=3)
season("Small Game", "Woodchuck (rifle)", "2026-03-02", "2026-09-30", weapon="Centerfire/Rimfire/Muzzleloading Rifle",
       bag="No limit", notes="Rifle Permit required. Prohibited on all WMAs/Parks/Forests/Recreation Areas.", weekday="!Sunday", order=4)
season("Small Game", "Coyote & Fox (daytime)", "2026-09-08", "2027-03-15", weapon="Bow/Shotgun/Rifle/Air Gun",
       bag="No limit", notes="Rifle use prohibited on State WMAs/Parks/Forests Sept 8–Dec 31. Harvest of coyote AND gray fox must be reported by 10pm same day.", weekday="!Sunday", order=5)
season("Small Game", "Coyote & Fox (nighttime)", "2027-01-01", "2027-03-15", weapon="Shotgun only",
       bag="No limit", notes="Standing/calling only, no dogs. Portable lights permitted. Harvest of coyote AND gray fox must be reported by 10pm same day.", order=6)

note("Small Game", "What You Need to Small Game Hunt", "A Firearm or Archery hunting license is required (whichever weapon you're using) — there's no separate small-game permit like deer/bear/turkey need. A Rifle Permit is required if using a centerfire/rimfire/muzzleloading rifle for woodchuck, or a muzzleloading rifle for squirrel.", order=1)
note("Small Game", "Legal Weapons — Squirrel, Rabbit, Hare", "Bow: longbow/recurve min. 35 lb draw, compound min. 35 lb peak weight, or crossbow min. 75 lb draw weight.\nShotgun: .410–10 ga, shot no larger than #4 fine.\nSmoothbore muzzleloader: 20–10 ga, shot no larger than #4 fine and no smaller than #10.\nAir gun: .177–.25 cal, min. 600 fps at the muzzle, wadcutter/domed/pointed/hollow-point pellets only — plain round BBs are NOT legal.\nMuzzleloading rifle: .36 cal or smaller, single-shot — SQUIRREL ONLY, does not apply to rabbit/hare/jackrabbit.\n\nNOT legal for squirrel, rabbit, or hare: rimfire or centerfire rifles (those are only legal in this chapter for woodchuck and coyote/fox).\n\nLicense: valid Archery License for bow, valid Firearm License for everything else, plus a Rifle Permit specifically if using the muzzleloading rifle option.", order=2)
note("Small Game", "Sunday Hunting", "Small game hunting is prohibited on Sundays, except opossum/raccoon (12:01am–1hr before sunrise only) and on properly licensed semi-wild/commercial preserves.", order=3)
note("Small Game", "Hunter Orange", "A solid daylight fluorescent orange hat (no camo/logos) is required as part of the 200 sq. in. hunter orange requirement when firearm hunting small game on any pheasant/quail-stocked WMA.", order=4)
note("Small Game", "Wanton Waste", "It's unlawful to kill or wound a squirrel, hare, rabbit, partridge, pheasant, quail, or woodcock and not make a reasonable effort to retrieve and possess it.", order=5)
note("Small Game", "Bobcat / Fisher Closed", "No open season for bobcat or fisher. Report sightings to the NJ Wildlife Tracker.", order=6)

# ============================== MIGRATORY BIRDS ==============================
season("Migratory Birds", "Woodcock — North Zone", "2026-10-24", "2026-12-05", species="Woodcock",
       bag="3/day", notes="Closed Nov 1–2. HIP Certification required.", order=1)
season("Migratory Birds", "Woodcock — South Zone", "2026-11-07", "2026-12-31", species="Woodcock",
       bag="3/day", notes="Closed Dec 6–18. HIP Certification required.", order=2)
season("Migratory Birds", "Ducks/Mergansers/Coot — North Zone", "2026-10-10", "2027-01-14", species="Ducks/Mergansers/Coot",
       bag="6 ducks in aggregate; mergansers 5; coot 15", notes="Closed Oct 18–Nov 13. Scaup limit graduates 1→2/day partway through. HIP + NJ & Federal Duck Stamps required.", order=3)
season("Migratory Birds", "Ducks/Mergansers/Coot — South Zone", "2026-10-17", "2027-01-21", species="Ducks/Mergansers/Coot",
       bag="6 ducks in aggregate; mergansers 5; coot 15", notes="Closed Oct 25–Nov 20.", order=4)
season("Migratory Birds", "Ducks/Mergansers/Coot — Coastal Zone", "2026-11-21", "2027-01-29", species="Ducks/Mergansers/Coot",
       bag="6 ducks in aggregate; mergansers 5; coot 15", order=5)
season("Migratory Birds", "Canada Geese (Regular) — North/South", "2026-11-21", "2027-01-30", species="Canada Goose",
       bag="3/day", notes="Closed Dec 1–18.", order=6)
season("Migratory Birds", "Canada Geese (Regular) — Coastal", "2026-11-21", "2027-01-29", species="Canada Goose",
       bag="2/day", order=7)
season("Migratory Birds", "September Canada Goose (statewide)", "2026-09-01", "2026-09-30", species="Canada Goose",
       bag="15/day", order=8)
season("Migratory Birds", "Brant — North/South", "2026-11-21", "2027-01-07", species="Brant",
       bag="1/day", notes="Closed Nov 29–Dec 11.", order=9)
season("Migratory Birds", "Snipe (statewide)", "2026-09-05", "2027-01-07", species="Snipe", bag="8/day", order=10)
season("Migratory Birds", "Rail & Gallinule (statewide)", "2026-09-01", "2026-11-20", species="Rail/Gallinule",
       bag="Sora & Virginia rail: 25 total; Gallinule: 1; Clapper rail: 10", order=11)
season("Migratory Birds", "Light Geese (Regular, statewide)", "2026-11-07", "2027-03-08", species="Light Geese",
       bag="25/day, singly or aggregate", order=12)

note("Migratory Birds", "No Sunday Hunting", "Migratory game bird hunting is not permitted on Sundays anywhere in New Jersey.")
note("Migratory Birds", "Required Stamps/Certs", "HIP Certification (all species), NJ Waterfowl Stamp, and Federal Duck Stamp are required to hunt ducks/geese/brant, all signed in ink.")
note("Migratory Birds", "Light Goose Conservation Order", "Dates TBD — determined from the 2026 Spring Migration count, decision expected by fall 2026. Requires a separate $2 Conservation Order Permit if it runs.")

# ============================== TRAPPING ==============================
season("Trapping", "Beaver", "2026-12-15", "2027-03-15", species="Beaver",
       bag="10 per permit", notes="Jan 1–Mar 15 only on stocked WMAs. Permit required (apply Oct 1–31, lottery).", order=1)
season("Trapping", "Otter", "2026-12-26", "2027-02-09", species="Otter",
       bag="1 per season", notes="Jan 1–Feb 9 only on stocked WMAs. Permit required (apply Oct 1–31, lottery). CITES seal required within 30 days of season end.", order=2)
season("Trapping", "Coyote / Gray Fox / Red Fox", "2026-11-15", "2027-03-15", species="Coyote/Fox",
       bag="No limit", notes="Jan 1–Mar 15 only on stocked WMAs. Coyote AND gray fox harvest must be reported by 10pm same day.", order=3)
season("Trapping", "Mink / Muskrat / Nutria", "2026-11-15", "2027-03-15", species="Mink/Muskrat/Nutria",
       bag="No limit", order=4)
season("Trapping", "Opossum / Raccoon / Striped Skunk", "2026-11-15", "2027-03-15", species="Opossum/Raccoon/Skunk",
       bag="No limit", notes="Jan 1–Mar 15 only on stocked WMAs.", order=5)
season("Trapping", "Weasels (long/short-tailed)", "2026-11-15", "2027-03-15", species="Weasel",
       bag="No limit", order=6)

note("Trapping", "Bobcat / Fisher Closed", "No take of bobcat or fisher is allowed anywhere. If one is caught incidentally, do not disturb the set — call (877) 927-6337 immediately.")
note("Trapping", "License & Education", "A Trapping License requires a Trapper Education Course Completion Card (min. age 12). Cable restraints additionally require a Snare Course Completion Card. Steel-jaw leghold traps are illegal statewide.")

# ============================== GENERAL / STATEWIDE ==============================
note(None, "Sunday Hunting", "No firearm hunting or carrying a loaded gun in the woods/fields/waters on Sunday, except semi-wild/commercial preserves and .22 rifles for dispatching trapped animals. Sunday bowhunting for deer is legal only on WMAs and private property. No Sunday hunting in NJ State Parks & Forests.", order=1)
note(None, "Hunter Orange", "Required (200 sq. in. solid daylight fluorescent orange, or a solid orange cap) for all firearm hunters pursuing deer, bear, rabbit, hare, squirrel, coyote, fox, railbirds, and game birds — including in a tree stand. Does not apply to waterfowl, crow, turkey, coyote/fox at night, or woodchuck hunting, nor to bowhunters (except during the Six-Day Firearm season or when using a deer decoy).", order=2)
note(None, "Safety Zones", "No loaded firearm within 450 ft of a building or school playground (150 ft for a nocked bow, but still 450 ft from a school playground) without the landowner's written permission in hand.", order=3)
note(None, "Licenses Needed", "A hunting license is required for everyone 10+ (10-16 gets a free Youth License after Hunter Education). Deer/Bear/Turkey seasons additionally require zone/area-specific permits on top of the base license. Apprentice Licenses let newcomers try hunting under a mentor before completing Hunter Education, with some restrictions (no rifle, no bear/coyote/fox, no muzzleloader deer season).", order=4)
note(None, "Chronic Wasting Disease (CWD)", "Whole deer carcasses and non-taxidermied heads from any other state/country are banned from import into NJ — only boned meat, cleaned skullcaps/hides, shed antlers, and clean upper canines may be brought in. Deer-derived scents/lures are banned statewide.", order=5)
note(None, "Source", "New Jersey Hunting & Trapping Digest, 2026-27 season (NJDEP Fish & Wildlife). Regulations in red in the original digest are new for 2026-27. This is a summary, not the full law — consult NJFishandWildlife.nj.gov for complete regulations.", order=99)

db.commit()
print(f"Seeded state id={nj.id}")
print("Season entries:", db.query(models.HuntingSeasonEntry).filter(models.HuntingSeasonEntry.state_id == nj.id).count())
print("Regulation notes:", db.query(models.HuntingRegulationNote).filter(models.HuntingRegulationNote.state_id == nj.id).count())
db.close()
