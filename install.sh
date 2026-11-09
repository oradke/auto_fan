
#!/bin/bash
set -e

# 52Pi EP-0152 Fan Controller Installer

INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="52pi-fan.py"
SERVICE_NAME="52pi-fan.service"

echo "======================================"
echo "  52Pi EP-0152 Fan Controller"
echo "  Installation"
echo "======================================"

# Check root privileges
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo ./install.sh"
    exit 1
fi

# Check source file
if [[ ! -f "$SCRIPT_NAME" ]]; then
    echo "ERROR: $SCRIPT_NAME not found!"
    echo "Place install.sh and $SCRIPT_NAME in the same directory."
    exit 1
fi

# Update package lists
echo "[1/6] Updating package lists..."
apt-get update

# Install Python and GPIO dependencies
echo "[2/6] Installing dependencies..."
apt-get install -y python3 python3-rpi.gpio

# Install vcgencmd if not already available
if ! command -v vcgencmd >/dev/null 2>&1; then
    if apt-cache show raspi-utils-core >/dev/null 2>&1; then
        apt-get install -y raspi-utils-core
    elif apt-cache show libraspberrypi-bin >/dev/null 2>&1; then
        apt-get install -y libraspberrypi-bin
    else
        echo "ERROR: Cannot find a package providing vcgencmd."
        exit 1
    fi
fi

# Verify dependencies
echo "[3/6] Checking dependencies..."
python3 -c "import RPi.GPIO" || {
    echo "ERROR: RPi.GPIO module unavailable."
    exit 1
}

command -v vcgencmd >/dev/null || {
    echo "ERROR: vcgencmd unavailable."
    exit 1
}

# Copy controller
echo "[4/6] Installing fan controller..."
install -m 755 "$SCRIPT_NAME" "$INSTALL_DIR/$SCRIPT_NAME"

# Create systemd service
echo "[5/6] Creating systemd service..."

cat > "/etc/systemd/system/$SERVICE_NAME" <<EOF
[Unit]
Description=52Pi EP-0152 Automatic Fan Control
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/$SCRIPT_NAME
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "[6/6] Enabling and starting service..."

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Verify service
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo ""
    echo "======================================"
    echo " Installation successful!"
    echo " Fan controller is running."
    echo "======================================"
else
    echo ""
    echo "ERROR: Service failed to start."
    echo "Check logs with:"
    echo "journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
