# 52Pi EP-0152 Automatic Fan Control

Temperature-based PWM fan control for a Raspberry Pi 3 fitted with the 52Pi EP-0152 cooling HAT Raspberry Pi Fan Expansion Board Plus 0.91 OLED V1.0 (https://wiki.52pi.com/index.php?title=EP-0152).

The controller reads the CPU temperature and adjusts the fan speed using a configurable temperature/speed curve. The fan remains off while the CPU is cool and ramps up as the temperature rises.

## Features

- Automatic CPU-temperature-based fan control
- Configurable PWM fan-speed curve
- Runs as a systemd service
- Starts automatically at boot
- Simple installation and removal scripts

## Requirements

- Raspberry Pi 3
- 52Pi EP-0152 cooling HAT and fan
- Raspberry Pi OS or a compatible DietPi installation
- `systemd`
- Python 3
- `RPi.GPIO`
- `vcgencmd`

The installer attempts to install the required packages using APT. Package availability can vary by operating-system release. The Python script uses `RPi.GPIO` for PWM output and `vcgencmd measure_temp` to read the CPU temperature.

## Files

```text
52pi-fan/
├── 52pi-fan.py
├── install.sh
├── uninstall.sh
└── README.md
```

Keep all three scripts in the same directory before installation.

## Installation

Make the installer executable and run it as root:

```bash
chmod +x install.sh
sudo ./install.sh
```

The installer:

1. Updates the APT package index.
2. Installs Python GPIO support and the utility providing `vcgencmd`.
3. Checks that the Python GPIO module and `vcgencmd` are available.
4. Copies `52pi-fan.py` to `/usr/local/bin/`.
5. Creates `/etc/systemd/system/52pi-fan.service`.
6. Enables and starts the service.

Check the service:

```bash
sudo systemctl status 52pi-fan.service
```

## Fan-speed curve

The default curve in `52pi-fan.py` is:

| CPU temperature | Fan speed |
|---:|---:|
| Below 40°C | Off |
| 40°C | 30% |
| 45°C | 40% |
| 50°C | 55% |
| 55°C | 70% |
| 60°C | 85% |
| 65°C and above | 100% |

The controller interpolates between the defined points to produce gradual changes in fan speed. It checks the temperature every five seconds.

The fan switches off below 38°C after it has been running. It starts again when the temperature reaches 40°C. This hysteresis helps prevent rapid on/off switching near the start temperature.

To change the behaviour, edit the `FAN_CURVE`, `OFF_TEMP`, and `POLL_INTERVAL` values near the top of `52pi-fan.py`. Make sure the fan can reliably start at the lowest configured duty cycle. Some fans need a higher minimum speed.

After changing the installed script, restart the service:

```bash
sudo systemctl restart 52pi-fan.service
```

## Monitoring and service commands

Follow the controller's output, including CPU temperature and fan duty cycle:

```bash
sudo journalctl -u 52pi-fan.service -f
```

Other useful commands:

```bash
# Start
sudo systemctl start 52pi-fan.service

# Stop
sudo systemctl stop 52pi-fan.service

# Restart
sudo systemctl restart 52pi-fan.service

# Enable at boot
sudo systemctl enable 52pi-fan.service

# Disable at boot
sudo systemctl disable 52pi-fan.service
```

## Uninstallation

Run:

```bash
chmod +x uninstall.sh
sudo ./uninstall.sh
```

The uninstaller stops and disables the service, removes the systemd service file and installed Python script, and reloads systemd.

**The uninstaller intentionally does not remove Python or GPIO packages.** They may be used by other applications. Remove them separately only if you are sure they are no longer needed.

## Troubleshooting

### Service does not start

Inspect the service status and logs:

```bash
sudo systemctl status 52pi-fan.service
sudo journalctl -u 52pi-fan.service -n 50
```

### GPIO module cannot be imported

Check whether the module is available to the system Python:

```bash
python3 -c "import RPi.GPIO; print('RPi.GPIO OK')"
```

If the import fails, check package availability for your OS:

```bash
apt policy python3-rpi.gpio
```

### `vcgencmd` is not found

Check whether the command is installed and available:

```bash
command -v vcgencmd
vcgencmd measure_temp
```

The package providing `vcgencmd` varies between Raspberry Pi OS and DietPi releases.

### Fan does not start at low duty cycle

Some fans cannot start reliably at a low PWM duty cycle. Increase the first fan-speed value in `FAN_CURVE` (for example, from 30% to 40% or higher), and test that the fan starts consistently.

## Notes

- This project is intended for the 52Pi EP-0152 fan-control hardware.
- The script uses BCM GPIO numbering and GPIO14 for PWM, as specified by the applicable EP-0152 setup.
- Do not run another fan-control service at the same time; competing processes can interfere with PWM control.
- Monitor CPU temperature under load after installation and adjust the curve if necessary.
- The fan curve is a starting point, not a substitute for checking the cooling performance of your own hardware.

## License

Choose and add a license before redistributing this project. If you publish it on GitHub, include the corresponding `LICENSE` file.
