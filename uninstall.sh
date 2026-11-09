
#!/bin/bash
set -e

# 52Pi EP-0152 Fan Controller Uninstaller

INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="auto_fan.py"
SERVICE_NAME="auto_fan.service"

echo "======================================"
echo "  52Pi EP-0152 Fan Controller"
echo "  Uninstallation"
echo "======================================"

if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo ./uninstall.sh"
    exit 1
fi

echo "[1/4] Stopping service..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true

echo "[2/4] Disabling service..."
systemctl disable "$SERVICE_NAME" 2>/dev/null || true

echo "[3/4] Removing service file..."
rm -f "/etc/systemd/system/$SERVICE_NAME"

echo "[4/4] Removing Python script..."
rm -f "$INSTALL_DIR/$SCRIPT_NAME"

# Reload systemd
systemctl daemon-reload
systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true

echo ""
echo "======================================"
echo " Uninstallation complete!"
echo " Fan controller and service removed."
echo "======================================"
echo ""
echo "Note: Python and GPIO dependencies were"
echo "left installed."
