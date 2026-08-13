---
title: LXC Setup
nav_order: 2
---

# Proxmox LXC Setup

This guide covers creating the Proxmox LXC container that will host the application.
The app runs directly under Python — no Docker needed — so the LXC requires no elevated kernel privileges.

---

## 1. Download a Container Template

In the Proxmox web UI:

1. Select your node → **local** storage → **CT Templates**
2. Click **Templates** and download **Debian 12 (Bookworm)**

---

## 2. Create the LXC Container

In the Proxmox web UI click **Create CT** and fill in:

| Field | Recommended value |
|---|---|
| Hostname | `firearm-inventory` |
| Password | Set a strong root password |
| Template | `debian-12-standard_*.tar.zst` |
| Unprivileged container | **Yes** (default) |
| Disk | 8 GB (expandable later) |
| CPU | 1–2 cores |
| Memory | 512 MB (1024 MB recommended) |
| Swap | 512 MB |
| Network | DHCP or a static IP on your LAN bridge |
| DNS | Use host settings |

> **Tip:** Assign a static IP so the app URL never changes. Either configure it in the LXC network settings or set a DHCP reservation on your router.

No special features (nesting, keyctl, etc.) are required. Leave them all off.

Click **Finish**, start the container, then open a shell via the Proxmox console or SSH.

---

## 3. Update the System

```bash
apt update && apt upgrade -y
```

---

## 4. Install Python and Git

```bash
apt install -y python3 python3-pip python3-venv git
```

Verify:

```bash
python3 --version
```

---

## Next Step

Continue to [Installation Guide](installation.md).
