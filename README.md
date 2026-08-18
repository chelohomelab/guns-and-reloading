# Firearm Inventory & Reloading

A self-hosted homelab app to track your firearm collection and reloading data.

**Stack:** FastAPI · SQLite · Jinja2 · Tailwind CSS · Docker

---

## Documentation

**📖 [Full documentation site](https://chelohomelab.github.io/guns-and-reloading/)**

| Guide | Description |
|---|---|
| [LXC Setup](docs/lxc-setup.md) | Create and configure a Proxmox LXC container |
| [Installation](docs/installation.md) | Deploy the app, first-time setup, and updating |
| [Desktop App](docs/desktop-app.md) | Windows/macOS/Linux installers for single-computer use, no server needed |
| [User Guide](docs/user-guide.md) | Feature walkthrough — inventory, reloading, range sessions, profiles |
| [Admin Guide](docs/admin-guide.md) | Users, backup/restore, self-upgrade, phone/tablet HTTPS setup |

---

## Quick Start

```bash
git clone https://github.com/chelohomelab/guns-and-reloading.git
cd guns-and-reloading
docker compose up -d --build
```

Then open `http://<host-ip>:8000/setup` to create your admin account.

---

## Features

- **Firearm inventory** — Rifles, Shotguns, Handguns with photos and sale tracking
- **Thompson Center** — Receivers and barrels tracked independently
- **Scope management** — Shared scope pool, mount/unmount inline
- **Reloading components** — Powders, primers, bullets, casings with low-stock alerts
- **Ammo log** — Factory and handload records, barcode-scannable
- **Range Session & Ladder Test** — Chronograph data with automatic ES/SD, target-photo group
  measurement, and charge-weight load development
- **Reloading Data Center** — Built-in reference library across six manufacturers' published data
- **Wishlist** — Track gear you want, convert straight to inventory once purchased
- **Barcode scanner** — Bookmarklet capture from supported retailers, with a review/completion queue
- **Offline-capable PWA** — Installable to your phone's home screen; browse inventory and log
  sessions with no signal, synced automatically once back online
- **Privacy-first pricing** — Dollar amounts are hidden/blurred by default everywhere except your
  own private Profile page
- **Per-user preferences** — Each user can hide features they don't use
- **Multi-user** — Admin-managed accounts, self-upgrade with automatic backup/rollback
