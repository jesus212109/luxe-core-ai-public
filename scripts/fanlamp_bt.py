#!/usr/bin/env python3
"""
FanLamp F8808 BLE Advertisement Controller (protocol description).

This file documents the reverse-engineered BLE advertising protocol for the
FanLamp Pro F8808 ceiling fan/light. The actual byte arrays that encode each
command are omitted from this public release as they are the result of original
reverse engineering effort and constitute proprietary protocol knowledge.

Protocol overview:
- The device listens for BLE advertisements (not GATT connections)
- Each command consists of two advertisement groups (G1 + G2), each carrying
  13 UUIDs of 16 bits encoded as service data
- The ESP32 firmware (firmware/esp32_fanlamp/) implements the same protocol
  for environments where direct BLE advertisement emission is not available

Available commands (11 total):
  off         — power off both fan and light
  fan_on      — turn fan on
  fan_off     — turn fan off
  1 through 5 — set fan speed (1 = minimum, 5 = maximum)
  light_on    — turn light on
  light_off   — turn light off
  night       — night mode (dimmed light)

Usage requires root privileges:
  sudo python3 fanlamp_bt.py off
  sudo python3 fanlamp_bt.py 3

For the full protocol data including the specific byte arrays, contact the author
or refer to the private repository (main-private branch).
"""

import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Byte array pairs (G1/G2) for each of the 11 commands.
# REDACTED in the public release — these were obtained through weeks of
# reverse engineering with BLE sniffing and ESP32 experimentation.
# The private repository (main-private branch) contains the full data.
# ---------------------------------------------------------------------------
COMMANDS: dict[str, tuple[str, str]] = {
    # "off":      ("hex_g1", "hex_g2"),
    # "fan_on":   ("hex_g1", "hex_g2"),
    # "fan_off":  ("hex_g1", "hex_g2"),
    # "1":        ("hex_g1", "hex_g2"),
    # "2":        ("hex_g1", "hex_g2"),
    # "3":        ("hex_g1", "hex_g2"),
    # "4":        ("hex_g1", "hex_g2"),
    # "5":        ("hex_g1", "hex_g2"),
    # "light_on": ("hex_g1", "hex_g2"),
    # "light_off":("hex_g1", "hex_g2"),
    # "night":    ("hex_g1", "hex_g2"),
}

SLEEP_BETWEEN_PAIRS = 0.05
REPETITIONS = 5


def send_command(cmd_name: str) -> None:
    """Transmit a BLE advertisement pair for the given command."""
    if cmd_name not in COMMANDS:
        available = ", ".join(sorted(COMMANDS.keys()))
        print(f"Unknown command '{cmd_name}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    group1, group2 = COMMANDS[cmd_name]

    subprocess.run(["sudo", "systemctl", "stop", "bluetoothd"], check=True)
    try:
        for _ in range(REPETITIONS):
            subprocess.run(
                ["sudo", "btmgmt", "add-adv", "-c", "-d", group1, "-u", group1],
                check=True,
            )
            time.sleep(SLEEP_BETWEEN_PAIRS)
            subprocess.run(
                ["sudo", "btmgmt", "add-adv", "-c", "-d", group2, "-u", group2],
                check=True,
            )
            time.sleep(SLEEP_BETWEEN_PAIRS)
    finally:
        subprocess.run(["sudo", "systemctl", "start", "bluetoothd"], check=True)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <command>", file=sys.stderr)
        print(f"Commands: {', '.join(sorted(COMMANDS.keys()))}", file=sys.stderr)
        sys.exit(1)
    send_command(sys.argv[1])


if __name__ == "__main__":
    main()

