---
title: Admin Guide
nav_order: 5
---

# Admin Guide
{: .no_toc }

Tools available to admin accounts only, reachable from the account menu in the top-right corner
(desktop) or the mobile menu.
{: .fs-6 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Users

Create additional accounts for family members or other users, grant/revoke admin privileges, and
deactivate or delete accounts. Deactivating removes access without deleting the user's data;
deleting removes the account entirely.

---

## Backup & Disaster Recovery

- **Download Backup** — a single zip containing the database and all uploaded photos, downloaded
  straight to your browser
- **Push to Cloud** — if `rclone` is installed and configured with a remote (set the remote name
  and path in Settings on this page), pushes a backup there in one click
- **Restore from Backup** — upload a previously downloaded backup zip to overwrite all current
  data. This always asks for confirmation first, since it's destructive.
- **Local Backups** — a list of backups already saved on the server, including the automatic ones
  taken before every self-upgrade or rollback (see below)

---

## Upgrade & Rollback

Keeps the app itself up to date by pulling the latest code from git and restarting — no SSH
needed for a routine update.

- **Current Version** is shown at the top. If a newer version is available on the project's `main`
  branch, a **New version** line appears with a **Show details** toggle (the underlying commit
  list) and an **Upgrade to X.Y** button.
- A backup is taken **automatically** before any upgrade touches the database or code, so a
  rollback always has something to restore to.
- **Roll Back** reverts the code to exactly the commit it was on before the last upgrade, and
  restores the database/photos from that automatic backup — anything entered since the upgrade is
  lost, which is why this asks for confirmation twice.
- If the server has local uncommitted changes (rare — usually only during development), both
  upgrade and rollback are blocked until they're resolved, to avoid an unsafe merge.
- Self-upgrade only works for a real git checkout (the LXC/systemd install path). Docker and
  desktop installs update via a new image tag or installer instead — this page says so and hides
  the controls automatically when git isn't available.

Want the full commit history or release notes beyond what's shown in-app? There's a link to the
project's GitHub page at the bottom of the Upgrade page.

---

## Phone/Tablet Setup

The app's offline features (browsing your inventory and logging range sessions with no signal)
require a secure (`https://`) connection — browsers won't enable them on a plain `http://`
address at all. If your server was set up with `install.sh`, this is already running: a private
certificate authority generated entirely on your own machine (no public domain, no internet
account, nothing leaves your network), with your server reachable at a stable `<hostname>.local`
address instead of a raw IP that can change.

The only remaining step is **per device, once**: each phone/tablet needs to trust that
certificate. This page shows a QR code and walks through the one-time install on both Android and
iOS. After that, `https://<hostname>.local` works like any other trusted website, and offline mode
starts working on that device. Plain `http://` access keeps working the whole time, unaffected —
this is purely additive.

---

## Reloading Data Center — Import

Where the [Reloading Data Center]({% link user-guide.md %}#reloading-data-center) reference
library actually comes from: upload a manufacturer's published reloading-data PDF here and it's
parsed and made browsable/searchable in the main app. You can select multiple files at once — each
is parsed independently, and the manufacturer is normally auto-detected per file (Barnes PDFs are
the one exception — always set that one manually, since there's no reliable brand text inside the
file to detect from).

Re-uploading a file only replaces that same manufacturer/caliber/weight combination — it never
touches another manufacturer's data. The **Imported Sources** list on this page shows everything
that's been uploaded so far, with an option to remove a source if you need to.

---

## Trash

Deleted inventory items go here first instead of being erased immediately — restore something you
deleted by mistake, or permanently delete it (which cannot be undone) once you're sure.

---

## Barcode Scanner Review Queue

See [Barcode Scanner]({% link user-guide.md %}#barcode-scanner-admin) in the User Guide — the
review/completion workflow for items captured via the bookmarklet is an admin-only tool since it
touches shared inventory data directly.
