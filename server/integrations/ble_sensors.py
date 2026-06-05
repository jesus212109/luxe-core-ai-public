"""
BLE sensor integration via ESP32 serial bridge.

Reads temperature and humidity from Xiaomi LYWSD03MMC sensors
over GATT without pairing, using the ESP32 BLE bridge.

Protocol (ebe0ccc1, 5 bytes LE):
  bytes 0-1: temperature * 100 (int16, little-endian)
  byte 2:    relative humidity (%)
  bytes 3-4: battery voltage in mV (uint16, little-endian)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

LOGGER = logging.getLogger("ble_sensors")

CACHE_PATH = "/tmp/ble_sensor_cache.json"
CACHE_MAX_AGE = 900  # 15 min
CONTROL_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "fanlamp_control.py"
)


@dataclass
class SensorReading:
    address: str
    name: Optional[str]
    temperature_c: float
    humidity_pct: int
    battery_mv: int
    rssi: Optional[int] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def read_cache() -> Optional[dict]:
    """Return cached reading if fresh enough."""
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        age = time.time() - data.get("cached_at", 0)
        if age < CACHE_MAX_AGE:
            return data
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def write_cache(reading: dict) -> None:
    """Write reading to cache file."""
    data = {**reading, "cached_at": time.time()}
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)


def read_via_esp32() -> Optional[dict]:
    """Trigger a scan on the ESP32 bridge and parse the result."""
    try:
        result = subprocess.run(
            [sys.executable, CONTROL_SCRIPT, "scan"],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            LOGGER.error("ESP32 scan failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return None

        data = json.loads(result.stdout)
        sensors = data.get("sensors", [])
        if sensors:
            s = sensors[0]
            reading = {
                "address": "A4:C1:38:84:03:1C",
                "temperature_c": s["temperature_c"],
                "humidity_pct": s["humidity_pct"],
                "battery_mv": s["battery_mv"],
                "rssi": data.get("rssi"),
            }
            write_cache(reading)
            return reading

        LOGGER.warning("ESP32 scan found no sensors: %s", data.get("error", "unknown"))
        return None

    except subprocess.TimeoutExpired:
        LOGGER.error("ESP32 scan timed out")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        LOGGER.error("Failed to parse ESP32 output: %s", e)
        return None


def read_sensor_cli(force: bool = False) -> dict:
    """CLI entry: return cached reading or perform fresh scan via ESP32."""
    if not force:
        cached = read_cache()
        if cached:
            return {"sensors": [cached], "source": "cache"}

    result = read_via_esp32()
    if result:
        return {"sensors": [result], "source": "live"}
    return {"sensors": [], "source": "no_data", "error": "esp32_scan_failed"}


def main() -> None:
    """Direct CLI entry."""
    force = "--force" in sys.argv or "-f" in sys.argv
    result = read_sensor_cli(force=force)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
