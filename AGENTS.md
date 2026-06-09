# AGENTS.md — Luxe Core AI

## Identity
- **Project:** TFG (Bachelor's Thesis) — Local Edge AI home automation ecosystem
- **Author:** Jesús Fernández López (UCO, Ingeniería Informática)
- **Architecture:** Node.js orchestrator (OpenClaw npm/lobster) + Python device drivers + C++20 ESP32 LIN bridge.

## Engineering profile
Edge AI systems engineer. Data sovereignty and zero cloud dependency are absolute priorities. Structured academic tone, humanised: no unnecessary jargon, as an excellent student would.

## Language
- **LaTeX (TFG memory):** compulsory Spanish.
- **Code:** English.

## Architecture overview
```
OpenClaw Gateway (Node.js 24, port 18789, LAN 192.168.1.0/24)
  │
  ├── Telegram channel (native)
  ├── Web dashboard (LAN)
  ├── Web search (Gemini, native)
  └── exec ─── server/tools/ wrappers ─── Python device drivers
                                               ├── integrations/tuya_devices.py
                                               ├── integrations/ble_sensors.py
                                               ├── integrations/hvac_bridge.py (stub)
                                               └── scripts/fanlamp_bt.py
```

## Environment
- **Server (Torre Ryzen):** Ubuntu 24.04 LTS, Node.js 24 (npm global), Python 3.12 (venv)
- **Python virtual env:** `server/venv/` (deprecated, being removed)
- **OpenClaw gateway:** `systemctl --user openclaw-gateway` (port 18789, LAN bind)
- **Ollama:** `localhost:11434` (models: `qwen3-coder`, `llama3.2`, `bge-m3`)
- **Dashboard:** `http://192.168.1.50:18789`

## Developer commands

```bash
# 1. Device driver dependencies only (Python)
python3 -m venv server/venv
source server/venv/bin/activate
pip install tinytuya bleak

# 2. OpenClaw is already installed globally via curl openclaw.ai/install.sh
#    Gateway runs as a systemd user service

# 3. Test device drivers
python server/tools/tuya_toggle.py
python server/tools/tuya_status.py
python server/tools/ble_scan.py
sudo bash server/tools/fanlamp.sh off
```

## Project layout
```
luxe-core-ai/
├── server/
│   ├── integrations/      ← Device drivers: Tuya, BLE, HVAC (stub)
│   ├── tools/             ← CLI wrappers invoked by OpenClaw exec
│   └── requirements.txt   ← Only tinytuya + bleak
├── scripts/               ← fanlamp_control.py (ESP32 serial) + fanlamp_bt.py (legacy) + fan_investigation.py
├── firmware/
│   ├── Enchufe/           ← Tuya device configs + dumps
│   ├── esp32_fanlamp/     ← PlatformIO project for FanLamp BLE bridge
│   └── btsnoop_fanlamp.log ← BLE capture (FanLamp reverse engineering)
├── docs/                  ← TFG LaTeX memory + ADR decision records
├── meta/                  ← Roadmap, TODO, validation notes
├── AGENTS.md              ← This file
└── README.md
```

## Hardware integrations (do not break these)
- **Tuya devices** (`firmware/Enchufe/devices.json`): smart plug + smart bulb with DPS mappings, local keys, MACs. Uses `tinytuya` protocol 3.5.
- **HVAC (General/Fujitsu)** via LIN bus on ESP32 DevKit V1 + LINTTL3 transceiver (future).
- **Xiaomi BLE sensors** (LYWSD03MMC): GATT direct to characteristic `ebe0ccc1` on service `ebe0ccb0`. No flash, no bind key, no cloud. Format: temp (int16 LE x100), humidity (uint8), battery mV (uint16 LE).
- **FanLamp F8808:** BLE advertisements (not GATT). 13 UUIDs per command, 11 commands mapped. Control via `scripts/fanlamp_control.py` over USB serial to ESP32 bridge (PlatformIO project at `firmware/esp32_fanlamp/`). ESP32 sends raw BLE advertisement bytes via its onboard BT radio.

## Known issues
- `server/integrations/hvac_bridge.py` — stub, ESP32 firmware not yet implemented.
- Ollama models `qwen3-coder` and `llama3.2` not yet pulled (pending disk space / selection).
- DNS via `resolvectl` not persistent — need `/etc/systemd/resolved.conf.d/dns.conf`.
- FanLamp protocol reverse engineering incomplete (would need nRF52840 dongle + Wireshark), but all 11 commands work via ESP32 bridge.

## docs/ LaTeX
- Compile: `bash docs/compile_docs.sh` (requires `pdflatex` + `biber`, TeX Live 2023).
- Appendices A (user manual), B (code listing), C (tests) are TODO.
