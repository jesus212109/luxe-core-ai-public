"""
Smart Advisor v2 — Recomendaciones inteligentes con auto-acción.

Decisiones (Opción C corregida):
  1. Sin presencia → no actuar (ahorrar energía)
  2. Interior vs exterior → ventana/persiana
  3. +1 zona → PREGUNTAR (cambio pequeño, pregunta primero)
  4. +2+ zonas → ACTUAR (cambio brusco, actúa automático)
  5. Excepción: si el usuario subió manualmente el ventilador y empeora,
     auto-subir (respeta la intención del usuario)
  6. Tracking de tendencia: ¿subiendo o bajando la temperatura?
"""

import json
import logging
import os
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional

from model_router.comfort import ComfortAdvisor

logger = logging.getLogger("smart_advisor")

# ============================================================================
# WeatherClient
# ============================================================================

class WeatherClient:
    """Obtiene condiciones meteorológicas exteriores vía wttr.in."""

    BASE_URL = "https://wttr.in"
    LOCATION = "Córdoba,Spain"  # Barrio de Fátima
    CACHE_PATH = "/tmp/outdoor_weather.json"
    CACHE_MAX_AGE = 600  # 10 min

    @classmethod
    def get_current(cls, force: bool = False) -> Optional[dict]:
        if not force and os.path.exists(cls.CACHE_PATH):
            try:
                age = time.time() - os.path.getmtime(cls.CACHE_PATH)
                if age < cls.CACHE_MAX_AGE:
                    with open(cls.CACHE_PATH) as f:
                        return json.load(f)
            except Exception:
                pass
        try:
            from urllib.parse import quote
            url = f"{cls.BASE_URL}/{quote(cls.LOCATION)}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "LuxeCoreAI/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                cc = data["current_condition"][0]
                result = {
                    "temperature_c": float(cc["temp_C"]),
                    "humidity_pct": float(cc["humidity"]),
                    "feels_like_c": float(cc["FeelsLikeC"]),
                    "weather": cc["weatherDesc"][0]["value"],
                    "wind_kmh": float(cc["windspeedKmph"]),
                    "uv_index": float(cc.get("uvIndex", 0)),
                    "timestamp": time.time(),
                }
                with open(cls.CACHE_PATH, "w") as f:
                    json.dump(result, f)
                return result
        except Exception as e:
            logger.warning(f"Weather fetch failed: {e}")
            if os.path.exists(cls.CACHE_PATH):
                try:
                    with open(cls.CACHE_PATH) as f:
                        return json.load(f)
                except Exception:
                    pass
            return None

    @classmethod
    def get_history_entry(cls) -> dict | None:
        """Formatea los datos exteriores para el JSONL histórico."""
        w = cls.get_current()
        if not w:
            return None
        return {
            "outdoor_temp_c": w["temperature_c"],
            "outdoor_humidity_pct": w["humidity_pct"],
            "outdoor_feels_like_c": w["feels_like_c"],
            "outdoor_weather": w["weather"],
            "outdoor_wind_kmh": w["wind_kmh"],
            "outdoor_uv": w["uv_index"],
        }


# ============================================================================
# PresenceDetector — BLE + manual
# ============================================================================

PRESENCE_FILE = "/tmp/luxe_presence.json"


class PresenceDetector:
    """Detecta presencia en la habitación.

    Métodos (en orden de prioridad):
      1. Manual: flag home/away (vía "he llegado" / "me voy")
      2. BLE: escaneo del teléfono móvil (rápido, ~3-5s)
    """

    TIMEOUT_MIN = 30
    BLE_SCAN_TIMEOUT = 8  # segundos para escaneo BLE

    @classmethod
    def is_home(cls) -> bool:
        manual = cls._read_manual_flag()
        if manual is not None:
            return manual
        # BLE check
        ble = cls._check_ble()
        if ble is not None:
            return ble
        # Sin datos → asumir que sí
        return True

    @classmethod
    def set_home(cls, at_home: bool) -> None:
        data = {"home": at_home, "set_at": time.time(), "method": "manual"}
        with open(PRESENCE_FILE, "w") as f:
            json.dump(data, f)
        logger.info(f"🏠 Presencia → {'HOME' if at_home else 'AWAY'}")

    @classmethod
    def get_status(cls) -> dict:
        return {
            "home": cls.is_home(),
            "manual": cls._read_manual_flag(),
            "ble": cls._check_ble(),
            "phone_mac": os.environ.get("LUXE_PHONE_BLE_MAC", ""),
        }

    @classmethod
    def _read_manual_flag(cls) -> Optional[bool]:
        try:
            if not os.path.exists(PRESENCE_FILE):
                return None
            with open(PRESENCE_FILE) as f:
                data = json.load(f)
            age = time.time() - data.get("set_at", 0)
            if age > cls.TIMEOUT_MIN * 60:
                return None
            return data.get("home")
        except Exception:
            return None

    @classmethod
    def _check_ble(cls) -> Optional[bool]:
        """Escanea dispositivos BLE buscando el MAC del teléfono.

        Usa bluetoothctl (BlueZ) si está disponible. Rápido (~3-5s).
        """
        phone_mac = os.environ.get("LUXE_PHONE_BLE_MAC", "").strip().upper()
        if not phone_mac:
            return None

        # Método 1: bluetoothctl scan (más fiable)
        try:
            result = subprocess.run(
                ["timeout", str(cls.BLE_SCAN_TIMEOUT),
                 "bluetoothctl", "scan", "le"],
                capture_output=True, text=True, timeout=cls.BLE_SCAN_TIMEOUT + 2,
            )
            output = (result.stdout + result.stderr).upper()
            if phone_mac in output:
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Método 2: hcitool (fallback)
        try:
            result = subprocess.run(
                ["timeout", str(cls.BLE_SCAN_TIMEOUT),
                 "hcitool", "lescan"],
                capture_output=True, text=True, timeout=cls.BLE_SCAN_TIMEOUT + 2,
            )
            if phone_mac in (result.stdout + result.stderr).upper():
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None  # Sin herramientas BLE


# ============================================================================
# Window Advisor
# ============================================================================

class WindowAdvisor:
    OPEN_WINDOW_IF_OUTDOOR_COOLER_BY = 2.0
    CLOSE_WINDOW_IF_OUTDOOR_HOTTER_BY = 2.0
    BLINDS_DOWN_TEMP = 28.0
    BLINDS_DOWN_UV = 5
    MAX_OUTDOOR_FOR_WINDOW = 32.0

    @classmethod
    def assess(cls, indoor: dict, outdoor: dict) -> dict:
        result = {
            "open_window": False, "close_window": False,
            "blinds_down": False, "reason": "Sin datos suficientes",
        }
        if not indoor or not outdoor:
            return result

        in_temp = indoor.get("temperature_c", 0)
        out_temp = outdoor.get("temperature_c", 0)
        out_uv = outdoor.get("uv_index", 0)
        out_weather = outdoor.get("weather", "").lower()
        temp_diff = in_temp - out_temp

        if out_temp >= cls.MAX_OUTDOOR_FOR_WINDOW:
            result["close_window"] = True
            result["reason"] = f"Fuera hace {out_temp:.0f}°C — mejor cerrado"
        elif temp_diff >= cls.OPEN_WINDOW_IF_OUTDOOR_COOLER_BY:
            result["open_window"] = True
            result["reason"] = (
                f"Fuera está más fresco ({out_temp:.0f}°C vs {in_temp:.0f}°C) — abre"
            )
        elif -temp_diff >= cls.CLOSE_WINDOW_IF_OUTDOOR_HOTTER_BY:
            result["close_window"] = True
            result["reason"] = (
                f"Fuera hace más calor ({out_temp:.0f}°C vs {in_temp:.0f}°C) — cierra"
            )
        else:
            result["reason"] = "Temperaturas similares dentro y fuera"

        if in_temp >= cls.BLINDS_DOWN_TEMP:
            result["blinds_down"] = True
            if "persiana" not in result["reason"]:
                result["reason"] += " | Baja la persiana"

        if out_uv >= cls.BLINDS_DOWN_UV and "rain" not in out_weather:
            result["blinds_down"] = True

        if "rain" in out_weather or "drizzle" in out_weather:
            result["close_window"] = True
            result["open_window"] = False
            result["reason"] = "Está lloviendo — cierra la ventana"

        return result


# ============================================================================
# Trend Detector — ¿subiendo o bajando?
# ============================================================================

TREND_FILE = "/tmp/sensor_trend.json"


class TrendDetector:
    """Detecta la tendencia de temperatura comparando con lecturas anteriores."""

    WINDOW_MINUTES = 30  # Ventana de tiempo para detectar tendencia
    MIN_CHANGE = 0.3     # °C — cambio mínimo para considerar tendencia

    @classmethod
    def detect(cls, current_temp: float) -> dict:
        """Compara con el histórico y detecta tendencia."""
        history = cls._read_recent()
        history.append({"temp": current_temp, "ts": time.time()})
        cls._save(history)

        if len(history) < 2:
            return {"trend": "estable", "change_per_hour": 0.0, "samples": len(history)}

        # Calcular tasa de cambio (°C/hora)
        first = history[0]
        last = history[-1]
        hours = (last["ts"] - first["ts"]) / 3600
        if hours < 0.01:
            return {"trend": "estable", "change_per_hour": 0.0, "samples": len(history)}

        change = last["temp"] - first["temp"]
        rate = change / hours

        if rate > cls.MIN_CHANGE:
            trend = "subiendo"
        elif rate < -cls.MIN_CHANGE:
            trend = "bajando"
        else:
            trend = "estable"

        return {
            "trend": trend,
            "change_per_hour": round(rate, 2),
            "samples": len(history),
            "since_minutes": round(hours * 60, 1),
        }

    @classmethod
    def _read_recent(cls) -> list:
        try:
            if not os.path.exists(TREND_FILE):
                return []
            with open(TREND_FILE) as f:
                data = json.load(f)
            cutoff = time.time() - cls.WINDOW_MINUTES * 60
            return [p for p in data if p["ts"] >= cutoff]
        except Exception:
            return []

    @classmethod
    def _save(cls, history: list) -> None:
        cutoff = time.time() - cls.WINDOW_MINUTES * 60
        history = [p for p in history if p["ts"] >= cutoff]
        try:
            with open(TREND_FILE, "w") as f:
                json.dump(history, f)
        except Exception:
            pass


# ============================================================================
# SmartAdvisor — Orquestador con auto-acción (Opción C corregida)
# ============================================================================

HOME_SH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "server", "tools", "home.sh",
)

STATE_FILE = "/tmp/smart_advisor_state.json"


class SmartAdvisor:
    """Combina todos los advisors y ejecuta auto-acciones según Opción C.

    REGLAS (corregidas):
      +1 zona     → PREGUNTAR (cambio pequeño, confirma primero)
      +2+ zonas   → ACTUAR automático (cambio brusco, prioridad confort)
      Zona 🟣     → ACTUAR siempre (extremo)
      Misma zona  → Sin cambios (no molestar)
      Sin presencia → No actuar

    EXCEPCIÓN manual:
      Si el usuario puso manualmente el ventilador a velocidad X
      (en los últimos 30 min) y la zona empeora, auto-subir
      (respeta la intención de querer ventilación).
    """

    @classmethod
    def assess_full(cls) -> dict:
        indoor = cls._read_indoor()
        outdoor = WeatherClient.get_current()
        presence = PresenceDetector.is_home()

        result = {
            "timestamp": time.time(),
            "indoor": indoor,
            "outdoor": outdoor,
            "presence": presence,
            "comfort": None,
            "window": None,
            "trend": None,
            "actions": [],
            "notifications": [],
            "should_act": False,
            "should_ask": False,
        }

        if not indoor:
            result["notifications"].append("⚠️ Sin datos del sensor interior")
            return result

        # Confort
        temp = indoor["temperature_c"]
        hum = indoor["humidity_pct"]
        comfort = ComfortAdvisor.assess(temp, hum)
        result["comfort"] = {
            "zone": comfort["zone"], "label": comfort["label"],
            "emoji": comfort["emoji"], "fan_speed": comfort["fan_speed"],
            "ac_recommended": comfort["ac_recommended"],
            "humidifier_recommended": comfort["humidifier_recommended"],
            "heat_index": comfort["heat_index"],
        }

        # Tendencia
        trend = TrendDetector.detect(temp)
        result["trend"] = trend

        # Ventana
        if outdoor:
            result["window"] = WindowAdvisor.assess(indoor, outdoor)

        # ---- DECISIÓN DE ACTUACIÓN ----
        if not presence:
            result["notifications"].append("🏠 No hay nadie — no se actúa")
            cls._add_recommendations(result, comfort, result.get("window"))
            return result

        prev_zone = cls._get_previous_zone()
        current_zone = comfort["zone"]
        zone_jump = current_zone - prev_zone if prev_zone is not None else 0

        # Check excepción: velocidad manual previa
        prev_speed, prev_speed_ts = ComfortAdvisor.get_previous_manual_speed()

        if prev_zone is None:
            result["should_act"] = False  # Primera lectura
        elif current_zone >= 4:
            # 🟣 Extremo → actuar directo
            result["notifications"].append(f"🔴 Condiciones extremas — actuando...")
            result["should_act"] = True
        elif zone_jump >= 2:
            # +2 zonas → actuar automático
            result["notifications"].append(
                f"⚠️ Cambio brusco ({prev_zone}→{current_zone}) — ajustando..."
            )
            result["should_act"] = True
        elif zone_jump == 1:
            if prev_speed is not None and prev_speed > 0 and comfort["fan_speed"] > prev_speed:
                # El usuario ya quería ventilación → auto-subir
                result["notifications"].append(
                    f"ℹ️ Subo el ventilador de {prev_speed}→{comfort['fan_speed']} "
                    f"(ya lo tenías puesto y ha empeorado)"
                )
                result["should_act"] = True
            else:
                # +1 zona sin contexto → preguntar
                result["notifications"].append(
                    f"ℹ️ El ambiente pasó a {comfort['label']}. "
                    f"¿Pongo el ventilador al {comfort['fan_speed']}?"
                )
                result["should_ask"] = True
                result["should_act"] = False
        elif zone_jump == 0 and current_zone >= 3:
            if prev_speed is not None and prev_speed > 0 and comfort["fan_speed"] > prev_speed:
                result["notifications"].append(
                    f"ℹ️ Subiendo ventilador {prev_speed}→{comfort['fan_speed']} "
                    f"(sigue haciendo calor)"
                )
                result["should_act"] = True
            else:
                result["should_act"] = False
        else:
            result["should_act"] = False

        cls._save_zone(current_zone)
        cls._add_recommendations(result, comfort, result.get("window"))

        return result

    @classmethod
    def execute_auto_actions(cls, result: dict) -> list[str]:
        """Ejecuta las acciones automáticas. Devuelve lista de resultados."""
        if not result.get("should_act"):
            return []

        executed = []
        for action in result.get("actions", []):
            act_type = action.get("action", "")
            if act_type == "fan_speed":
                speed = action.get("speed", 1)
                if 1 <= speed <= 5:
                    cmd = f"bash {HOME_SH} fan_speed {speed}"
                    try:
                        subprocess.run(cmd.split(), capture_output=True,
                                       timeout=30)
                        executed.append(f"🌀 Ventilador → {speed}")
                    except Exception as e:
                        executed.append(f"❌ Ventilador: {e}")
            elif act_type == "fan_off":
                try:
                    subprocess.run(f"bash {HOME_SH} fan_off".split(),
                                   capture_output=True, timeout=30)
                    executed.append("🌀 Ventilador → apagado")
                except Exception as e:
                    executed.append(f"❌ Ventilador off: {e}")

        return executed

    @classmethod
    def _add_recommendations(cls, result: dict, comfort: dict,
                             window: Optional[dict]) -> None:
        actions = result["actions"]
        notifs = result["notifications"]

        if window:
            if window["open_window"]:
                notifs.append(f"🪟 {window['reason']}")
            elif window["close_window"]:
                notifs.append(f"🪟 {window['reason']}")
            if window["blinds_down"]:
                notifs.append("🎭 Baja la persiana")

        if comfort["fan_speed"] > 0:
            actions.append({
                "action": "fan_speed",
                "speed": comfort["fan_speed"],
                "reason": f"Confort {comfort['label']}",
            })
        elif comfort["zone"] <= 1 and result.get("presence"):
            actions.append({"action": "fan_off", "reason": "Temperatura fresca"})

        if comfort["humidifier_recommended"]:
            actions.append({"action": "humidifier", "reason": "Ambiente seco"})
            notifs.append("💦 El ambiente está seco — humidificador")

        if comfort["ac_recommended"]:
            notifs.append(
                f"❄️ Sensación térmica {comfort['heat_index']}°C. "
                f"Enciende el aire acondicionado."
            )

        # Tendencia
        trend = result.get("trend", {})
        if trend.get("trend") == "subiendo":
            rate = trend.get("change_per_hour", 0)
            notifs.append(f"📈 Temperatura subiendo +{rate}°C/h")
        elif trend.get("trend") == "bajando":
            rate = trend.get("change_per_hour", 0)
            notifs.append(f"📉 Temperatura bajando {rate}°C/h")

    # ------------------------------------------------------------------
    # Formato
    # ------------------------------------------------------------------

    @classmethod
    def format_response(cls) -> str:
        result = cls.assess_full()
        indoor = result["indoor"]
        outdoor = result["outdoor"]
        comfort = result["comfort"]

        if not indoor or not comfort:
            return "⚠️ No hay datos del sensor interior."

        lines = ["🏠 **Interior**"]
        lines.append(f"  {ComfortAdvisor.format_simple(indoor['temperature_c'], indoor['humidity_pct'])}")

        if outdoor:
            lines.append("")
            lines.append("🌍 **Exterior** (Córdoba, Fátima)")
            lines.append(f"  🌡️ {outdoor['temperature_c']:.0f}°C | 💧 {outdoor['humidity_pct']:.0f}%")
            lines.append(f"  {outdoor['weather']} | 🌬️ {outdoor['wind_kmh']:.0f} km/h | UV {outdoor['uv_index']:.0f}")

        lines.append("")
        if result["presence"]:
            lines.append("📍 En casa")
        else:
            lines.append("📍 Fuera de casa — no se actúa")

        if result.get("trend"):
            t = result["trend"]
            emoji = {"subiendo": "📈", "bajando": "📉", "estable": "➡️"}.get(t["trend"], "➡️")
            lines.append(f"{emoji} Tendencia: {t['trend']} ({t['change_per_hour']:+.1f}°C/h)")

        if result.get("window"):
            lines.append("")
            lines.append("🪟 **Ventana / Persiana**")
            lines.append(f"  {result['window']['reason']}")

        if result["notifications"]:
            lines.append("")
            lines.append("📋 **Recomendaciones**")
            for n in result["notifications"]:
                lines.append(f"  • {n}")

        if result["should_act"] and result["actions"]:
            lines.append("")
            lines.append("⚡ **Acciones automáticas**")
            for a in result["actions"]:
                if a["action"] == "fan_speed":
                    lines.append(f"  🌀 Ventilador → velocidad {a['speed']}")
                elif a["action"] == "fan_off":
                    lines.append(f"  🌀 Ventilador → apagado")
        elif result["should_ask"]:
            lines.append("")
            lines.append("❓ **¿Aplico estas acciones?** (responde 'sí' para ejecutar)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Estado interno
    # ------------------------------------------------------------------

    @staticmethod
    def _read_indoor() -> Optional[dict]:
        try:
            with open("/tmp/latest_sensor.json") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def _get_previous_zone(cls) -> Optional[int]:
        try:
            with open(cls.STATE_FILE) as f:
                return json.load(f).get("zone")
        except Exception:
            return None

    @classmethod
    def _save_zone(cls, zone: int) -> None:
        try:
            with open(cls.STATE_FILE, "w") as f:
                json.dump({"zone": zone, "timestamp": time.time()}, f)
        except Exception:
            pass
