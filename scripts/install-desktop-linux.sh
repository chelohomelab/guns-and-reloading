#!/bin/bash
# Installs the Guns & Reloading desktop AppImage for the current user — copies it to a stable
# location, registers a Start Menu / app-launcher entry with icon, and adds a `guns-and-reloading`
# command to your PATH. Works identically on any AppImage-capable Linux (Fedora, Ubuntu, etc.) —
# it's the same file either way, that's the whole point of AppImage.
#
# There's no hosted download URL yet (installers aren't attached to GitHub Releases), so this
# takes a path to an AppImage you've already downloaded from the build's GitHub Actions artifacts:
#   bash install-desktop-linux.sh ~/Downloads/GunsAndReloading-Setup-1.24-x86_64.AppImage
#
# Does NOT install GTK3/WebKit2GTK — those must already be on your system (same as running from
# source). If the app fails to launch complaining about Gtk or WebKit2, install them first, e.g.:
#   Fedora:  sudo dnf install gtk3 webkit2gtk4.1 python3-gobject
#   Ubuntu:  sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-gi

set -euo pipefail

if [ "$(uname -s)" != "Linux" ]; then
    echo "[install] This script is for Linux only." >&2
    exit 1
fi

APPIMAGE_SRC="${1:-}"
if [ -z "$APPIMAGE_SRC" ] || [ ! -f "$APPIMAGE_SRC" ]; then
    echo "Usage: bash install-desktop-linux.sh /path/to/GunsAndReloading-Setup-X.Y-x86_64.AppImage" >&2
    exit 1
fi

INSTALL_DIR="$HOME/.local/share/guns-and-reloading"
APPIMAGE_DEST="$INSTALL_DIR/GunsAndReloading.AppImage"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"

echo "[install] Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR" "$ICON_DIR" "$DESKTOP_DIR" "$BIN_DIR"
cp "$APPIMAGE_SRC" "$APPIMAGE_DEST"
chmod +x "$APPIMAGE_DEST"

# Pull the icon out of the AppImage itself rather than depending on any other file being present
# — this script is meant to work standalone, without a repo checkout alongside it.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
( cd "$TMP" && "$APPIMAGE_DEST" --appimage-extract 'guns-and-reloading.png' >/dev/null )
if [ -f "$TMP/squashfs-root/guns-and-reloading.png" ]; then
    cp "$TMP/squashfs-root/guns-and-reloading.png" "$ICON_DIR/guns-and-reloading.png"
fi

cat > "$DESKTOP_DIR/guns-and-reloading.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Guns & Reloading
Comment=Firearm inventory and reloading tracker
Exec="$APPIMAGE_DEST" %U
Icon=guns-and-reloading
Categories=Utility;
Terminal=false
EOF

ln -sf "$APPIMAGE_DEST" "$BIN_DIR/guns-and-reloading"

# Best-effort — a fresh app-launcher entry/icon normally needs one of these to show up without
# logging out and back in, but neither is universally present, and their absence isn't fatal.
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

echo "[install] Done. Launch it from your application menu, or run: guns-and-reloading"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "[install] Note: $BIN_DIR isn't on your PATH, so the 'guns-and-reloading' command won't work in a terminal yet — the app-menu launcher will still work fine. Add 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your shell profile to fix that." ;;
esac
