---
title: User Guide
layout: default
nav_order: 4
---

# User Guide
{: .no_toc }

A walkthrough of every feature in the Guns & Reloading app.
{: .fs-6 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Navigation

**On a wide screen (desktop/tablet landscape)**, a top bar runs across every page: your logo/home
link, **Inventory**, **Range Session**, and **Reloading Data Center** on the left, and your
username in the top right — click it to open **Profile**, admin tools (if you're an admin), and
**Sign Out**.

**On a phone**, the same links live behind the ☰ menu button, and your username/account menu is
in the top-right corner of the header — tap it for the same Profile/admin/Sign Out options.

---

## Inventory

Inventory is organized into four tabs: **Platforms** (firearms), **Optics**, **Ammunition**, and
**Components**.

### Platforms — Firearms, Handguns, Shotguns, Thompson Center

The Platforms tab has its own sub-tabs: **Rifles**, **Shotguns**, **Handguns**, and **Thompson
Center**.

To add one, use the **+ Add** button (or the **Add Inventory** shortcut) and fill in brand, model,
caliber, serial number, and price paid. Up to two photos can be attached. Click any card to open
its detail page, where you can edit every field, mount/unmount a scope, replace photos, log a
sale, or move the item to Trash.

**Thompson Center** works a little differently, since receivers and barrels are bought, sold, and
tracked independently:

- **Receivers** — Encore or Contender, with their own serial number and price paid
- **Barrels** — caliber, length, twist rate, hardware color, threading, and muzzle brake, each with
  its own scope mount

A **Sold** toggle filters the current view between your active collection and items you've sold
(with the recorded sale price). TC barrels always show regardless of the toggle, since a barrel
doesn't have its own sold status independent of the receiver it's mounted to.

### Optics

Scopes are a shared pool — any scope can be mounted to any rifle, handgun, shotgun, or TC barrel.
Mount/unmount a scope directly from the firearm or barrel's detail page; mounting to a new item
automatically unmounts it from wherever it was before.

### Ammunition

Tracks both **factory** ammo and **handloads**, with quantity kept in sealed boxes + loose rounds.
Each entry can be scanned in via barcode (see [Add Ammo — Scan Only](#add-ammo-is-scan-only)
below) or added manually. Handloads additionally record powder, charge weight, primer, brass, and
COAL.

A **Rounds Used** button on the ammo detail page deducts rounds from on-hand inventory — this is
the same deduction path a Range Session entry uses when you log a session against that ammo, so
your count stays accurate either way.

#### Add Ammo is scan-only

The **Add Ammunition** form only accepts a barcode scan — there's no manual "type in every field"
path for factory ammo, since the whole point is to pull brand/caliber/bullet weight/BC/etc.
automatically from the UPC. If a scan comes back with fields the app couldn't determine, you'll see
**Search UPC**, **Search Manufacturer #**, and **Refresh from Cache** buttons to fill in the gaps
without retyping everything. See the [Barcode Scanner](#barcode-scanner-admin) section for the
other (bulk/field) way to capture ammo.

### Components

Powders, primers, bullets, and casings — each tracked with brand, relevant specs (weight, caliber,
BC G1/G7, primer type, etc.), quantity on hand, and price. A low-stock badge appears once a
component drops below its threshold (adjustable per component type — see [Reload Data
Center](#reloading-data-center) admin tools, or ask an admin).

Use each component's **Deduct** control to subtract a used quantity after a loading session —
this keeps on-hand counts accurate without having to re-enter the full total.

---

## Range Session

**Range Session** and **Ladder Test** live on the same page as two tabs — both get filled in after
a trip to the range, so they're grouped together instead of being separate destinations.

### Logging a session

1. Upload a photo of your target
2. Calibrate: click two points a known distance apart (your target's grid lines work well), enter
   that distance, and lock it — this is what lets the app measure group size from the photo
3. Select the firearm and ammo/load used, and the distance to target
4. Tap each bullet hole on the photo to place a shot marker; drag a marker to nudge it, or use
   **Remove a Shot** to delete one
5. **Confirm & Save Group** — repeat for additional strings in the same session
6. **Upload Data to Homelab DB** commits the whole session (group sizes, velocities if entered,
   and the annotated photo) to your permanent records

You can also mark a **Point of Aim** on the photo, which the app uses to calculate distance from
POA to group center (useful for zeroing).

### Ladder Test

A ladder test tracks a charge-weight sweep for load development. Create one with a name, caliber,
COAL, powder/primer/bullet/casing, and a charge range (start/end/increment) — the app generates
one step per increment automatically. Rounds per step defaults to 1; raise it if you're loading
more than one round per charge.

As you shoot each step, record the velocities. The app plots charge weight vs. velocity and can
suggest candidate "nodes" (flat spots in the velocity curve, often a sign of a stable load) — click
a point on the chart to mark or unmark it as a node. You can add extra charge steps beyond the
original sweep at any time.

Components used in a ladder test (all rounds, for every step) are deducted from your reloading
component inventory immediately when the test is created, not later when velocities are recorded.

---

## Reloading Data Center

A built-in reference library for published reloading data across **six manufacturers**: Hodgdon,
Nosler, Speer, Sierra, Barnes, and Hornady. Pick a manufacturer tab, filter by caliber, and browse
published charge data (start/max charge, velocity, pressure where available) without leaving the
app or hunting down a PDF.

Admins can upload additional manufacturer PDFs to expand this library — see the [Admin
Guide]({% link admin-guide.md %}).

---

## Wishlist

A running list of gear you want to buy — rifles, handguns, shotguns, TC systems/barrels, optics,
or anything else. Each item has a priority (Low/Medium/High), an optional estimated price, notes,
and a link to where you found it. When you actually buy something on your wishlist, use **✓
Acquired** to convert it straight into your real inventory instead of re-entering it from scratch.

---

## Barcode Scanner (admin)

The Scanner page is a capture/review workflow for adding items in bulk, especially useful while
you're physically standing in front of a shelf of components or ammo:

- **Bookmarklet import** — drag the provided bookmarklet into your phone's bookmarks bar. On a
  supported retailer's product page (MidwayUSA, Target Sports USA, Academy Sports, Palmetto State
  Armory, LuckyGunner, Sportsman's Warehouse, Bass Pro Shops, Cabela's), tapping it captures the
  product's specs directly from the page. A complete capture is cached immediately; an incomplete
  one lands in the **Review** queue below for you to fill in the gaps later.
- **Review queue** — every incomplete or newly captured item shows up here, filterable by
  All/Incomplete/Reviewed, with a completeness badge so you can tell at a glance what still needs
  attention.

---

## Profile

Click your username (top right on desktop, or the account menu on mobile) → **Profile**.

### Inventory Value

Your collection's total count and dollar value per category (Firearms, Optics, Ammo, Components)
— shown only here, never anywhere else in the app, since it's private financial information.
Item-level prices elsewhere in the app are either hidden entirely (on inventory cards) or blurred
until you tap to reveal them (on detail pages).

### Feature Preferences

Toggle off entire sections you don't use — Shotguns, Handguns, Thompson Center, Reloading
Components, or Ammunition & Range Sessions. Hidden sections disappear from your nav and add forms
everywhere, on every device you log into. This is per-user, so a family member with a simpler setup
can hide what they don't need without affecting your account.

---

## Installing as an App (PWA)

On both Android and iOS, the app can be installed to your home screen like a native app — no app
store needed. Android shows an install prompt automatically; iOS doesn't support that, so look for
"Add to Home Screen" in Safari's Share menu instead.

Once installed (and once your device trusts your server's certificate — see [Phone/Tablet
Setup]({% link admin-guide.md %}#phonetablet-setup) in the Admin Guide), the app also works
**offline**: your inventory stays browsable with no signal, and logging a range session or
deducting rounds used queues up locally and syncs automatically the moment you're back online.
