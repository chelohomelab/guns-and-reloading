"""Seed Pennsylvania 2026-27 hunting data, hand-extracted from the PA Game
Commission's 2026-27 Hunting & Trapping Digest (static/temp/PA-Game-Hunting-and-Trapping-Digest-26-27.pdf).
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from database import SessionLocal, HuntingState, HuntingSeasonEntry, HuntingRegulationNote

db = SessionLocal()

# Idempotent: wipe any existing PA data first
existing = db.query(HuntingState).filter(HuntingState.name == "Pennsylvania").first()
if existing:
    db.delete(existing)
    db.commit()

state = HuntingState(name="Pennsylvania", abbreviation="PA", display_order=1)
db.add(state)
db.commit()
db.refresh(state)

YEAR = "2026-27"
STATEWIDE = "Statewide"

_season_order = {}


def season(game_type, species, season_label, start, end, weapon=None, zone=STATEWIDE,
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
season(G, "Deer", "Archery", "2026-10-03", "2026-11-20", weapon="Bow", bag="Antlered & Antlerless")
season(G, "Deer", "Archery", "2026-12-26", "2027-01-24", weapon="Bow", bag="Antlered & Antlerless")
season(G, "Deer", "Archery", "2026-09-19", "2026-11-27", weapon="Bow", zone="WMUs 2B, 5C & 5D", bag="Antlered & Antlerless")
season(G, "Deer", "Archery", "2026-12-26", "2027-01-24", weapon="Bow", zone="WMUs 2B, 5C & 5D", bag="Antlered & Antlerless")
season(G, "Deer", "October Muzzleloader", "2026-10-17", "2026-10-25", weapon="Muzzleloader", bag="Antlerless only", notes="Requires a muzzleloader license unless exempt.")
season(G, "Deer", "Flintlock", "2026-12-26", "2027-01-24", weapon="Flintlock", bag="Antlered & Antlerless", notes="An unused antlered tag from a general license may be used for antlerless deer ONLY in this season. Each participant needs a muzzleloader license in addition to a general license (unless exempt). No fluorescent orange required.")
season(G, "Deer", "Special Firearms", "2026-10-22", "2026-10-25", weapon="Special Firearms", bag="Antlerless only", notes="Limited to licensed seniors, junior license holders, mentored permit holders, qualified active-duty military, and disabled hunters with a vehicle-as-blind permit.")
season(G, "Deer", "Regular Firearms", "2026-11-28", "2026-12-13", weapon="Regular Firearms (rifle/shotgun/muzzleloader/bow)", bag="Antlered & Antlerless (1 antlered deer/license year max)")
season(G, "Deer", "Extended Firearms (DMAP)", "2026-12-26", "2027-01-24", weapon="Regular Firearms", bag="Antlerless only — requires DMAP permit")
season(G, "Deer", "Extended Firearms (DMAP)", "2026-12-26", "2027-01-18", weapon="Regular Firearms", zone="WMUs 4A, 4C, 4D & 5A", bag="Antlerless only — requires DMAP permit")

note(G, "Antler Restrictions", "Statewide: antlered deer must have 3 points on one side (or a spike ≥3\" long).\nWMUs 1A, 1B, 2A, 2B & 2D (“three up”): 3 points on one side INCLUDING the main beam, EXCLUDING the brow tine.\nSenior license holders must also follow antler restrictions.")
note(G, "Antlerless License Requirement", "Except during the Flintlock season, you must hold a valid antlerless deer license, DMAP permit, or Ag Tag permit to take an antlerless deer — one antlerless deer per license/permit. Max 6 unfilled antlerless licenses at a time (15 in WMUs 5C & 5D).")
note(G, "Fluorescent Orange — Deer", "250 sq. in. on head/chest/back combined, visible 360°, required during Regular, Special & Extended Firearms seasons and the October Muzzleloader season — for ALL participants including bowhunters. NOT required during archery-only seasons or the after-Christmas Flintlock season.")
note(G, "Tagging", "Detach the harvest tag from your license, fill it out, and attach it to the deer's EAR immediately after harvest, before the carcass is moved. Tag must stay attached until the animal is processed or mounted.")

# ============================== BLACK BEAR ==============================
G = "Black Bear"
season(G, "Black Bear", "Archery", "2026-10-17", "2026-10-25", weapon="Bow")
season(G, "Black Bear", "Archery", "2026-10-03", "2026-11-20", weapon="Bow", zone="WMUs 3C, 3D & 5B")
season(G, "Black Bear", "Archery", "2026-09-19", "2026-11-27", weapon="Bow", zone="WMUs 2B, 5C & 5D")
season(G, "Black Bear", "Special Firearms", "2026-10-22", "2026-10-25", weapon="Special Firearms", notes="Same restricted eligibility as the Deer Special Firearms season (seniors, juniors, mentored, active-duty military, disabled vehicle-blind permit).")
season(G, "Black Bear", "Regular Firearms", "2026-11-21", "2026-11-24", weapon="Regular Firearms")
season(G, "Black Bear", "Muzzleloader", "2026-10-22", "2026-10-25", weapon="Muzzleloader")
season(G, "Black Bear", "Extended Firearms", "2026-11-28", "2026-12-13", weapon="Regular Firearms", zone="WMUs 2B, 5B, 5C & 5D")
season(G, "Black Bear", "Extended Firearms", "2026-11-28", "2026-12-06", weapon="Regular Firearms", zone="WMUs 3A, 3B, 3C, 3D, 4C, 4E & 5A")

note(G, "Bear License & Bag Limit", "Hunters are limited to 1 bear per license year, combined across ALL segments (archery + special + regular + extended). A Black Bear License is required in addition to a general hunting license, and it covers the archery and muzzleloader bear seasons without needing a separate archery/muzzleloader license.")
note(G, "Mandatory Bear Check", "Every harvested bear must be checked by the Game Commission within 24 hours. Check stations are open ONLY the first 2 days of the Regular Firearms season and select days of the Extended seasons — call the Centralized Dispatch Center (1-833-PGC-HUNT) for instructions any other time, including during all early/archery/muzzleloader seasons.")
note(G, "Fluorescent Orange — Bear", "250 sq. in. on head/chest/back combined, visible 360°, required during Special, Regular and Extended Firearms seasons (firearm hunters) — NOT required during archery season.")

# ============================== ELK ==============================
G = "Elk"
season(G, "Elk", "Archery", "2026-09-12", "2026-09-27", weapon="Bow", zone="Drawn Elk Hunt Zone only")
season(G, "Elk", "First Regular Firearms", "2026-10-03", "2026-10-11", weapon="Firearms", zone="Drawn Elk Hunt Zone only")
season(G, "Elk", "Second Regular Firearms", "2026-10-31", "2026-11-08", weapon="Firearms", zone="Drawn Elk Hunt Zone only")
season(G, "Elk", "Third Regular Firearms", "2027-01-09", "2027-01-17", weapon="Firearms", zone="Drawn Elk Hunt Zone only")

note(G, "Lottery Draw Required", "Elk hunting is by DRAWN LICENSE ONLY — you cannot hunt elk without being drawn. A single application (deadline July 12) lets you pick up to 5 season/zone/antlered-or-antlerless combinations. There are 11 Elk Hunt Zones (300-310, zone 300 closed). Bonus points accumulate each year you apply and aren't drawn (max 37). Antlered elk licenses are once-in-a-lifetime; antlerless license holders can apply again after their bonus points reset.")
note(G, "License Fee If Drawn", "Resident elk license: $25. Nonresident: $250. No more than 10% of licenses go to nonresidents.")

# ============================== TURKEY ==============================
G = "Turkey"
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-15", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 1A, 2G, 3A, 4A, 4B & 4D", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-08", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 1B, 3D, 4C & 4E", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-15", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 2A, 2F, 3B & 3C", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-20", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 2B, 2C, 2D & 2E", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Fall Season", "2026-11-25", "2026-11-27", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 2B, 2C, 2D & 2E", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Fall Season", "2026-10-31", "2026-11-03", weapon="Shotgun/Muzzleloading Shotgun/Bow", zone="WMUs 5A & 5B", bag="1 bird (bearded or unbearded)")
season(G, "Wild Turkey", "Spring Youth Hunt", "2027-04-24", "2027-04-25", weapon="Shotgun/Muzzleloading Shotgun/Bow", bag="1 bearded bird")
season(G, "Wild Turkey", "Spring Season", "2027-05-01", "2027-05-31", weapon="Shotgun/Muzzleloading Shotgun/Bow", bag="1 bearded bird")

note(G, "Fall Season Closed in 5C & 5D", "WMUs 5C & 5D (extreme SE Philadelphia-metro units) have NO fall turkey season this year.")
note(G, "Legal Arms Changed for Fall", "Fall season: shotgun (≤ 3-shell capacity), muzzleloading shotgun, or bow/crossbow only. Centerfire/rimfire rifles, muzzleloading rifles/handguns, slug guns and single-projectile ammunition are NO LONGER legal for fall turkey. Spring season: same shotgun/muzzleloading-shotgun/bow restriction.")
note(G, "Bag Limit Reduced This Year", "Spring bag limit is reduced to 1 bearded bird (down from 2) to offset the additional harvest expected from expanded Sunday hunting.")
note(G, "Dogs", "Dogs may be used during the FALL season only — not during spring turkey season.")

# ============================== SMALL GAME ==============================
G = "Small Game"
season(G, "Gray/Red/Fox/Black Squirrel", "Junior Hunt", "2026-09-12", "2026-09-27", bag="6 daily, 18 possession")
season(G, "Gray/Red/Fox/Black Squirrel", "Regular Season", "2026-09-12", "2026-12-24", bag="6 daily, 18 possession")
season(G, "Gray/Red/Fox/Black Squirrel", "Regular Season", "2026-12-26", "2027-02-28", bag="6 daily, 18 possession")
season(G, "Cottontail Rabbit", "Junior Hunt", "2026-10-03", "2026-10-18", bag="4 daily, 12 possession")
season(G, "Cottontail Rabbit", "Regular Season", "2026-10-17", "2026-12-24", bag="4 daily, 12 possession")
season(G, "Cottontail Rabbit", "Regular Season", "2026-12-26", "2027-02-28", bag="4 daily, 12 possession")
season(G, "Woodchuck", "Open Season", "2026-07-01", "2026-12-24", bag="No limit")
season(G, "Woodchuck", "Open Season", "2026-12-26", "2027-06-30", bag="No limit")
season(G, "Crow", "Open Season", "2026-08-20", "2027-03-21", bag="No limit", notes="Cannot be hunted during the Regular Firearms Deer season.")
season(G, "Snowshoe Hare", "Open Season", "2026-12-26", "2026-12-27", bag="1 daily, 3 season limit", notes="Open Thursdays, Fridays, Saturdays & Sundays only — legal days this year: Dec. 26, 27 & 31.")
season(G, "Snowshoe Hare", "Open Season", "2026-12-31", "2026-12-31", bag="1 daily, 3 season limit")

note(G, "Legal Weapons", "Shotgun: ≤10 gauge, ≤3-shell capacity (chamber+magazine).\nRifle/handgun: manually operated or semiautomatic, .22 rimfire or smaller (no magazine-capacity limit for semiauto rifles).\nAir gun: .177–.22 cal (BBs prohibited); woodchuck requires ≥.22 cal.\nMuzzleloading rifle/handgun: ≤.40 cal; muzzleloading shotgun ≤10 ga.\nBow/crossbow: long, recurve, compound or crossbow.\nNote: rifle/handgun caliber restrictions (except air guns) do NOT apply to woodchuck.")
note(G, "Fluorescent Orange", "250 sq. in. on head/chest/back, visible 360°, required for small game and porcupine hunters. Woodchuck hunters need a solid fluorescent orange cap specifically. No orange required for crow hunters.")
note(G, "Hunting During Firearms Deer Season", "Small game hunting is allowed to overlap with the Regular Firearms Deer season, but you must meet the arms/ammo AND orange requirements for whichever species you're actually hunting at that moment — you can't carry deer-legal gear while small-game hunting or vice versa.")

# ============================== UPLAND BIRDS ==============================
G = "Upland Birds"
season(G, "Pheasant", "Junior Hunt", "2026-10-10", "2026-10-18", bag="2 daily, 6 possession")
season(G, "Pheasant", "Regular Season", "2026-10-24", "2026-12-24", bag="2 daily, 6 possession", notes="Pheasant permit required for most adult hunters, in addition to a general license.")
season(G, "Pheasant", "Regular Season", "2026-12-26", "2027-02-28", bag="2 daily, 6 possession")
season(G, "Bobwhite Quail", "Regular Season", "2026-09-01", "2026-12-24", bag="No limit", notes="No open season in the Letterkenny Army Depot Bobwhite Quail Recovery Area.")
season(G, "Bobwhite Quail", "Regular Season", "2026-12-26", "2027-03-31", bag="No limit")
season(G, "Ruffed Grouse", "Regular Season", "2026-10-17", "2026-12-24", bag="2 daily, 6 possession")

note(G, "Pheasant Permit", "Required for most adult (and some senior) pheasant hunters, in addition to a general hunting license/mentored permit. Free for junior hunters and mentored permit holders under 17. Exempt: senior/senior-combo lifetime license holders who bought before May 13, 2017.")
note(G, "Wild Pheasant Recovery Areas (WPRAs)", "No open pheasant season inside a WPRA except limited hunts the executive director may authorize. All other small game species can still be hunted in a WPRA when in season.")

# ============================== MIGRATORY BIRDS ==============================
G = "Migratory Birds"
season(G, "Ducks/Mergansers/Coots", "South Zone", "2026-10-10", "2026-10-17", zone="South Zone (most of PA — excludes Lake Erie/Northwest/North zones)", bag="6 ducks/4 sea ducks daily combined, see species sub-limits", weekday="!Sunday")
season(G, "Ducks/Mergansers/Coots", "South Zone", "2026-11-18", "2027-01-18", zone="South Zone (most of PA — excludes Lake Erie/Northwest/North zones)", bag="6 ducks/4 sea ducks daily combined, see species sub-limits", weekday="!Sunday")
season(G, "Mourning Dove", "Regular Season", "2026-09-01", "2026-11-27", bag="15 daily, 45 possession", weekday="!Sunday")
season(G, "American Woodcock", "Regular Season", "2026-10-17", "2026-12-08", bag="3 daily, 9 possession", weekday="!Sunday")
season(G, "Wilson's Snipe", "Regular Season", "2026-10-17", "2026-12-08", bag="8 daily, 24 possession", weekday="!Sunday")
season(G, "Wilson's Snipe", "Regular Season", "2026-12-18", "2027-01-02", bag="8 daily, 24 possession", weekday="!Sunday")
season(G, "Virginia & Sora Rail / Gallinule", "Regular Season", "2026-09-01", "2026-11-20", bag="3 daily, 9 possession (singly or combined)", weekday="!Sunday")
season(G, "Brant", "Regular Season", "2026-10-10", "2026-11-13", zone="Both Goose Zones", bag="1 daily, 3 possession", weekday="!Sunday")

note(G, "License Requirements", "A general hunting license or mentored permit is required. To hunt ducks/geese/doves/woodcock/brant/coots/gallinules/rails/snipe you also need a PA Migratory Game Bird License. Waterfowl hunters 16+ need a federal duck stamp (E-Stamp accepted for the full season).")
note(G, "Closed on Sundays", "Unlike every other PA hunting season this year, ALL migratory game bird hunting (waterfowl, doves, woodcock, snipe, rails, gallinules, geese) remains CLOSED on Sundays.")
note(G, "Canada & Light Geese — Check Zone Dates", "Canada goose season dates/bag limits differ between the Resident Population Zone and the Atlantic Population Zone (boundary is a detailed road/county description, not WMU-based), plus a separate early-September season and county-line exceptions in western Crawford/Mercer counties. This digest's goose zone diagram didn't extract cleanly as text, so dates weren't seeded here — check pa.gov/pgc or the digest's Canada Geese page directly before hunting geese. Light geese (snow/Ross's): Nov. 6–Mar. 10 in both zones, no possession limit, calls/e-calls allowed.")
note(G, "Duck Zone", "PA has 4 duck zones (Lake Erie, Northwest, North, South) with different dates — only the South Zone (which covers the entire eastern/southeastern part of the state, including everywhere within a few hours of central NJ) was seeded here.")

# ============================== TRAPPING ==============================
G = "Trapping"
# Hunting (no trap required)
season(G, "Coyote", "Hunting — No Closed Season", "2026-07-01", "2027-06-30", bag="No limit", notes="Can be hunted year-round, including Sundays, with a hunting license. During any big-game season, big-game orange rules apply; if you're out of big-game tags you need a furtaker license instead.")
season(G, "Raccoon", "Hunting", "2026-10-24", "2027-02-21", bag="No limit", notes="Legal hours: 1/2 hr after sunset to 1/2 hr before sunrise. During the Nov. 28–Dec. 13 Regular Firearms Deer season overlap, hunting may only occur after legal deer hunting hours have closed for the day.")
season(G, "Fox", "Hunting", "2026-10-24", "2027-02-21", bag="No limit", notes="Same nighttime-hours and deer-season-overlap restriction as raccoon.")
season(G, "Opossum / Striped Skunk / Weasel", "Hunting — No Closed Season", "2026-07-01", "2027-06-30", bag="No limit")
season(G, "Bobcat", "Hunting (permit)", "2027-01-09", "2027-02-03", zone="WMUs 2A, 2B, 2C, 2D, 2E, 2F, 2G, 3A, 3B, 3C, 3D, 4A, 4B, 4C, 4D, 4E & 5A", bag="1 per license year, permit required")
season(G, "Porcupine", "Hunting", "2026-10-10", "2026-11-27", bag="3 daily, 10 per season", notes="May not be hunted at night.")
season(G, "Porcupine", "Hunting", "2026-12-14", "2026-12-24", bag="3 daily, 10 per season", notes="May not be hunted at night.")
season(G, "Porcupine", "Hunting", "2026-12-26", "2027-01-31", bag="3 daily, 10 per season", notes="May not be hunted at night.")
# Trapping
season(G, "Coyote", "Trapping — General", "2026-10-24", "2027-02-21", bag="No limit")
season(G, "Fox & Coyote", "Trapping — Cable Restraints", "2026-12-26", "2027-02-21", bag="No limit", notes="Cable restraints permitted for fox & coyote only, during late-winter freezing conditions. Certification course required to use cable restraints.")
season(G, "Raccoon / Opossum / Striped Skunk / Weasel", "Trapping — General", "2026-10-24", "2027-02-21", zone="WMUs 2C, 2D, 2E, 2F, 3A, 3B, 3D, 5C & 5D", bag="Combined 20 daily, 20 per season", notes="Combined bag limit varies by WMU group: 1A&1B = 60/season; 2A,2B&3C = 40/season; 2C,2D,2E,2F,3A,3B,3D,5C&5D = 20/season; 2G,4A,4B,4C,4D,4E,5A&5B = 5/season.")
season(G, "Beaver", "Trapping", "2026-12-19", "2027-03-31", bag="See digest for zone-specific limits")
season(G, "Mink & Muskrat", "Trapping", "2026-11-21", "2027-01-10", bag="Combined 20 daily, 20 per season")
season(G, "Bobcat", "Trapping (permit)", "2026-12-19", "2027-01-10", zone="WMUs 2A, 2B, 2C, 2D, 2E, 2F, 2G, 3A, 3B, 3C, 3D, 4A, 4B, 4C, 4D, 4E & 5A", bag="1 per license year, permit required")
season(G, "Fisher", "Trapping (permit)", "2026-12-19", "2027-01-10", zone="WMUs 1B, 2C, 2D, 2E, 2F, 2G, 3A, 3B, 3C, 3D, 4A, 4B, 4C, 4D & 4E", bag="1 per license year, permit required")
season(G, "River Otter", "Trapping (permit)", "2027-02-13", "2027-02-21", zone="WMUs 1A, 1B, 2F, 2G, 3A, 3B, 3C, 3D, 4C & 4E", bag="1 per license year, permit required")

note(G, "Licenses & Permits", "A furtaker license is required to TRAP any furbearer (including coyotes) and to HUNT most furbearers (raccoon, fox, bobcat, etc.). Coyotes can be hunted with just a general hunting license. Bobcat, fisher and river otter each require their own separate permit in addition to the furtaker license.")
note(G, "Nighttime Hunting Hours", "Fox, raccoon, opossum, striped skunk and weasel may be hunted any hour of the day or night during their open season — EXCEPT during the Regular Firearms Deer season (Nov. 28–Dec. 13), when hunting may only occur after legal deer-hunting hours have closed.")
note(G, "Regional Trapping Bag Limits", "The combined Raccoon/Opossum/Skunk/Weasel trapping bag limit is split into 4 WMU groups with different per-season totals: WMUs 1A&1B = 60; WMUs 2A,2B&3C = 40; WMUs 2C,2D,2E,2F,3A,3B,3D,5C&5D = 20; WMUs 2G,4A,4B,4C,4D,4E,5A&5B = 5. Check which group covers your WMU before you trap.")

# ============================== GENERAL / STATEWIDE ==============================
note(None, "Sunday Hunting Expanded This Year", "New for 2026-27: Sunday hunting now applies to ALL seasons EXCEPT migratory game birds (waterfowl, doves, woodcock, snipe, rails, gallinules, geese), which remain closed on Sundays as before.")
note(None, "Wildlife Management Units (WMUs)", "PA splits Deer, Bear, Turkey and some Furtaking seasons by Wildlife Management Unit (WMU) — entries here labeled “Statewide” apply everywhere EXCEPT where a specific WMU group has its own entry with different dates. Check whether your WMU appears in any zone-specific entry's WMU list before assuming the statewide dates apply to you.")
note(None, "Fluorescent Orange — General Rule", "When required, 250 sq. in. of daylight fluorescent orange on the head, chest and back combined, visible from 360°, worn at all times while hunting (from 1 hr before legal hours start to 1 hr after they end). Required for: all small game seasons, Deer/Bear/Elk regular firearms seasons, October Muzzleloader Deer/Bear, and Special/Extended Firearms seasons. NOT required for: archery-only big-game seasons, waterfowl, doves, turkey, furbearers, or crows.")
note(None, "Licenses", "A general hunting license (or mentored permit) is required for any season. Archery and Muzzleloader seasons each need their own license unless you hold a combination license or mentored permit that includes that privilege. A Black Bear License covers bear archery + muzzleloader seasons without a separate license. A furtaker license is needed to trap furbearers and to hunt most of them.")

db.commit()

# Summary
for gt in ["Deer", "Black Bear", "Elk", "Turkey", "Small Game", "Upland Birds", "Migratory Birds", "Trapping"]:
    n_seasons = db.query(HuntingSeasonEntry).filter(HuntingSeasonEntry.state_id == state.id, HuntingSeasonEntry.game_type == gt).count()
    n_notes = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type == gt).count()
    print(f"{gt}: {n_seasons} season entries, {n_notes} notes")
n_general = db.query(HuntingRegulationNote).filter(HuntingRegulationNote.state_id == state.id, HuntingRegulationNote.game_type.is_(None)).count()
print(f"General: {n_general} notes")

db.close()
print("Done.")
