---
title: Desktop App
layout: default
nav_order: 4
---

# Desktop App

For a single computer — no server, no LAN setup, no other devices needed. The desktop app is the
same software running locally, with its own local database. It doesn't share data with a [server
install]({% link installation.md %}) unless you restore a backup taken from one (see [Backup &
Disaster Recovery]({% link admin-guide.md %}#backup-disaster-recovery) in the Admin Guide).

## Downloads

Builds for all three platforms come from the [`Build Desktop Installers`
workflow](https://github.com/chelohomelab/guns-and-reloading/actions/workflows/build-desktop.yml).
Open the most recent successful (green ✓) run, and download the installer for your OS from its
**Artifacts** section at the bottom of the page. You'll need to be signed into GitHub for the
download link to work.

Windows builds are installer-tested on real hardware. macOS and Linux builds are newer and still
being verified — if something doesn't work, that's useful to know about.

### Windows

1. Download `installer-windows-latest`, unzip it to get `GunsAndReloading-Setup-X.Y.exe`.
2. Run it. Windows SmartScreen will likely warn "Windows protected your PC," since the installer
   isn't code-signed — click **More info → Run anyway**.
3. It installs the Microsoft Edge WebView2 Runtime automatically if you don't already have it,
   then the app itself, with Start Menu and an optional desktop shortcut.

### macOS

1. Download `installer-macos-latest`, unzip it to get a `.dmg`.
2. Open it and drag **Guns & Reloading** into Applications.
3. First launch: **right-click the app → Open** — not a normal double-click. The app is ad-hoc
   signed but not notarized (that needs a paid Apple Developer account), so a plain double-click
   gets silently blocked by Gatekeeper. Right-click → Open gives you an "Open anyway" option.
   After that first time, it launches normally.

### Linux (Fedora, Ubuntu, or any AppImage-capable distro)

1. Download `installer-ubuntu-latest`, unzip it to get
   `GunsAndReloading-Setup-X.Y-x86_64.AppImage`. The same file works on any distro — that's the
   whole point of AppImage, nothing distro-specific to pick.
2. It needs GTK3 and WebKit2GTK already on your system (same as running the app from source) —
   most desktop Linux installs already have these, but if launching it fails with a Gtk or
   WebKit2 error, install them first:
   - Fedora: `sudo dnf install gtk3 webkit2gtk4.1 python3-gobject`
   - Ubuntu: `sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-gi`
3. Install it properly — app-menu entry, icon, and a `guns-and-reloading` terminal command — with
   the installer script:
   ```bash
   curl -fsSLo install-desktop-linux.sh https://raw.githubusercontent.com/chelohomelab/guns-and-reloading/main/scripts/install-desktop-linux.sh
   bash install-desktop-linux.sh ~/Downloads/GunsAndReloading-Setup-X.Y-x86_64.AppImage
   ```
   Or skip installing it anywhere and just run it directly:
   ```bash
   chmod +x GunsAndReloading-Setup-X.Y-x86_64.AppImage
   ./GunsAndReloading-Setup-X.Y-x86_64.AppImage
   ```

## Where your data lives

- Windows: `%LOCALAPPDATA%\InventoryAndReloading`
- macOS: `~/Library/Application Support/InventoryAndReloading`
- Linux: `~/.local/share/InventoryAndReloading`

## Updating

There's no git checkout to `git pull` on a desktop install, so it checks for updates differently:
your account menu → **Upgrade** compares your installed version against the [latest GitHub
Release](https://github.com/chelohomelab/guns-and-reloading/releases/latest) and shows a Download
link when a newer one exists. Installing a newer version over an existing install upgrades it in
place — no need to uninstall first.
