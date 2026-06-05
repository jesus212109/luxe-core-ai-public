#!/usr/bin/env python3
"""ESP32 serial bridge controller.

FanLamp (11 commands) + Xiaomi sensor scan.

Usage:
    python3 scripts/fanlamp_control.py off          # FanLamp off
    python3 scripts/fanlamp_control.py 3            # FanLamp speed 3
    python3 scripts/fanlamp_control.py light_on     # FanLamp light on
    python3 scripts/fanlamp_control.py scan         # Read Xiaomi sensor
"""

import json
import serial
import sys
import time

PORT = "/dev/ttyUSB0"
BAUD = 115200

CMD_MAP = {
    "off": "0", "0": "0", "1": "1", "2": "2", "3": "3",
    "4": "4", "5": "5",
    "fan_on": "f", "fan_off": "F",
    "light_on": "l", "light_off": "L",
    "night": "n",
}


def drain_until_ok(ser, timeout=8):
    """Read serial until 'OK' is found (ESP32 boot complete)."""
    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        buf += ser.read(500)
        if b"OK" in buf:
            return
    raise TimeoutError("ESP32 did not respond with OK")


def wait_for_boot(ser=None):
    """Close, reopen, reset ESP32, wait for OK. Returns fresh Serial."""
    if ser:
        ser.close()
        time.sleep(0.5)
    s = serial.Serial(PORT, BAUD, timeout=3)
    s.dtr = False
    time.sleep(0.1)
    s.dtr = True
    drain_until_ok(s, timeout=5)
    return s


def send_cmd(cmd_char: str) -> None:
    ser = serial.Serial(PORT, BAUD, timeout=3)
    time.sleep(0.1)
    ser.write(cmd_char.encode())
    time.sleep(1)
    resp = ser.read(2000).decode(errors="replace").strip()
    ser.close()
    if resp:
        print(resp)


def scan_sensor() -> dict:
    ser = wait_for_boot()
    ser.write(b"s")
    time.sleep(12)
    raw = ser.read(8000).decode(errors="replace").strip()
    ser.close()

    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    result = {"sensors": []}

    for line in lines:
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if "temperature_c" in obj:
                    result["sensors"].append(obj)
                elif "detected" in obj:
                    result.update(obj)
            except json.JSONDecodeError:
                pass
        if line == "OK":
            break

    if not result.get("sensors") and result.get("detected") is not False:
        result["error"] = "gatt_failed"
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1].lower()

    if arg == "scan":
        result = scan_sensor()
        print(json.dumps(result, indent=2))
        return

    if arg not in CMD_MAP:
        names = ", ".join(sorted(CMD_MAP.keys(), key=lambda x: (
            0 if x == "off" else 1 if x.isdigit() else 2, x)))
        print(f"Unknown: {arg}. Valid: {names}")
        sys.exit(1)

    send_cmd(CMD_MAP[arg])


if __name__ == "__main__":
    main()
