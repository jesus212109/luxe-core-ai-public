#!/usr/bin/env python3
import sys, logging
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from integrations.tuya_devices import TuyaSmartPlug, TuyaCommunicationError
logging.basicConfig(level=logging.INFO, format="%(message)s")
plug = TuyaSmartPlug()
try:
    before = plug.is_on()
    plug.toggle()
    after = plug.is_on()
    print(f"plug: {'ON' if before else 'OFF'} -> {'ON' if after else 'OFF'}")
except TuyaCommunicationError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
