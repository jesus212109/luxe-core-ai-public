#!/bin/bash
# ============================================================
# home.sh — Unified home automation CLI for Luxe Core AI
# ============================================================
# Natural language (Spanish) → device commands.
# The AI calls this with a keyword and it routes to the right
# backend (FanLamp ESP32 bridge, Tuya devices, BLE sensors).
#
# Usage:
#   bash server/tools/home.sh fan_off         # Apaga ventilador
#   bash server/tools/home.sh fan_speed 3     # Velocidad 3
#   bash server/tools/home.sh light_on        # Enciende luz techo
#   bash server/tools/home.sh light_off       # Apaga luz techo
#   bash server/tools/home.sh night           # Modo noche
#   bash server/tools/home.sh plug_toggle     # Alterna enchufe
#   bash server/tools/home.sh plug_status     # Estado enchufe
#   bash server/tools/home.sh scan            # Escanea sensores BLE
#
# AI mapping (what to call for Spanish prompts):
#   "apaga el ventilador" / "para el ventilador"     → fan_off
#   "enciende el ventilador" / "pon el ventilador"   → fan_on   (restaura última velocidad)
#   "velocidad 3" / "pon el ventilador al 3"         → fan_speed 3
#   "enciende la luz" / "luz"                        → light_on
#   "apaga la luz" / "luz off"                       → light_off
#   "modo noche" / "noche"                           → night
#   "apaga todo" / "todo off"                        → all_off
#   "enciende todo" / "todo on"                      → all_on
#   "enciende el enchufe" / "enchufe on"             → plug_on
#   "apaga el enchufe" / "enchufe off"               → plug_off
#   "estado del enchufe"                             → plug_status
#   "temperatura" / "sensor" / "BLE"                 → scan
#
# Note: fan_on ('f') restaura la última velocidad con la que se apagó.
#        fan_speed 1 ('1') arranca siempre a velocidad 1 desde cero.
#        fan_off/light_off también preservan estado para restaurar con fan_on/light_on.
#
# Key distinctions (IMPORTANT for AI):
#   fan_off  → solo apaga el ventilador (velocidad 0), luz sigue igual.
#              Guarda última velocidad para restaurar con fan_on.
#   off      → igual que fan_off (ventilador a 0) — NO apaga la luz
#   fan_on   → enciende el ventilador restaurando la última velocidad
#              (distinto de fan_speed 1 que arranca siempre a velocidad 1)
#   light_off → solo apaga la luz, ventilador sigue igual
#   night    → modo noche (luz apagada, ventilador al mínimo)
#   all_off  → apaga TODO (ventilador + luz a la vez, un solo comando)
#   all_on   → enciende TODO (ventilador velocidad 1 + luz)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Usar system Python directamente (venv deprecated)
PYTHON="/usr/bin/python3"

ACTION="${1:-help}"

# ---- FanLamp commands (via ESP32 serial, needs dialout group) ----
fanlamp_cmd() {
    local cmd="$1"
    sg dialout -c "$PYTHON $BASE/scripts/fanlamp_control.py \"$cmd\""
}

# ---- Tuya plug commands ----
tuya_toggle() {
    cd "$BASE/server"
    $PYTHON tools/tuya_toggle.py
}

tuya_set() {
    local target="$1"  # on or off
    cd "$BASE/server"
    $PYTHON tools/tuya_set.py "$target"
}

tuya_status() {
    cd "$BASE/server"
    $PYTHON tools/tuya_status.py
}

# ---- Routing ----
case "$ACTION" in
    # FanLamp — fan-only commands
    fan_off)
        fanlamp_cmd "off"       # CMD_MAP["off"]="F" → ESP32 FAN_OFF pair (fan only)
        ;;
    off)
        fanlamp_cmd "off"       # same as fan_off: fan to 0, light unchanged
        ;;
    fan_on|fan)
        fanlamp_cmd "fan_on"
        ;;
    fan_speed|speed)
        fanlamp_cmd "${2:-1}"   # 0 maps to "F" (fan only off) in CMD_MAP
        ;;
    light_on|light)
        fanlamp_cmd "light_on"
        ;;
    light_off)
        fanlamp_cmd "light_off"
        ;;
    night)
        fanlamp_cmd "night"
        ;;
    # FanLamp combined
    all_off)
        fanlamp_cmd "all_off"   # OFF pair = everything off in one command
        ;;
    all_on)
        fanlamp_cmd "fan_on"
        sleep 1
        fanlamp_cmd "light_on"
        ;;
    # Tuya plug
    plug_toggle|toggle)
        tuya_toggle
        ;;
    plug_on)
        tuya_set "on"
        ;;
    plug_off)
        tuya_set "off"
        ;;
    plug_status|status)
        tuya_status
        ;;
    # BLE scan
    scan|sensors|ble)
        fanlamp_cmd "scan"
        ;;
    help|--help|-h)
        head -30 "$0"
        ;;
    *)
        echo "Unknown action: '$ACTION'"
        echo "Valid: fan_off, fan_on, fan_speed <N>, light_on, light_off, night, all_off, all_on, plug_toggle, plug_status, scan"
        exit 1
        ;;
esac
