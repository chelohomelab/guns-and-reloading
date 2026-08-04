#!/bin/bash
# Fresh install (clones the repo if needed) / disaster recovery reinstall — this script is
# idempotent over both cases, detected automatically.
# Run as root: bash install.sh   (or: curl -fsSL <raw-url>/scripts/install.sh | bash)

set -euo pipefail
APP_DIR="/opt/inventory-and-reloading"
REPO_URL="https://github.com/chelohomelab/inventory-and-reloading.git"

FRESH_INSTALL=true
if [ -f "$APP_DIR/data/reloading.db" ]; then
    FRESH_INSTALL=false
fi

CADDY_KEYRING=/usr/share/keyrings/caddy-stable-archive-keyring.gpg
CADDY_REPO=/etc/apt/sources.list.d/caddy-stable.list

# Self-heal from a previous run where a network blip left an empty/invalid GPG keyring behind
# with the repo still registered — apt-get update fails hard on an unsigned repo, which would
# otherwise permanently block *every* future install/reinstall attempt (not just Caddy) until
# manually cleaned up.
if [ -f "$CADDY_REPO" ] && [ ! -s "$CADDY_KEYRING" ]; then
    echo "[install] Cleaning up a broken Caddy repo registration from a previous attempt..."
    rm -f "$CADDY_REPO" "$CADDY_KEYRING"
fi

echo "[install] Installing system dependencies..."
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip git curl unzip

# avahi-daemon (mDNS/.local hostname) and Caddy (LAN-only HTTPS) are both additive nice-to-haves,
# not required for the app itself to work — a flaky download here must never abort the whole
# install. Each is wrapped so a failure prints a clear warning and the script continues normally.
CADDY_OK=true
AVAHI_OK=true

if ! apt-get install -y avahi-daemon; then
    echo "[install] WARNING: avahi-daemon install failed — .local hostname won't resolve, but the app itself will still work fine over IP. Continuing..."
    AVAHI_OK=false
fi

if ! command -v caddy >/dev/null 2>&1; then
    echo "[install] Installing Caddy (for LAN-only HTTPS — see step below)..."
    if ! apt-get install -y debian-keyring debian-archive-keyring apt-transport-https; then
        CADDY_OK=false
    fi
    if $CADDY_OK; then
        curl -fsSL --retry 3 --retry-delay 2 --max-time 30 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
            | gpg --yes --dearmor -o "$CADDY_KEYRING" || true
        if [ ! -s "$CADDY_KEYRING" ]; then
            echo "[install] WARNING: Caddy GPG key download failed or was empty — skipping HTTPS setup, app will still work fine over plain HTTP. Continuing..."
            rm -f "$CADDY_KEYRING"
            CADDY_OK=false
        fi
    fi
    if $CADDY_OK; then
        curl -fsSL --retry 3 --retry-delay 2 --max-time 30 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
            | tee "$CADDY_REPO" >/dev/null
        chmod o+r "$CADDY_KEYRING" "$CADDY_REPO"
        if ! apt-get update -qq; then
            echo "[install] WARNING: apt-get update failed after adding the Caddy repo — removing it and skipping HTTPS setup. Continuing..."
            rm -f "$CADDY_REPO" "$CADDY_KEYRING"
            apt-get update -qq || true
            CADDY_OK=false
        fi
    fi
    if $CADDY_OK && ! apt-get install -y caddy; then
        echo "[install] WARNING: Caddy package install failed — skipping HTTPS setup, app will still work fine over plain HTTP. Continuing..."
        CADDY_OK=false
    fi
fi

if [ ! -d "$APP_DIR/.git" ]; then
    echo "[install] Cloning repository into $APP_DIR..."
    mkdir -p "$(dirname "$APP_DIR")"
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "[install] Setting up Python venv..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

echo "[install] Creating required directories..."
mkdir -p data static/uploads backups

echo "[install] Installing systemd service..."
cp "$APP_DIR/inventory.service" /etc/systemd/system/inventory.service
cp "$APP_DIR/inventory-backup.service" /etc/systemd/system/inventory-backup.service
cp "$APP_DIR/inventory-backup.timer" /etc/systemd/system/inventory-backup.timer
chmod 644 /etc/systemd/system/inventory*.service /etc/systemd/system/inventory*.timer
chmod +x "$APP_DIR/scripts/backup.sh"

if ! command -v rclone >/dev/null 2>&1; then
    echo "[install] Installing rclone..."
    curl -s https://rclone.org/install.sh | bash
fi

HOSTNAME_LOCAL="$(hostname).local"
if $CADDY_OK; then
    echo "[install] Configuring LAN-only HTTPS (Caddy reverse proxy, local CA)..."
    cat > /etc/caddy/Caddyfile <<CADDYEOF
${HOSTNAME_LOCAL} {
    reverse_proxy localhost:8000
    tls internal
}
CADDYEOF
fi

echo "[install] Enabling and starting services..."
systemctl daemon-reload
# `enable --now` only starts a service if it isn't already running — on a reinstall/update run
# (re-running this script to pick up new code on an already-installed instance), the app would
# otherwise keep running whatever was already in memory, silently ignoring everything `git pull`
# just updated on disk. `restart` correctly starts it either way.
systemctl enable inventory
systemctl restart inventory
systemctl enable --now inventory-backup.timer
if $AVAHI_OK; then systemctl enable --now avahi-daemon || AVAHI_OK=false; fi
if $CADDY_OK; then systemctl restart caddy || CADDY_OK=false; fi

if $CADDY_OK; then
    echo "[install] Waiting for Caddy to provision its local CA..."
    mkdir -p "$APP_DIR/static/uploads"
    for i in $(seq 1 15); do
        if curl -s http://localhost:2019/pki/ca/local/certificates 2>/dev/null | grep -q "BEGIN CERTIFICATE"; then
            curl -s http://localhost:2019/pki/ca/local/certificates > "$APP_DIR/static/uploads/ca.crt"
            echo "[install] CA certificate saved — downloadable at https://${HOSTNAME_LOCAL}/static/uploads/ca.crt"
            break
        fi
        sleep 2
    done
    if [ ! -s "$APP_DIR/static/uploads/ca.crt" ]; then
        echo "[install] WARNING: could not fetch the local CA certificate yet — check 'systemctl status caddy'"
        echo "[install] and retry manually later: curl http://localhost:2019/pki/ca/local/certificates > $APP_DIR/static/uploads/ca.crt"
    fi
fi

IP=$(hostname -I | awk '{print $1}')
if $CADDY_OK && $AVAHI_OK; then
    PRIMARY_URL="https://${HOSTNAME_LOCAL}"
    HTTPS_NOTE="(or http://$IP:8000 — both work; see /admin/https-setup after logging in to get your phone trusting the HTTPS certificate too)"
else
    PRIMARY_URL="http://$IP:8000"
    HTTPS_NOTE="(LAN-only HTTPS wasn't set up this run — see the WARNINGs above. The app itself works fine over plain HTTP; re-run this script later to retry HTTPS setup once network conditions are better.)"
fi

echo ""
if [ "$FRESH_INSTALL" = true ]; then
    echo "[install] Done! Open ${PRIMARY_URL}/setup to create your admin account"
    echo "[install] ${HTTPS_NOTE}"
else
    echo "[install] Done! App running at ${PRIMARY_URL}"
    echo "[install] ${HTTPS_NOTE}"
    echo ""
    echo "Next steps:"
    echo "  1. Go to /admin/backup and restore your backup ZIP"
    echo "  2. Run: rclone config  — to set up cloud backup"
fi
