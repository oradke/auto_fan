#!/usr/bin/env python3
"""
52Pi EP-0152 adaptive fan controller for Raspberry Pi 3 / 3B+.

The PI controller adjusts fan speed from CPU temperature error. Its integral
term learns the steady fan-speed requirement as ambient temperature, workload,
or cooling performance changes.

The CSV log records temperature, fan duty and temperature trend. The trend
is diagnostic only: without a workload or ambient sensor, it cannot isolate
fan effectiveness from changes in CPU load or room temperature.
"""

import csv
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import RPi.GPIO as GPIO


# ---------------------------- USER SETTINGS ----------------------------

FAN_PIN = 14                 # BCM GPIO numbering, as used by the EP-0152
PWM_FREQUENCY_HZ = 100

TARGET_TEMP_C = 45.0          # Desired CPU temperature
DEADBAND_C = 1.0              # Ignore errors smaller than +/- 1 C
FAN_START_TEMP_C = TARGET_TEMP_C - 5.0
FAN_STOP_TEMP_C = TARGET_TEMP_C - 10.0
EMERGENCY_TEMP_C = 70.0       # Force 100% fan at or above this temperature

MIN_FAN_DUTY_PERCENT = 30.0   # Adjust if your fan cannot start at 30%
MAX_FAN_DUTY_PERCENT = 100.0

# PI tuning: KP is immediate response; KI changes the learned baseline.
# Increase cautiously. Too much gain can cause fan-speed/temperature cycling.
KP = 4.0                     # Percent duty per degree C
KI = 0.08                    # Percent duty per degree C per second

# Limit ordinary speed changes. Emergency cooling bypasses this limit.
MAX_DUTY_CHANGE_PER_SECOND = 5.0
POLL_INTERVAL_SECONDS = 10.0

LOG_DIR = Path("/home/dietpi/log")
CSV_LOG_FILE = LOG_DIR / "temperature-log.csv"


# ---------------------------- RUNTIME STATE ----------------------------

running = True
fan_pwm = None
fan_duty_percent = 0.0
integral_percent = 0.0
fan_is_running = False
previous_temperature_c = None
previous_sample_time = None


# ---------------------------- HELPER FUNCTIONS ----------------------------

def clamp(value, low, high):
    """Return value limited to the inclusive range low..high."""
    return max(low, min(value, high))


def get_cpu_temperature():
    """Read and parse output such as: temp=48.7'C."""
    result = subprocess.run(
        ["vcgencmd", "measure_temp"],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    value = result.stdout.strip().split("=", 1)[1].split("'", 1)[0]
    return float(value)


def set_fan_duty(duty_percent):
    """Apply PWM duty and keep a copy of the commanded value."""
    global fan_duty_percent
    duty_percent = clamp(float(duty_percent), 0.0, MAX_FAN_DUTY_PERCENT)
    fan_pwm.ChangeDutyCycle(duty_percent)
    fan_duty_percent = duty_percent


def append_log(temp_c, gradient_c_min, duty, mode):
    """
    Append one measurement to CSV. A positive gradient means the CPU is
    warming; a negative gradient means it is cooling. This is not a pure
    fan-efficiency measurement because workload and ambient temperature
    also affect the gradient.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_LOG_FILE.exists()
    with CSV_LOG_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if new_file:
            writer.writerow([
                "timestamp_utc", "cpu_temperature_c",
                "temperature_gradient_c_per_minute", "fan_duty_percent",
                "mode", "integral_baseline_percent",
            ])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            f"{temp_c:.2f}", f"{gradient_c_min:.2f}", f"{duty:.1f}",
            mode, f"{integral_percent:.2f}",
        ])


def shutdown_signal(signum, frame):
    """Tell the main loop to finish cleanly on SIGTERM or Ctrl+C."""
    global running
    running = False


# ---------------------------- PI CONTROL ----------------------------

def calculate_pi_duty(temp_c, elapsed):
    """
    Calculate the requested duty cycle.

    requested duty = KP * temperature error + integral

    The integral accumulates sustained error. If the CPU stays warmer than
    target, it rises and the fan's steady speed increases. If the CPU stays
    cooler than target, it falls. This automatically compensates for seasonal
    ambient-temperature changes without changing the target temperature.
    """
    global integral_percent, fan_is_running

    error = temp_c - TARGET_TEMP_C

    # Deadband prevents tiny sensor fluctuations from constantly changing
    # the integral term and fan speed.
    if abs(error) <= DEADBAND_C:
        error = 0.0

    # When stopped, wait for the start threshold. Initialize the integral
    # so the first PI output is at least the minimum reliable fan speed.
    if not fan_is_running:
        if temp_c < FAN_START_TEMP_C:
            # Keep the learned baseline while the fan is off.
            return 0.0, "fan-off"

        fan_is_running = True

        # If there is no learned baseline yet, initialize the PI output at
        # the minimum reliable fan speed. Otherwise retain the learned
        # baseline and let feedback adjust it.
        if integral_percent < 0.1:
            integral_percent = clamp(
                MIN_FAN_DUTY_PERCENT - KP * error,
                0.0,
                MAX_FAN_DUTY_PERCENT,
            )

    proportional = KP * error
    candidate_integral = clamp(
        integral_percent + KI * error * elapsed,
        0.0,
        MAX_FAN_DUTY_PERCENT,
    )
    candidate_output = proportional + candidate_integral

    # Anti-windup: don't keep accumulating in a direction that would push
    # an already saturated output further beyond its limits.
    pushing_high = candidate_output > MAX_FAN_DUTY_PERCENT and error > 0
    pushing_low = candidate_output < 0.0 and error < 0
    if not (pushing_high or pushing_low):
        integral_percent = candidate_integral

    requested = clamp(
        proportional + integral_percent,
        0.0,
        MAX_FAN_DUTY_PERCENT,
    )

    # Use separate start and stop temperatures to prevent rapid on/off
    # switching. Only stop if the CPU is cool AND requested duty is low.
    if temp_c <= FAN_STOP_TEMP_C and requested <= MIN_FAN_DUTY_PERCENT:
        fan_is_running = False
        # Retain the learned baseline. It will be useful next time the fan
        # starts, and will continue adapting when the CPU warms up again.
        return 0.0, "fan-off"

    return max(MIN_FAN_DUTY_PERCENT, requested), "pi-control"


def limit_speed_change(requested, elapsed):
    """Slew-limit ordinary duty changes to avoid abrupt fan-speed changes."""
    max_change = MAX_DUTY_CHANGE_PER_SECOND * elapsed
    difference = requested - fan_duty_percent
    return fan_duty_percent + clamp(difference, -max_change, max_change)


# ---------------------------- MAIN PROGRAM ----------------------------

def main():
    global fan_pwm, fan_duty_percent, fan_is_running
    global previous_temperature_c, previous_sample_time

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(FAN_PIN, GPIO.OUT)
    fan_pwm = GPIO.PWM(FAN_PIN, PWM_FREQUENCY_HZ)

    # Brief full-speed startup provides cooling while Python/GPIO initialize.
    fan_pwm.start(100.0)
    fan_duty_percent = 100.0
    time.sleep(1.0)
    # Keep full cooling until the first temperature sample is available.
    # The logical state remains "off" so the controller can initialize its
    # first PI fan start correctly. The first decision is not slew-limited.
    fan_is_running = False
    first_control_sample = True

    previous_sample_time = time.monotonic()

    print("52Pi EP-0152 adaptive fan controller started.")
    print(f"Target {TARGET_TEMP_C:.1f} C; emergency {EMERGENCY_TEMP_C:.1f} C")
    print(f"Poll interval {POLL_INTERVAL_SECONDS:.1f} seconds")
    print(f"CSV log: {CSV_LOG_FILE}")

    while running:
        loop_start = time.monotonic()
        elapsed = max(0.1, loop_start - previous_sample_time)
        previous_sample_time = loop_start

        try:
            temp_c = get_cpu_temperature()
        except Exception as error:
            # Fail safe: never turn the fan off if the temperature sensor
            # command fails. Retry on the next polling interval.
            set_fan_duty(MAX_FAN_DUTY_PERCENT)
            fan_is_running = True
            print(f"Temperature read error: {error}; fan forced to 100%.")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # Calculate observed temperature trend in degrees C per minute.
        if previous_temperature_c is None:
            gradient = 0.0
        else:
            gradient = (temp_c - previous_temperature_c) / elapsed * 60.0
        previous_temperature_c = temp_c

        if temp_c >= EMERGENCY_TEMP_C:
            # Emergency cooling overrides PI and the normal slew limit.
            requested = MAX_FAN_DUTY_PERCENT
            fan_is_running = True
            mode = "EMERGENCY"
        else:
            requested, mode = calculate_pi_duty(temp_c, elapsed)

            if first_control_sample:
                # On startup, move directly from the temporary 100% setting
                # to the first calculated setting. Do not ramp down over
                # several samples just because startup cooling was used.
                pass
            elif requested <= 0.0:
                # A deliberate fan-off decision should stop PWM immediately;
                # don't slew slowly through duty cycles too low to turn the fan.
                requested = 0.0
            elif fan_duty_percent == 0.0:
                requested = max(MIN_FAN_DUTY_PERCENT, requested)
            else:
                requested = limit_speed_change(requested, elapsed)

        first_control_sample = False
        set_fan_duty(requested)

        print(
            f"CPU {temp_c:5.1f} C | target {TARGET_TEMP_C:.1f} C | "
            f"trend {gradient:+5.1f} C/min | fan {fan_duty_percent:5.1f}% | "
            f"learned baseline {integral_percent:5.1f}% | {mode}"
        )

        append_log(temp_c, gradient, fan_duty_percent, mode)

        # Keep a consistent interval, accounting for time spent processing.
        remaining = POLL_INTERVAL_SECONDS - (time.monotonic() - loop_start)
        time.sleep(max(0.0, remaining))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_signal)
    signal.signal(signal.SIGINT, shutdown_signal)
    try:
        main()
    finally:
        # Release GPIO resources even if an unexpected error occurs.
        if fan_pwm is not None:
            try:
                fan_pwm.stop()
            except Exception:
                pass
        GPIO.cleanup()
        print("Fan controller stopped; GPIO cleaned up.")
