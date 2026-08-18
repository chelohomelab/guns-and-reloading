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

All three are attached directly to the [latest GitHub
Release](https://github.com/chelohomelab/guns-and-reloading/releases/latest) — no GitHub account
or login needed, just click and download.

Windows is installer-tested on real hardware. macOS and Linux are newer and still being verified —
the Release page itself notes the current status of each; if something doesn't work, that's
useful to know about.

### Windows

1. Download `GunsAndReloading-Setup-X.Y.exe` from the [latest
   Release](https://github.com/chelohomelab/guns-and-reloading/releases/latest).
2. Run it. Windows SmartScreen will likely warn "Windows protected your PC," since the installer
   isn't code-signed — click **More info → Run anyway**.
3. It installs the Microsoft Edge WebView2 Runtime automatically if you don't already have it,
   then the app itself, with Start Menu and an optional desktop shortcut.

### macOS

1. Download `GunsAndReloading-Setup-X.Y.dmg` from the [latest
   Release](https://github.com/chelohomelab/guns-and-reloading/releases/latest).
2. Double-click the downloaded file. A window pops up with two icons side by side: the **Guns &
   Reloading** app on the left and a folder icon labeled **Applications** on the right. Click and
   hold the app icon, drag it on top of the Applications folder icon, then let go — that copies
   it into your actual Applications folder (this window itself is just a temporary "installer,"
   not where the app actually lives).
3. Open a Finder window, click **Applications** in the sidebar, and find **Guns & Reloading**
   there. **Right-click it → Open** — not a normal double-click. The app is ad-hoc signed but not
   notarized (that needs a paid Apple Developer account), so a plain double-click gets silently
   blocked by Gatekeeper the first time. Right-click → Open gives you an "Open anyway" option.
   After that first time, a normal double-click works from then on.

### Linux (Fedora, Ubuntu, or any AppImage-capable distro)

1. Download `GunsAndReloading-Setup-X.Y-x86_64.AppImage` from the [latest
   Release](https://github.com/chelohomelab/guns-and-reloading/releases/latest). The same file
   works on any distro — that's the whole point of AppImage, nothing distro-specific to pick.
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
