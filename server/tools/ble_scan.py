#!/usr/bin/env python3
"""BLE sensor reader via ESP32 bridge.

Usage:
    python3 server/tools/ble_scan.py          # try cache first, fallback to ESP32
    python3 server/tools/ble_scan.py --force  # force fresh scan via ESP32
"""

import json, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from integrations.ble_sensors import read_sensor_cli

def main():
    force = "--force" in sys.argv or "-f" in sys.argv
    result = read_sensor_cli(force=force)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
