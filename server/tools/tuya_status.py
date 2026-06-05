#!/usr/bin/env python3
import json, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from integrations.tuya_devices import TuyaSmartPlug, TuyaCommunicationError
plug = TuyaSmartPlug()
try:
    state = plug.is_on()
    print(json.dumps({"device": "smart_plug", "on": state}))
except TuyaCommunicationError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
