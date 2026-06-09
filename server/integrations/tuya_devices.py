"""Tuya local LAN integration for the air-gapped Luxe Core AI ecosystem.

This module wraps `tinytuya` (protocol 3.5) to drive the Smart Plug paired via
the documented Hotspot Spoofing onboarding. All traffic stays inside the
isolated 192.168.1.0/24 subnet — no cloud calls are issued at runtime.

NOTE: Device credentials are read from environment variables. Set TUYA_DEVICE_ID,
TUYA_LOCAL_KEY, and TUYA_PLUG_IP before running. See .env.example for details.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from typing import Any, Optional

import tinytuya

LOGGER = logging.getLogger(__name__)

# Device credentials — set via environment variables.
# These were removed from the public release for security.
# To configure, copy .env.example to .env and fill in your values.
SMART_PLUG_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
SMART_PLUG_LOCAL_KEY = os.environ.get("TUYA_LOCAL_KEY", "")
SMART_PLUG_IP = os.environ.get("TUYA_PLUG_IP", "192.168.1.100")
TUYA_PROTOCOL_VERSION = 3.5
SWITCH_DP = "1"
DEFAULT_TIMEOUT_SECONDS = 5.0


class TuyaCommunicationError(RuntimeError):
    """Raised when a Tuya device cannot be reached on the local network."""


@dataclass(frozen=True)
class TuyaDeviceConfig:
    device_id: str
    local_key: str
    address: str
    version: float = TUYA_PROTOCOL_VERSION
    timeout: float = DEFAULT_TIMEOUT_SECONDS


SMART_PLUG_CONFIG = TuyaDeviceConfig(
    device_id=SMART_PLUG_DEVICE_ID,
    local_key=SMART_PLUG_LOCAL_KEY,
    address=SMART_PLUG_IP,
)


class TuyaSmartPlug:
    """Thin wrapper around `tinytuya.OutletDevice` for the air-gapped plug."""

    def __init__(self, config: TuyaDeviceConfig = SMART_PLUG_CONFIG) -> None:
        self._config = config
        self._device = tinytuya.OutletDevice(
            dev_id=config.device_id,
            address=config.address,
            local_key=config.local_key,
            version=config.version,
        )
        self._device.set_socketTimeout(config.timeout)

    def status(self) -> dict[str, Any]:
        payload = self._call(self._device.status)
        dps = payload.get("dps") or {}
        return dps

    def is_on(self) -> Optional[bool]:
        dps = self.status()
        value = dps.get(SWITCH_DP)
        if isinstance(value, bool):
            return value
        return None

    def set_state(self, on: bool) -> dict[str, Any]:
        LOGGER.info("Setting plug %s -> %s", self._config.address, "ON" if on else "OFF")
        return self._call(self._device.set_status, on, SWITCH_DP)

    def toggle(self) -> dict[str, Any]:
        current = self.is_on()
        target = not bool(current)
        return self.set_state(target)

    def _call(self, fn, *args, **kwargs) -> dict[str, Any]:
        try:
            result = fn(*args, **kwargs)
        except socket.timeout as exc:
            raise TuyaCommunicationError(
                f"Timeout talking to Tuya device at {self._config.address}"
            ) from exc
        except OSError as exc:
            raise TuyaCommunicationError(
                f"Network error reaching Tuya device at {self._config.address}: {exc}"
            ) from exc

        if isinstance(result, dict) and "Error" in result:
            raise TuyaCommunicationError(
                f"Tuya device reported error: {result.get('Error')} "
                f"(payload={result.get('Payload')})"
            )
        if not isinstance(result, dict):
            raise TuyaCommunicationError(f"Unexpected response from device: {result!r}")
        return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    plug = TuyaSmartPlug()
    try:
        before = plug.is_on()
        LOGGER.info("Current plug state: %s", before)
        plug.toggle()
        after = plug.is_on()
        LOGGER.info("New plug state: %s", after)
    except TuyaCommunicationError as exc:
        LOGGER.error("Failed to toggle plug: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
