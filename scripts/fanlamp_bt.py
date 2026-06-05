#!/usr/bin/env python3
"""FanLamp controller via BLE advertising (btmgmt, no ESP32).

Requires: sudo, btmgmt (from bluez)
Usage:
    sudo python3 scripts/fanlamp_bt.py off
    sudo python3 scripts/fanlamp_bt.py 1
"""

import os
import subprocess
import sys
import time


def detect_bt_index() -> int:
    result = subprocess.run(
        "btmgmt info 2>&1 | grep -oP 'hci\\K[0-9]+' | head -1",
        shell=True, capture_output=True, text=True, timeout=5,
    )
    if result.stdout.strip():
        return int(result.stdout.strip())
    return 0


BT_INDEX = detect_bt_index()


PATTERNS = {
    "off": [
        "0201051B03F0082082364DFD5F0632DB861E3A770F9180FFA221C6532B7C8B",
        "0201051B0377F8B65F2B5E00FC31512E17B208240AD1FC71AFF45982328268",
    ],
    "1": [
        "0201051B03F00820823646FD5F0632DB861E64770FB181FFC286C6532B5E4A",
        "0201051B0377F8B65F2B5E00FC31519417B288440A3DFC459BF46DA06F4691",
    ],
    "2": [
        "0201051B03F00820823659FD5F0632DB861E64770FB182FFBACFC6532BE08A",
        "0201051B0377F8B65F2B5E00FC31519417B248440ABDFC29F7F40192826B7C",
    ],
    "3": [
        "0201051B03F00820823658FD5F0632DB861E64770FB183FFB14BC6532BA817",
        "0201051B0377F8B65F2B5E00FC31519417B2C8440A7DFC5987F471E6B64AF0",
    ],
    "4": [
        "0201051B03F0082082365BFD5F0632DB861E64770FB184FF6A5EC6532B1300",
        "0201051B0377F8B65F2B5E00FC31519417B228440AFDFC24FAF40C62891A42",
    ],
    "5": [
        "0201051B03F0082082365AFD5F0632DB861E64770FB185FFDA10C6532B9584",
        "0201051B0377F8B65F2B5E00FC31519417B2A8440A1DFC5B85F473F32410FB",
    ],
    "fan_on": [
        "0201051B03F00820823638FD5F0632DB861E64770FB185FF55D2C6532BA190",
        "0201051B0377F8B65F2B5E00FC31519417B2A8440A7BFCE638F4CE42FCB3EC",
    ],
    "fan_off": [
        "0201051B03F00820823632FD5F0632DB861E64770FB180FFAB16C6532B8C5C",
        "0201051B0377F8B65F2B5E00FC31515417B208240A0BFC13CDF43BCEEB29B5",
    ],
    "light_off": [
        "0201051B03F0082082363BFD5F0632DB861E44770F9180FF5CE2C6532B81CE",
        "0201051B0377F8B65F2B5E00FC31515017B208240AFBFC5886F470A2A4E7F5",
    ],
    "light_on": [
        "0201051B03F00820823635FD5F0632DB861E45770F9180FF8192C6532B1B36",
        "0201051B0377F8B65F2B5E00FC3151D017B208240A8BFC09D7F4212C75CBC9",
    ],
    "night": [
        "0201051B03F0082082363AFD5F0632DB861E76770F9180FF1232C6532BA939",
        "0201051B0377F8B65F2B5E00FC31511C17B208240A1BFC21FFF4091C980351",
    ],
}


def run_btmgmt(args: str) -> str:
    """Run btmgmt with list args. Uses setsid to avoid TTY hang."""
    full_args = ["btmgmt", "--index", str(BT_INDEX)] + args
    r = subprocess.run(full_args, capture_output=True, text=True, timeout=10,
                       preexec_fn=os.setsid)
    return r.stdout + r.stderr


def send_pair(g1_hex: str, g2_hex: str) -> None:
    """Send G1+G2 alternating 4 times. One instance at a time."""
    for _ in range(4):
        run_btmgmt(["add-adv", "-d", g1_hex, "-t", "2", "-c", "1"])
        time.sleep(0.25)
        run_btmgmt(["rm-adv", "1"])
        run_btmgmt(["add-adv", "-d", g2_hex, "-t", "2", "-c", "1"])
        time.sleep(0.25)
        run_btmgmt(["rm-adv", "1"])
    time.sleep(2)


def main():
    if os.geteuid() != 0:
        print("ERROR: This script requires root. Run with: sudo python3 fanlamp_bt.py <cmd>")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd not in PATTERNS:
        print(f"Unknown: {cmd}. Use: off, fan_on, fan_off, light_on, light_off, night, 1-5")
        sys.exit(1)

    print(f"Using Bluetooth adapter hci{BT_INDEX}")
    run_btmgmt(["power", "on"])

    g1, g2 = PATTERNS[cmd]
    print(f"Sending: {cmd}")
    send_pair(g1, g2)
    print("Done.")


if __name__ == "__main__":
    main()
