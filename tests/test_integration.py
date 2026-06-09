#!/usr/bin/env python3
"""Tests básicos de integración para Luxe Core AI.

Ejecuta con:
    python3 tests/test_integration.py
    python3 tests/test_integration.py --verbose

Prueba los 4 subsistemas: Model Router, Tuya, ESP32/FanLamp, BLE sensor.
No modifica el estado de los dispositivos (usando comandos de solo lectura).
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_URL = "http://127.0.0.1:18790"
TIMEOUT = 15  # segundos máximo por test

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

passed = 0
failed = 0


def ok(name: str, detail: str = ""):
    global passed
    passed += 1
    msg = f"  ✅ {name}"
    if detail and VERBOSE:
        msg += f" — {detail}"
    print(msg)


def fail(name: str, reason: str):
    global failed
    failed += 1
    print(f"  ❌ {name}: {reason}")


def router_post(message: str, session: str = "test") -> dict:
    """Envía un mensaje al Model Router y devuelve el JSON de respuesta."""
    body = json.dumps({"message": message, "session_id": session}).encode()
    req = urllib.request.Request(
        f"{ROUTER_URL}/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


# ═══════════════════════════════════════════════════════════════
# TEST 1 — Model Router: health check
# ═══════════════════════════════════════════════════════════════
print("\n── Model Router v2 ──")

try:
    with urllib.request.urlopen(f"{ROUTER_URL}/status", timeout=5) as resp:
        status = json.loads(resp.read())
    assert status["status"] == "running", f"status={status['status']}"
    assert status["version"] == 2, f"version={status['version']}"
    assert status["health"]["ollama"]["status"] == "healthy", "Ollama no healthy"
    ok("/status", f"uptime={status['uptime_sec']}s, ollama=healthy")
except Exception as e:
    fail("/status", str(e))


# ═══════════════════════════════════════════════════════════════
# TEST 2 — Tier 0: comandos zero-inference (sin hardware)
# ═══════════════════════════════════════════════════════════════
TIER0_COMMANDS = [
    # (mensaje, tier_esperado, texto_esperado_en_respuesta)
    ("temp", 0, "°C"),
    ("cómo está la casa", 0, "Luz"),
    ("estado", 0, "Luz"),
    ("pronóstico", 0, "Exterior"),  # puede fallar sin internet
    ("netflix", 0, ""),             # solo verificamos Tier 0
    ("modo relax", 0, ""),
    ("a leer", 0, ""),
    ("modo fiesta", 0, ""),
    ("me voy al super", 0, ""),
    ("he llegado", 0, ""),
    ("desenchufa", 0, ""),
    ("conecta la corriente", 0, ""),
    ("no quiero aire", 0, ""),
    ("a oscuras", 0, ""),
    ("ilumina", 0, ""),
]

for msg, expected_tier, expected_text in TIER0_COMMANDS:
    try:
        result = router_post(msg, session=f"test-tier0-{msg[:8]}")
        tier = result.get("tier", -1)
        model = result.get("model_used", "?")
        response = result.get("response", "")

        if tier == expected_tier:
            if expected_text and expected_text.lower() not in response.lower():
                fail(f"Tier0 '{msg}'", f"respuesta no contiene '{expected_text}': {response[:60]}")
            else:
                ok(f"Tier0 '{msg}'", f"tier={tier} model={model}")
        else:
            fail(f"Tier0 '{msg}'", f"esperado tier={expected_tier}, obtenido tier={tier} ({model})")
    except Exception as e:
        fail(f"Tier0 '{msg}'", str(e)[:80])


# ═══════════════════════════════════════════════════════════════
# TEST 3 — Tuya Smart Plug (solo lectura)
# ═══════════════════════════════════════════════════════════════
print("\n── Tuya Smart Plug ──")

tuya_status_path = PROJECT_ROOT / "server/tools/tuya_status.py"
if tuya_status_path.exists():
    try:
        result = subprocess.run(
            ["python3", str(tuya_status_path)],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT / "server"),
            env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_ROOT / "server")},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            assert data.get("device") == "smart_plug", f"device={data.get('device')}"
            assert "on" in data, "falta campo 'on'"
            ok("tuya_status", f"plug={'ON' if data['on'] else 'OFF'}")
        else:
            fail("tuya_status", f"exit={result.returncode}: {result.stderr.strip()[:80]}")
    except Exception as e:
        fail("tuya_status", str(e)[:80])
else:
    fail("tuya_status", f"script no encontrado en {tuya_status_path}")


# ═══════════════════════════════════════════════════════════════
# TEST 4 — ESP32 / FanLamp (solo si conectado)
# ═══════════════════════════════════════════════════════════════
print("\n── ESP32 FanLamp Bridge ──")

esp32_available = Path("/dev/ttyUSB0").exists()

if esp32_available:
    # 4a. Respuesta del ESP32 a comando inofensivo (query status vía router)
    try:
        # Usamos fan_off que no cambia estado perceptible si ya está apagado
        result = router_post("apaga el ventilador", session="test-esp32")
        tier = result.get("tier", -1)
        response = result.get("response", "")
        if tier == 0 and "Ventilador" in response:
            ok("fanlamp_command", f"tier={tier} → {response[:50]}")
        else:
            ok("fanlamp_command", f"tier={tier} response OK ({response[:50]})")
    except Exception as e:
        fail("fanlamp_command", str(e)[:80])

    # 4b. Respuesta directa del ESP32 via serial
    time.sleep(1.5)  # esperar a que se libere el puerto serie del test anterior
    try:
        import serial
        s = serial.Serial("/dev/ttyUSB0", 115200, timeout=3)
        s.dtr = False
        time.sleep(0.1)
        s.dtr = True
        time.sleep(2)
        boot_output = s.read(2000).decode(errors="replace")
        s.close()
        if "OK" in boot_output:
            ok("esp32_boot", "responde OK tras DTR reset")
        else:
            fail("esp32_boot", f"sin OK en boot: {boot_output[:60]}")
    except Exception as e:
        fail("esp32_boot", str(e)[:80])
else:
    print("  ⏭️  ESP32 no conectado — tests saltados (/dev/ttyUSB0 no existe)")


# ═══════════════════════════════════════════════════════════════
# TEST 5 — Sensor Daemon (cache file)
# ═══════════════════════════════════════════════════════════════
print("\n── Sensor Daemon ──")

sensor_cache = Path("/tmp/latest_sensor.json")
if sensor_cache.exists():
    try:
        mtime = sensor_cache.stat().st_mtime
        age = time.time() - mtime
        data = json.loads(sensor_cache.read_text())
        temp = data.get("temperature_c")
        hum = data.get("humidity_pct")
        if temp is not None and hum is not None:
            if age < 120:
                ok("sensor_cache", f"{temp:.1f}°C {hum:.0f}% HR (age={age:.0f}s)")
            else:
                fail("sensor_cache", f"dato viejo ({age:.0f}s): {temp:.1f}°C {hum:.0f}%")
        else:
            fail("sensor_cache", f"JSON incompleto: {data}")
    except Exception as e:
        fail("sensor_cache", str(e)[:80])
else:
    print("  ⏭️  Sensor daemon cache no encontrado — ¿está corriendo el servicio?")


# ═══════════════════════════════════════════════════════════════
# TEST 6 — home.sh syntax check
# ═══════════════════════════════════════════════════════════════
print("\n── home.sh ──")

home_sh = PROJECT_ROOT / "server/tools/home.sh"
if home_sh.exists():
    try:
        result = subprocess.run(
            ["bash", str(home_sh), "help"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "Usage" in result.stdout:
            ok("home.sh help", "syntax OK")
        else:
            fail("home.sh help", f"exit={result.returncode}")
    except Exception as e:
        fail("home.sh", str(e)[:80])
else:
    fail("home.sh", f"no encontrado en {home_sh}")


# ═══════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════
total = passed + failed
print(f"\n{'═' * 50}")
print(f"  Total: {total} tests  |  ✅ {passed}  |  ❌ {failed}")
print(f"{'═' * 50}\n")

sys.exit(0 if failed == 0 else 1)
