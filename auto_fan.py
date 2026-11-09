#!/usr/bin/env python3

import RPi.GPIO as GPIO
import subprocess
import time

FAN_PIN = 14
PWM_FREQUENCY = 100

# Temperature / fan speed curve
FAN_CURVE = [
    (40, 30),
    (45, 40),
    (50, 55),
    (55, 70),
    (60, 85),
    (65, 100)
]

OFF_TEMP = 38
POLL_INTERVAL = 5

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(FAN_PIN, GPIO.OUT)

fan = GPIO.PWM(FAN_PIN, PWM_FREQUENCY)
fan.start(0)

fan_on = False

def get_cpu_temp():
    output = subprocess.check_output(
        ["vcgencmd", "measure_temp"]
    ).decode()
    return float(output.split("=")[1].split("'")[0])

def get_fan_speed(temp):
    if temp >= FAN_CURVE[-1][0]:
        return 100

    for i in range(len(FAN_CURVE) - 1):
        t1, s1 = FAN_CURVE[i]
        t2, s2 = FAN_CURVE[i + 1]

        if t1 <= temp < t2:
            ratio = (temp - t1) / (t2 - t1)
            return s1 + ratio * (s2 - s1)

    return FAN_CURVE[0][1]

try:
    while True:
        temp = get_cpu_temp()

        if fan_on:
            if temp < OFF_TEMP:
                speed = 0
                fan_on = False
            else:
                speed = get_fan_speed(temp)
        else:
            if temp >= 40:
                fan_on = True
                speed = get_fan_speed(temp)
            else:
                speed = 0

        fan.ChangeDutyCycle(speed)

        print(
            f"CPU: {temp:.1f}°C | "
            f"Fan: {speed:.0f}%"
        )

        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    pass

finally:
    fan.stop()
    GPIO.cleanup()