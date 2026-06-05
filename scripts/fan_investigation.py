"""FanLamp Pro BLE reverse-engineering probe.

Connects to the target ceiling-fan controller and dumps every GATT service,
characteristic, descriptor, property set and (when readable) initial value.
The goal is to harvest enough information to reconstruct the FanLamp Pro
control protocol without depending on the vendor's app.

Usage:
    python scripts/fan_investigation.py [--mac AA:BB:CC:DD:EE:FF] [--timeout 20]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakDeviceNotFoundError, BleakError

TARGET_MAC = "A1:B3:13:9A:A6:1A"
DEFAULT_SCAN_TIMEOUT = 15.0
DEFAULT_CONNECT_TIMEOUT = 20.0

LOGGER = logging.getLogger("fan_investigation")


async def discover(mac: str, timeout: float):
    LOGGER.info("Scanning for %s (timeout=%.1fs)", mac, timeout)
    device = await BleakScanner.find_device_by_address(mac, timeout=timeout)
    if device is None:
        LOGGER.warning("Device %s not found during active scan; trying direct connect anyway.", mac)
    else:
        LOGGER.info("Found %s : name=%r rssi=%s", device.address, device.name, getattr(device, "rssi", "n/a"))
    return device


async def enumerate_gatt(client: BleakClient) -> None:
    services = client.services
    if services is None:
        LOGGER.error("No services exposed by device.")
        return

    LOGGER.info("=== GATT Services Enumeration ===")
    for service in services:
        LOGGER.info("Service: %s  uuid=%s  description=%s", service.handle, service.uuid, service.description)
        for char in service.characteristics:
            props = ",".join(char.properties)
            LOGGER.info(
                "  Char: handle=%s uuid=%s props=[%s] description=%s",
                char.handle,
                char.uuid,
                props,
                char.description,
            )
            if "read" in char.properties:
                await _safe_read(client, char.uuid)
            for descriptor in char.descriptors:
                LOGGER.info(
                    "    Descriptor: handle=%s uuid=%s",
                    descriptor.handle,
                    descriptor.uuid,
                )


async def _safe_read(client: BleakClient, uuid: str) -> None:
    try:
        value = await client.read_gatt_char(uuid)
    except BleakError as exc:
        LOGGER.info("    Read[%s] -> error: %s", uuid, exc)
        return
    LOGGER.info("    Read[%s] -> %s (hex=%s)", uuid, value, value.hex())


async def investigate(mac: str, scan_timeout: float, connect_timeout: float) -> int:
    await discover(mac, scan_timeout)

    LOGGER.info("Connecting to %s ...", mac)
    try:
        async with BleakClient(mac, timeout=connect_timeout) as client:
            connected = client.is_connected
            LOGGER.info("Connected: %s", connected)
            if not connected:
                LOGGER.error("Client reported not connected after context entry.")
                return 2
            await asyncio.sleep(2.0)
            await enumerate_gatt(client)
    except BleakDeviceNotFoundError as exc:
        LOGGER.error("Device not found: %s", exc)
        return 3
    except BleakError as exc:
        LOGGER.error("BLE error while talking to %s: %s", mac, exc)
        return 4
    except asyncio.TimeoutError:
        LOGGER.error("Timed out connecting to %s after %.1fs", mac, connect_timeout)
        return 5
    return 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FanLamp Pro BLE service enumerator")
    parser.add_argument("--mac", default=TARGET_MAC, help="Target BLE MAC address")
    parser.add_argument("--scan-timeout", type=float, default=DEFAULT_SCAN_TIMEOUT)
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT)
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    try:
        return asyncio.run(
            investigate(args.mac, args.scan_timeout, args.connect_timeout)
        )
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
