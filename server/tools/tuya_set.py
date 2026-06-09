#!/usr/bin/env python3
"""Set Tuya smart plug state (on/off) — absolute, idempotent, no toggle."""
import sys, logging
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from integrations.tuya_devices import TuyaSmartPlug, TuyaCommunicationError

logging.basicConfig(level=logging.INFO, format="%(message)s")
plug = TuyaSmartPlug()

if len(sys.argv) < 2 or sys.argv[1].lower() not in ("on", "off"):
    print("Usage: tuya_set.py on|off", file=sys.stderr)
    sys.exit(1)

target = sys.argv[1].lower() == "on"

try:
    # set_state is absolute (not toggle). Calling set_state(True) on an
    # already-ON plug is a no-op. No need to read is_on() first — avoids
    # the race condition where is_on() returns None on a slow LAN.
    plug.set_state(target)
    print(f"plug: {'ON' if target else 'OFF'}")
except TuyaCommunicationError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
