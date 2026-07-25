# Installation Guide

Prerequisites: a running Debian 12 LXC with Python 3 and Git installed. See [LXC Setup](lxc-setup.md) if you haven't done that yet.

---

## 1. Clone the Repository

```bash
cd /opt
git clone https://github.com/chelohomelab/inventory-and-reloading.git
cd inventory-and-reloading
```

---

## 1a. Optional: Personal Reloading-Data Submodule

`scripts/reload_data_seeds/data` is a private git submodule (`chelohomelab/reloading-books`)
holding hand-transcribed manufacturer reloading data (e.g. Hornady cartridge pages read directly
from photos — see project memory for why this isn't OCR'd or shipped in the public repo). It's
kept private and separate on purpose: the public app never redistributes any manufacturer's
compiled reloading data, only the general-purpose tool.

If you have access to that private repo, pull it in and run each seed script once:

```bash
git submodule update --init --recursive
venv/bin/python scripts/reload_data_seeds/data/*.py
```

Skip this step entirely if you don't have access — the app works fully without it, just without
that pre-loaded data (Hodgdon/Nosler/Speer/Sierra/Barnes still work normally via the regular
`/admin/reload-data` PDF upload).

---

## 2. Create a Virtual Environment and Install Dependencies

```bash
python3 -m venv venv
venv/bin/pip install --no-cache-dir -r requirements.txt
```

---

## 3. Create Persistent Data Directories

```bash
mkdir -p data static/uploads
```

These directories survive updates since they are on the host filesystem:

- `data/` — SQLite database
- `static/uploads/` — photo uploads

---

## 4. Install and Enable the systemd Service

```bash
cp /opt/inventory-and-reloading/inventory.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable inventory
systemctl start inventory
```

Check that it started cleanly:

```bash
systemctl status inventory
journalctl -u inventory -f   # Ctrl+C to exit
```

---

## 5. First-Time Setup

Open a browser and navigate to:

```
http://<lxc-ip>:8000/setup
```

Create the first admin account. After submitting you are redirected to the login page. This `/setup` endpoint is automatically disabled once at least one user exists.

---

## 6. Updating the Application

**From the UI (recommended):** sign in as an admin and go to `⚙️ → 🚀 Upgrade`. It shows whether
you're behind `main`, takes an automatic backup before touching anything, pulls, reinstalls
dependencies, and restarts itself — no SSH needed. A "Roll Back" button restores the code and the
database/photos to exactly how they were right before the last upgrade, in case something goes
wrong. It relies on `inventory.service`'s `Restart=on-failure` to come back up, so it only works
when the app is actually running under that systemd unit (not `--reload` dev mode).

**From the shell (manual/scripted):**

```bash
cd /opt/inventory-and-reloading
git pull
git submodule update --init --recursive  # only does anything if you set up 1a
venv/bin/pip install --no-cache-dir -r requirements.txt
systemctl restart inventory
```

The database and uploads are untouched either way. The app is typically back online in seconds.

---

## 7. (Optional) HTTPS with a Reverse Proxy

For HTTPS access from outside your LAN, put a reverse proxy in front of port 8000. Two common options on Proxmox:

### Option A — Nginx Proxy Manager (recommended for beginners)
- Deploy NPM as a separate LXC or Docker container
- Add a **Proxy Host** pointing to `http://<lxc-ip>:8000`
- Enable **Force SSL** and request a Let's Encrypt certificate

### Option B — Caddy
```bash
apt install -y caddy
```

`/etc/caddy/Caddyfile`:
```
inventory.yourdomain.com {
    reverse_proxy localhost:8000
}
```

```bash
systemctl reload caddy
```

Caddy handles TLS automatically via Let's Encrypt.

---

## 8. Stopping / Removing the App

```bash
# Stop the service
systemctl stop inventory

# Disable autostart
systemctl disable inventory

# Remove the service file
rm /etc/systemd/system/inventory.service
systemctl daemon-reload
```

---

## Next Step

Continue to the [User Guide](user-guide.md) to learn how to use the application.
