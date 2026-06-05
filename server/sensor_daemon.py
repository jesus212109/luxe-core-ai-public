#!/usr/bin/env python3
"""Sensor Daemon — lectura continua del sensor BLE Xiaomi LYWSD03MMC.

Lee el sensor cada N segundos vía ESP32 bridge y almacena:
  /tmp/latest_sensor.json   — última lectura (para consultas instantáneas)
  /tmp/sensor_history.jsonl  — histórico (una línea JSON por lectura)

Usage:
  python3 server/sensor_daemon.py              # foreground, 60s interval
  python3 server/sensor_daemon.py --interval 30  # cada 30s
  python3 server/sensor_daemon.py --once        # una sola lectura y sale

systemd:
  systemctl --user start sensor-daemon
  systemctl --user stop sensor-daemon
  journalctl --user -u sensor-daemon -f
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- Config ---
CONTROL_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "fanlamp_control.py"
)
LATEST_PATH = "/tmp/latest_sensor.json"
HISTORY_PATH = "/tmp/sensor_history.jsonl"
MAX_HISTORY_LINES = 100_000  # ~10MB max, rotar si excede
SCAN_TIMEOUT = 25  # segundos (BLE scan tarda ~12s + boot ESP32)
DEFAULT_INTERVAL = 60  # segundos entre lecturas

logger = logging.getLogger("sensor_daemon")
running = True
NOTIFICATIONS_PATH = "/tmp/luxe_notifications.jsonl"
MAX_NOTIFICATIONS = 50


def _write_notification(result: dict, executed: list[str], ask: bool = False) -> None:
    """Escribe una notificación para el usuario."""
    notif = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "ask" if ask else "action",
        "comfort": result.get("comfort", {}),
        "executed": executed,
        "notifications": result.get("notifications", []),
    }
    try:
        with open(NOTIFICATIONS_PATH, "a") as f:
            f.write(json.dumps(notif, ensure_ascii=False) + "\n")
        # Rotar si hay demasiadas
        with open(NOTIFICATIONS_PATH) as f:
            lines = f.readlines()
        if len(lines) > MAX_NOTIFICATIONS:
            with open(NOTIFICATIONS_PATH, "w") as f:
                f.writelines(lines[-MAX_NOTIFICATIONS:])
    except OSError:
        pass


def _read_sensor() -> dict | None:
    """Lee el sensor vía ESP32 bridge. Retorna dict o None si falla."""
    try:
        result = subprocess.run(
            [sys.executable, CONTROL_SCRIPT, "scan"],
            capture_output=True, text=True, timeout=SCAN_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning(f"ESP32 scan rc={result.returncode}: {result.stderr.strip()[:100]}")
            return None

        data = json.loads(result.stdout)
        sensors = data.get("sensors", [])
        if not sensors:
            error = data.get("error", "no_sensors")
            logger.warning(f"Scan sin sensores: {error}")
            return None

        s = sensors[0]
        return {
            "temperature_c": s["temperature_c"],
            "humidity_pct": s["humidity_pct"],
            "battery_mv": s["battery_mv"],
            "rssi": data.get("rssi"),
            "attempt": data.get("attempt"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except subprocess.TimeoutExpired:
        logger.warning("ESP32 scan timeout")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Error parseando scan: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error inesperado: {e}")
        return None


def _write_latest(reading: dict) -> None:
    """Escribe la última lectura al fichero JSON (atómico)."""
    tmp = LATEST_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reading, f)
    os.replace(tmp, LATEST_PATH)


def _append_history(reading: dict) -> None:
    """Añade una línea al histórico JSONL. Rota si excede MAX_HISTORY_LINES."""
    line = json.dumps(reading, ensure_ascii=False) + "\n"
    with open(HISTORY_PATH, "a") as f:
        f.write(line)

    # Rotar si es muy grande (mantener últimas 50K líneas)
    try:
        if os.path.getsize(HISTORY_PATH) > 10 * 1024 * 1024:  # 10MB
            with open(HISTORY_PATH) as f:
                lines = f.readlines()
            if len(lines) > MAX_HISTORY_LINES:
                keep = lines[-50000:]
                with open(HISTORY_PATH, "w") as f:
                    f.writelines(keep)
                logger.info(f"Histórico rotado: {len(lines)} → {len(keep)} líneas")
    except OSError:
        pass


def _shutdown(signum, frame):
    global running
    logger.info(f"Señal {signum} recibida, cerrando...")
    running = False


def run_once() -> bool:
    """Una sola lectura. Retorna True si éxito."""
    reading = _read_sensor()
    if not reading:
        return False
    
    # Añadir datos exteriores al histórico
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from model_router.smart_advisor import WeatherClient, SmartAdvisor
        outdoor = WeatherClient.get_current()
        if outdoor:
            reading["outdoor_temp_c"] = outdoor["temperature_c"]
            reading["outdoor_humidity_pct"] = outdoor["humidity_pct"]
            reading["outdoor_weather"] = outdoor["weather"]
            reading["outdoor_uv"] = outdoor.get("uv_index")
    except Exception as e:
        logger.debug(f"No se pudo obtener exterior: {e}")
    
    _write_latest(reading)
    _append_history(reading)
    
    # Log
    outdoor_str = ""
    if reading.get("outdoor_temp_c"):
        outdoor_str = f" | 🌍 {reading['outdoor_temp_c']:.0f}°C"
    logger.info(
        f"🌡️ {reading['temperature_c']}°C | "
        f"💧 {reading['humidity_pct']}% | "
        f"🔋 {reading['battery_mv']}mV | "
        f"📶 {reading.get('rssi', '?')}dBm"
        f"{outdoor_str}"
    )
    
    # Ejecutar SmartAdvisor y auto-acciones
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from model_router.smart_advisor import SmartAdvisor
        result = SmartAdvisor.assess_full()
        if result.get("should_act"):
            executed = SmartAdvisor.execute_auto_actions(result)
            if executed:
                logger.info(f"⚡ Auto-acciones: {' | '.join(executed)}")
                # Guardar notificación para el usuario
                _write_notification(result, executed)
        if result.get("should_ask"):
            logger.info(f"❓ SmartAdvisor sugiere: {result.get('notifications', [])}")
            _write_notification(result, [], ask=True)
    except Exception as e:
        logger.debug(f"SmartAdvisor: {e}")
    
    return True


def run_daemon(interval: int = DEFAULT_INTERVAL):
    """Loop principal: leer cada `interval` segundos."""
    logger.info(f"🚀 Sensor Daemon iniciado (intervalo={interval}s)")
    logger.info(f"   Último: {LATEST_PATH}")
    logger.info(f"   Histórico: {HISTORY_PATH}")

    fail_count = 0
    while running:
        ok = run_once()
        if ok:
            fail_count = 0
        else:
            fail_count += 1
            # Backoff si fallos consecutivos
            if fail_count >= 3:
                logger.error(f"❌ {fail_count} fallos consecutivos, pausando 5min...")
                time.sleep(300)
                fail_count = 0

        # Esperar hasta la siguiente lectura (con chequeo de shutdown cada 5s)
        for _ in range(interval // 5):
            if not running:
                break
            time.sleep(5)
        # Resto de segundos si el intervalo no es múltiplo de 5
        remainder = interval % 5
        if remainder > 0 and running:
            time.sleep(remainder)

    logger.info("👋 Sensor Daemon detenido")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sensor Daemon — BLE Xiaomi LYWSD03MMC")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Segundos entre lecturas (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--once", action="store_true",
                        help="Una sola lectura y salir")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Logs detallados")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if args.once:
        ok = run_once()
        print(json.dumps({
            "ok": ok,
            "latest": LATEST_PATH,
            "history": HISTORY_PATH,
        }, indent=2))
        sys.exit(0 if ok else 1)
    else:
        run_daemon(args.interval)


if __name__ == "__main__":
    main()
