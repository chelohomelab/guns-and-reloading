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

echo "[install] Installing system dependencies..."
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip git curl unzip

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

echo "[install] Enabling and starting services..."
systemctl daemon-reload
systemctl enable --now inventory
systemctl enable --now inventory-backup.timer

IP=$(hostname -I | awk '{print $1}')
echo ""
if [ "$FRESH_INSTALL" = true ]; then
    echo "[install] Done! Open http://$IP:8000/setup to create your admin account."
else
    echo "[install] Done! App running at http://$IP:8000"
    echo ""
    echo "Next steps:"
    echo "  1. Go to /admin/backup and restore your backup ZIP"
    echo "  2. Run: rclone config  — to set up cloud backup"
fi
