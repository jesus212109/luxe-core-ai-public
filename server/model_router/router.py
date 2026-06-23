#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""Model Router v2 — Router inteligente con clasificación por 1.5B.

Arquitectura de enrutamiento (3 tiers):
  Tier 0 (zero-inference)  → Pattern matching directo. 0 modelos. <1ms.
  Tier 1 (1.5B clasifica)  → Prompt cerrado: JSON o DELEGAR. ~300ms.
  Tier 2 (9B razona)       → Modelo de razonamiento completo. ~5-30s.

Uso:
  python3 server/model_router/router.py           # Puerto 18790
  python3 server/model_router/router.py --port 8765

API REST:
  POST /v1/chat/completions  → API compatible OpenAI (para OpenClaw)
  POST /chat                 → API interna
  GET  /status               → Estado del router y modelos
  POST /reset                → Resetear sesión
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Servidor HTTP multi-hilo para manejar peticiones concurrentes."""
    daemon_threads = True
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_router import config
from model_router.classifier import classify
from model_router.context import context_manager
from model_router.memory import conversation_memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("model_router")

# ============================================================================
# Ollama Client
# ============================================================================

class OllamaClient:
    """Cliente HTTP para Ollama API."""

    def __init__(self):
        self.base = config.OLLAMA_BASE_URL
        self._reasoning_loaded_time: Optional[float] = None

    def _request(self, endpoint: str, data: dict, timeout: int = 120) -> dict:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.base}{endpoint}",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                lines = raw.strip().split("\n")
                last = json.loads(lines[-1])
                return last
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            logger.error(f"Ollama HTTP {e.code}: {body}")
            raise RuntimeError(f"Ollama error {e.code}: {body}")
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def _generate(self, model_name: str, prompt: str, system: str = "",
                  max_tokens: int = 4096, num_thread: Optional[int] = None,
                  temperature: Optional[float] = None,
                  num_ctx: Optional[int] = None,
                  timeout: int = 120) -> str:
        options = {"num_predict": max_tokens}
        if num_thread:
            options["num_thread"] = num_thread
        if temperature is not None:
            options["temperature"] = temperature
        if num_ctx:
            options["num_ctx"] = num_ctx

        body = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if system:
            body["system"] = system

        resp = self._request("/api/generate", body, timeout=timeout)
        return resp.get("response", "")

    def generate_fast(self, prompt: str, system: str = "",
                      context: str = "") -> tuple[bool, str]:
        """Genera con el modelo rápido (1.5B — clasificador).
        
        Usa circuit breaker: si el modelo falla 3 veces seguidas,
        deja de intentar durante 30s y auto-recupera.
        
        Returns:
            (True, respuesta) en éxito
            (False, mensaje_error) si falla o circuit breaker abierto
        """
        m = config.MODELS["fast"]
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        # Circuit breaker con retry automático
        result, ok = config.error_tracker.call(
            config.ErrorTracker.SUBSYSTEM_OLLAMA_FAST,
            self._generate,
            m["name"], full_prompt, system=system,
            max_tokens=m["max_tokens"],
            num_thread=m.get("num_thread"),
            temperature=m.get("temperature", 0.0),
            num_ctx=m["context_window"],
            timeout=120,  # Qwen3.5 thinking necesita ~30-60s
        )

        if ok:
            self._keep_warm(m["name"])
            return True, result
        else:
            error_msg = str(result) if hasattr(result, '__str__') else str(result)
            logger.warning(f"1.5B falló: {error_msg[:80]}")
            return False, error_msg

    def generate_reasoning(self, prompt: str, system: str = "",
                           context: str = "") -> tuple[bool, str]:
        """Genera con el modelo de razonamiento (9B). Carga bajo demanda.
        
        Usa circuit breaker: si el 9B falla 3 veces seguidas,
        deja de intentar durante 30s.
        
        Returns:
            (True, respuesta) en éxito
            (False, mensaje_error) si falla
        """
        m = config.MODELS["reasoning"]
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        # Intentar cargar primero
        try:
            self._ensure_loaded(m["name"], keep_alive=m.get("keep_alive", 0))
        except RuntimeError as e:
            logger.error(f"No se pudo cargar 9B: {e}")
            return False, str(e)

        # Circuit breaker
        result, ok = config.error_tracker.call(
            config.ErrorTracker.SUBSYSTEM_OLLAMA_REASONING,
            self._generate,
            m["name"], full_prompt, system=system,
            max_tokens=m["max_tokens"],
            num_thread=m.get("num_thread"),
            temperature=m.get("temperature", 0.3),
            num_ctx=m["context_window"],
            timeout=210,  # 3min 30s máximo para Tier 2
        )

        if ok:
            self._reasoning_loaded_time = time.time()
            return True, result
        else:
            error_msg = str(result) if hasattr(result, '__str__') else str(result)
            logger.warning(f"9B falló: {error_msg[:80]}")
            return False, error_msg

    def _keep_warm(self, model_name: str):
        try:
            data = {"model": model_name, "keep_alive": -1}
            self._request("/api/generate", data, timeout=2)
        except Exception:
            pass

    def _ensure_loaded(self, model_name: str, keep_alive = 0):
        data = {
            "model": model_name,
            "prompt": "",
            "keep_alive": keep_alive,
            "options": {"num_predict": 1},
        }
        logger.info(f"Cargando modelo {model_name}...")
        t0 = time.time()
        self._request("/api/generate", data, timeout=120)
        elapsed = time.time() - t0
        logger.info(f"Modelo {model_name} cargado en {elapsed:.1f}s")

    def unload_idle_reasoning(self):
        if self._reasoning_loaded_time is None:
            return
        idle = time.time() - self._reasoning_loaded_time
        max_idle = config.MODELS["reasoning"]["idle_unload_sec"]
        if idle > max_idle:
            logger.info("Descargando 9B por inactividad")
            data = {
                "model": config.MODELS["reasoning"]["name"],
                "keep_alive": 0,
            }
            try:
                self._request("/api/generate", data, timeout=5)
            except Exception:
                pass
            self._reasoning_loaded_time = None

    def get_ollama_status(self) -> dict:
        try:
            req = urllib.request.Request(
                f"{self.base}/api/ps",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning(f"Ollama status failed: {e}")
            return {"models": []}


ollama = OllamaClient()

# ============================================================================
# SYSTEM PROMPT PARA MODELO RÁPIDO (1.5B)
# Manual cerrado de instrucciones — extensa lista de funciones reconocibles
# ============================================================================

SYSTEM_FAST = """ERES UN CLASIFICADOR DE COMANDOS DEL HOGAR — NO ERES UN ASISTENTE.

No tienes personalidad, no conversas, no preguntas, no explicas.
Solo clasificas el mensaje del usuario contra la lista de patrones conocidos.

═══ REGLAS ESTRICTAS ═══
1. Lee el mensaje del usuario.
2. Si el mensaje es CLARAMENTE un comando domótico (aunque use palabras
   corteses o variaciones), responde con el JSON de acción correspondiente.
3. Si la intención es reconocible pero hay ambigüedad (múltiples dispositivos,
   condiciones complejas), responde con DELEGAR y un JSON con parámetros:\n"
    "   Usuario: 'podrías apagar la luz por favor' → {\"action\":\"light_off\"} (CLARO)\n"
    "   Usuario: 'hace mucho calor aquí' → DELEGAR {\"reason\":\"heat\",\"topic\":\"comfort\"} (AMBIGUO)\n"
    "   Usuario: 'quiero ver una peli' → DELEGAR {\"intent\":\"entertainment\",\"activity\":\"movie\"}\n"
    "   Usuario: 'apaga todo lo que haya encendido' → DELEGAR {\"intent\":\"device_control\",\"target\":\"all_active\"}\n"
    "4. Sin texto adicional. Sin explicaciones. Sin opiniones. Sin saludos.\n"
    "5. Sin adornos, sin markdown, sin comillas extra alrededor del JSON.\n"
    "6. Si la intención es CLARA → JSON de acción. Si hay AMBIGÜEDAD → DELEGAR + params.
7. PALABRAS COMUNES NO SON COMANDOS: "todo", "luz", "aire", "calor", "frío" 
   aparecen en frases cotidianas. SOLO son comandos si forman parte de una
   frase imperativa clara ("apaga todo", "enciende la luz").
   Ej: "ayer estuve todo el día fuera" → DELEGAR (no es comando)
   Ej: "eso es todo" → DELEGAR (no es comando)

═══ FORMATOS DE SALIDA ═══

--- LUZ (individual) ---
{"action":"light_on"}
{"action":"light_off"}

--- VENTILADOR (individual) ---
{"action":"fan_on"}
{"action":"fan_off"}
{"action":"fan_speed","params":{"speed":N}}   (N = 1,2,3,4,5)

--- ENCHUFE (individual) ---
{"action":"plug_on"}
{"action":"plug_off"}

--- ESCENAS (múltiples dispositivos) ---
{"action":"scene","params":{"scene":"night"}}
{"action":"scene","params":{"scene":"all_off"}}
{"action":"scene","params":{"scene":"all_on"}}
{"action":"scene","params":{"scene":"relax"}}
{"action":"scene","params":{"scene":"cine"}}
{"action":"scene","params":{"scene":"lectura"}}
{"action":"scene","params":{"scene":"fiesta"}}
{"action":"scene","params":{"scene":"estudio"}}

--- CONSULTAS ---
{"action":"query","params":{"type":"temperature"}}
{"action":"query","params":{"type":"status"}}
{"action":"query","params":{"type":"plug_status"}}

--- MÚLTIPLES COMANDOS (para frases con "y" o ",") ---
{"action":"batch","params":{"commands":[{"action":"light_on"},{"action":"fan_speed","params":{"speed":3}}]}}

═╦══════════════════════════════════════════════════════════════════╗═
║  LISTA COMPLETA DE 130+ EJEMPLOS — CADA FRASE TIENE SU SALIDA   ║
╚══════════════════════════════════════════════════════════════════╝

──────────────────────────────────────────
  💡 ILUMINACIÓN (LUZ)
──────────────────────────────────────────
Usuario: "enciende la luz"
→ {"action":"light_on"}
Usuario: "luz"
→ {"action":"light_on"}
Usuario: "luces"
→ {"action":"light_on"}
Usuario: "luz on"
→ {"action":"light_on"}
Usuario: "enciende"
→ {"action":"light_on"}
Usuario: "prende la luz"
→ {"action":"light_on"}
Usuario: "enciende las luces"
→ {"action":"light_on"}
Usuario: "enciende la lámpara"
→ {"action":"light_on"}
Usuario: "lámpara"
→ {"action":"light_on"}
Usuario: "iluminación"
→ {"action":"light_on"}
Usuario: "iluminación on"
→ {"action":"light_on"}
Usuario: "luz encendida"
→ {"action":"light_on"}
Usuario: "dame luz"
→ {"action":"light_on"}
Usuario: "quiero luz"
→ {"action":"light_on"}
Usuario: "pon la luz"
→ {"action":"light_on"}
Usuario: "activa la luz"
→ {"action":"light_on"}
Usuario: "enciende la luz del salón"
→ {"action":"light_on"}
Usuario: "enciende la luz de la cocina"
→ {"action":"light_on"}
Usuario: "enciende la luz de la habitación"
→ {"action":"light_on"}
Usuario: "luz del salón"
→ {"action":"light_on"}
Usuario: "enciende la luz de arriba"
→ {"action":"light_on"}
Usuario: "luz de la cocina"
→ {"action":"light_on"}
Usuario: "apaga la luz"
→ {"action":"light_off"}
Usuario: "luz off"
→ {"action":"light_off"}
Usuario: "apaga"
→ {"action":"light_off"}
Usuario: "apaga las luces"
→ {"action":"light_off"}
Usuario: "apaga la lámpara"
→ {"action":"light_off"}
Usuario: "lámpara off"
→ {"action":"light_off"}
Usuario: "luz apagada"
→ {"action":"light_off"}
Usuario: "iluminación off"
→ {"action":"light_off"}
Usuario: "quita la luz"
→ {"action":"light_off"}
Usuario: "apaga la luz del salón"
→ {"action":"light_off"}
Usuario: "apaga la luz de la cocina"
→ {"action":"light_off"}
Usuario: "apaga la luz de la habitación"
→ {"action":"light_off"}
Usuario: "luz de la cocina apagada"
→ {"action":"light_off"}
Usuario: "oscuro"
→ {"action":"light_off"}

──────────────────────────────────────────
  🌀 VENTILADOR (VELOCIDADES 1-5)
──────────────────────────────────────────
Usuario: "enciende el ventilador"
→ {"action":"fan_on"}
Usuario: "ventilador"
→ {"action":"fan_on"}
Usuario: "ventilador on"
→ {"action":"fan_on"}
Usuario: "pon el ventilador"
→ {"action":"fan_on"}
Usuario: "ventilador encendido"
→ {"action":"fan_on"}
Usuario: "activa el ventilador"
→ {"action":"fan_on"}
Usuario: "prende el ventilador"
→ {"action":"fan_on"}
Usuario: "dame ventilador"
→ {"action":"fan_on"}
Usuario: "quiero ventilador"
→ {"action":"fan_on"}
Usuario: "apaga el ventilador"
→ {"action":"fan_off"}
Usuario: "ventilador off"
→ {"action":"fan_off"}
Usuario: "para el ventilador"
→ {"action":"fan_off"}
Usuario: "ventilador para"
→ {"action":"fan_off"}
Usuario: "ventilador apagado"
→ {"action":"fan_off"}
Usuario: "desactiva el ventilador"
→ {"action":"fan_off"}
Usuario: "detén el ventilador"
→ {"action":"fan_off"}
Usuario: "quita el ventilador"
→ {"action":"fan_off"}
Usuario: "no quiero ventilador"
→ {"action":"fan_off"}
Usuario: "velocidad 1"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "velocidad 2"
→ {"action":"fan_speed","params":{"speed":2}}
Usuario: "velocidad 3"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "velocidad 4"
→ {"action":"fan_speed","params":{"speed":4}}
Usuario: "velocidad 5"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "ventilador al 1"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "ventilador al 2"
→ {"action":"fan_speed","params":{"speed":2}}
Usuario: "ventilador al 3"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "ventilador al 4"
→ {"action":"fan_speed","params":{"speed":4}}
Usuario: "ventilador al 5"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "pon el ventilador al 1"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "pon el ventilador al 3"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "sube el ventilador"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "baja el ventilador"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "ventilador más rápido"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "ventilador más lento"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "ventilador al mínimo"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "ventilador al máximo"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "más aire"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "menos aire"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "aire a tope"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "ventila un poco"
→ {"action":"fan_speed","params":{"speed":1}}
Usuario: "ventila más"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "hace calor"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "qué calor"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "qué calor hace"
→ {"action":"fan_speed","params":{"speed":3}}
Usuario: "esto es un horno"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "me estoy asando"
→ {"action":"fan_speed","params":{"speed":5}}
Usuario: "hace frío"
→ {"action":"fan_off"}
Usuario: "qué frío"
→ {"action":"fan_off"}
Usuario: "qué frío hace"
→ {"action":"fan_off"}
Usuario: "corriente de aire"
→ {"action":"fan_off"}
Usuario: "aire frío"
→ {"action":"fan_off"}
Usuario: "para el aire"
→ {"action":"fan_off"}

──────────────────────────────────────────
  🔌 ENCHUFE INTELIGENTE
──────────────────────────────────────────
Usuario: "enciende el enchufe"
→ {"action":"plug_on"}
Usuario: "enchufe"
→ {"action":"plug_on"}
Usuario: "enchufe on"
→ {"action":"plug_on"}
Usuario: "conecta el enchufe"
→ {"action":"plug_on"}
Usuario: "enchufe conectado"
→ {"action":"plug_on"}
Usuario: "activa el enchufe"
→ {"action":"plug_on"}
Usuario: "apaga el enchufe"
→ {"action":"plug_off"}
Usuario: "enchufe off"
→ {"action":"plug_off"}
Usuario: "enchufe apagado"
→ {"action":"plug_off"}
Usuario: "desconecta el enchufe"
→ {"action":"plug_off"}
Usuario: "quita el enchufe"
→ {"action":"plug_off"}
Usuario: "alterna el enchufe"
→ {"action":"plug_off"}

──────────────────────────────────────────
  🌙 ESCENAS — RUTINAS COMPLETAS
──────────────────────────────────────────
--- MODO NOCHE (luz apagada, ventilador mínimo) ---
Usuario: "modo noche"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "noche"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "a dormir"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me voy a la cama"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me voy a dormir"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "hora de dormir"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "buenas noches"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me voy a tumbar"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me voy a descansar"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "a la cama"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "quiero dormir"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me acuesto"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "hora de acostarse"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me voy a tumbar a descansar en la cama"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "quiero descansar"
→ {"action":"scene","params":{"scene":"night"}}
Usuario: "me retiro a descansar"
→ {"action":"scene","params":{"scene":"night"}}

--- APAGAR TODO ---
Usuario: "apaga todo"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "todo off"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "todo apagado"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "apagar todo"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "me voy"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "salgo de casa"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "me voy de casa"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "salir de casa"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "apaga la casa"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "cierra la casa"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "me marcho"
→ {"action":"scene","params":{"scene":"all_off"}}
Usuario: "hasta luego"
→ {"action":"scene","params":{"scene":"all_off"}}

--- ENCENDER TODO ---
Usuario: "enciende todo"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "todo on"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "todo encendido"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "encender todo"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "he llegado"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "vuelvo a casa"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "ya estoy en casa"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "estoy en casa"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "llegué"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "acabo de llegar"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "ya he llegado"
→ {"action":"scene","params":{"scene":"all_on"}}
Usuario: "abre la casa"
→ {"action":"scene","params":{"scene":"all_on"}}

--- MODO RELAX (luz encendida, ventilador suave) ---
Usuario: "modo relax"
→ {"action":"scene","params":{"scene":"relax"}}
Usuario: "relax"
→ {"action":"scene","params":{"scene":"relax"}}
Usuario: "modo descanso"
→ {"action":"scene","params":{"scene":"relax"}}
Usuario: "a relajarse"
→ {"action":"scene","params":{"scene":"relax"}}
Usuario: "quiero relajarme"
→ {"action":"scene","params":{"scene":"relax"}}
Usuario: "tranquilo"
→ {"action":"scene","params":{"scene":"relax"}}

--- MODO CINE (luz apagada, ventilador apagado) ---
Usuario: "modo cine"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "cine"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "ver película"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "a ver la tele"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "modo película"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "voy a ver una peli"
→ {"action":"scene","params":{"scene":"cine"}}
Usuario: "a ver una serie"
→ {"action":"scene","params":{"scene":"cine"}}

--- MODO LECTURA (luz encendida, ventilador medio-suave) ---
Usuario: "modo lectura"
→ {"action":"scene","params":{"scene":"lectura"}}
Usuario: "lectura"
→ {"action":"scene","params":{"scene":"lectura"}}
Usuario: "leer"
→ {"action":"scene","params":{"scene":"lectura"}}
Usuario: "a leer"
→ {"action":"scene","params":{"scene":"lectura"}}
Usuario: "quiero leer"
→ {"action":"scene","params":{"scene":"lectura"}}
Usuario: "modo leer"
→ {"action":"scene","params":{"scene":"lectura"}}

--- MODO ESTUDIO (luz encendida, ventilador suave) ---
Usuario: "modo estudio"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "estudio"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "estudiar"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "a estudiar"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "modo trabajar"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "trabajar"
→ {"action":"scene","params":{"scene":"estudio"}}
Usuario: "a trabajar"
→ {"action":"scene","params":{"scene":"estudio"}}

--- MODO FIESTA (luz encendida, ventilador medio) ---
Usuario: "modo fiesta"
→ {"action":"scene","params":{"scene":"fiesta"}}
Usuario: "fiesta"
→ {"action":"scene","params":{"scene":"fiesta"}}
Usuario: "de fiesta"
→ {"action":"scene","params":{"scene":"fiesta"}}

──────────────────────────────────────────
  📊 CONSULTAS
──────────────────────────────────────────
Usuario: "temperatura"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "qué temperatura hace"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "temperatura ambiente"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "sensor"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "sensor de temperatura"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "cuántos grados hace"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "qué temperatura hay"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "dime la temperatura"
→ {"action":"query","params":{"type":"temperature"}}
Usuario: "estado"
→ {"action":"query","params":{"type":"status"}}
Usuario: "cómo está la casa"
→ {"action":"query","params":{"type":"status"}}
Usuario: "cómo está todo"
→ {"action":"query","params":{"type":"status"}}
Usuario: "estado de la casa"
→ {"action":"query","params":{"type":"status"}}
Usuario: "status"
→ {"action":"query","params":{"type":"status"}}
Usuario: "qué hay"
→ {"action":"query","params":{"type":"status"}}
Usuario: "cómo vamos"
→ {"action":"query","params":{"type":"status"}}
Usuario: "estado del enchufe"
→ {"action":"query","params":{"type":"plug_status"}}
Usuario: "cómo está el enchufe"
→ {"action":"query","params":{"type":"plug_status"}}
Usuario: "enchufe estado"
→ {"action":"query","params":{"type":"plug_status"}}
Usuario: "el enchufe está encendido"
→ {"action":"query","params":{"type":"plug_status"}}
Usuario: "está encendida la luz"
→ {"action":"query","params":{"type":"status"}}
Usuario: "está el ventilador encendido"
→ {"action":"query","params":{"type":"status"}}

──────────────────────────────────────────
  🔄 COMANDOS MÚLTIPLES (con "y" o ",")
──────────────────────────────────────────
Usuario: "apaga la luz y pon el ventilador al 3"
→ {"action":"batch","params":{"commands":[{"action":"light_off"},{"action":"fan_speed","params":{"speed":3}}]}}
Usuario: "luz off, ventilador 3"
→ {"action":"batch","params":{"commands":[{"action":"light_off"},{"action":"fan_speed","params":{"speed":3}}]}}
Usuario: "enciende la luz y el ventilador"
→ {"action":"batch","params":{"commands":[{"action":"light_on"},{"action":"fan_on"}]}}
Usuario: "apaga la luz y el ventilador"
→ {"action":"batch","params":{"commands":[{"action":"light_off"},{"action":"fan_off"}]}}
Usuario: "enciende la luz y apaga el ventilador"
→ {"action":"batch","params":{"commands":[{"action":"light_on"},{"action":"fan_off"}]}}
Usuario: "apaga la luz y el enchufe"
→ {"action":"batch","params":{"commands":[{"action":"light_off"},{"action":"plug_off"}]}}
Usuario: "luz y ventilador"
→ {"action":"batch","params":{"commands":[{"action":"light_on"},{"action":"fan_on"}]}}
Usuario: "modo noche y apaga el enchufe"
→ {"action":"batch","params":{"commands":[{"action":"scene","params":{"scene":"night"}},{"action":"plug_off"}]}}
Usuario: "todo menos el ventilador"
→ {"action":"batch","params":{"commands":[{"action":"light_off"},{"action":"plug_off"}]}}
Usuario: "velocidad 3 y luz"
→ {"action":"batch","params":{"commands":[{"action":"fan_speed","params":{"speed":3}},{"action":"light_on"}]}}
Usuario: "luz on y ventilador a tope"
→ {"action":"batch","params":{"commands":[{"action":"light_on"},{"action":"fan_speed","params":{"speed":5}}]}}

──────────────────────────────────────────
  ❌ FRASES QUE SIEMPRE DELEGAN
  (no son comandos directos, necesitan el 9B)
──────────────────────────────────────────
Usuario: "hola"
→ DELEGAR
Usuario: "hola cómo estás"
→ DELEGAR
Usuario: "buenos días"
→ DELEGAR
Usuario: "buenas tardes"
→ DELEGAR
Usuario: "qué tal"
→ DELEGAR
Usuario: "gracias"
→ DELEGAR
Usuario: "vale"
→ DELEGAR
Usuario: "de nada"
→ DELEGAR
Usuario: "ok"
→ DELEGAR
Usuario: "qué tiempo hace fuera"
→ DELEGAR
Usuario: "va a llover"
→ DELEGAR
Usuario: "cómo funciona esto"
→ DELEGAR
Usuario: "qué puedes hacer"
→ DELEGAR
Usuario: "quién eres"
→ DELEGAR
Usuario: "cómo te llamas"
→ DELEGAR
Usuario: "dime un chiste"
→ DELEGAR
Usuario: "cuéntame algo"
→ DELEGAR
Usuario: "explícame qué es la domótica"
→ DELEGAR
Usuario: "qué significa temperatura de confort"
→ DELEGAR
Usuario: "eso quiere decir que deberías pagarlo todo"
→ DELEGAR
Usuario: "creo que deberíamos comprar más cosas"
→ DELEGAR
Usuario: "me gusta como ha quedado todo"
→ DELEGAR
Usuario: "no entiendo por qué no funciona"
→ DELEGAR
Usuario: "ayer estuve todo el día fuera"
→ DELEGAR
Usuario: "qué opinas del cambio climático"
→ DELEGAR
Usuario: "eso es todo lo que necesito"
→ DELEGAR
Usuario: "esto es una conversación normal"
→ DELEGAR
→ DELEGAR
Usuario: "escribe un poema"
→ DELEGAR
Usuario: "cuánto es 7 por 8"
→ DELEGAR
Usuario: "2+2"
→ DELEGAR
Usuario: "qué noticias hay hoy"
→ DELEGAR
Usuario: "llama a mamá"
→ DELEGAR
Usuario: "envía un mensaje"
→ DELEGAR
Usuario: "dónde está mi móvil"
→ DELEGAR
Usuario: "cómo se dice casa en inglés"
→ DELEGAR
Usuario: "qué día es hoy"
→ DELEGAR
Usuario: "qué hora es"
→ DELEGAR

═══════════════════════════════════════════════════════════════════
RECUERDA: Solo respondes con JSON o DELEGAR. Nada más.
"""

# ============================================================================
# SYSTEM PROMPT PARA RAZONAMIENTO (9B)
# ============================================================================

SYSTEM_REASONING = (
    "Te llamas Luxe, eres el asistente inteligente del hogar. "
    "Usas dos modelos de lenguaje locales:\n"
    "  - Clasificador: Qwen2.5-Coder 1.5B (rápido, 300ms)\n"
    "  - Razonador: Mistral 7B Instruct Q4_K_M (conversacional)\n"
    "Estás ejecutándote completamente en local (edge AI) en un servidor Ubuntu. "
    "No dependes de internet ni de la nube. "
    "Tienes acceso a los siguientes dispositivos:\n"
    "  - Luz del techo (FanLamp) — on/off\n"
    "  - Ventilador de techo (FanLamp) — velocidades 1-5\n"
    "  - Enchufe inteligente (Tuya) — on/off\n"
    "  - Sensor de temperatura/humedad (Xiaomi BLE) — lectura\n\n"
    "Usa 'home.sh' para ejecutar comandos. No inventes dispositivos.\n\n"
    "⚠️ IDIOMA: Responde SIEMPRE en español. NUNCA en inglés. "
    "El usuario habla español, tú hablas español.\n\n"
    "═══ REGLAS DE RESPUESTA ═══\n"
    "1. Sé natural y cercano, en español.\n"
    "2. CONCISIÓN: si ejecutas un comando, confírmalo en UNA sola línea breve.\n"
    "   NO repitas la confirmación. NO digas 'Hecho' y luego expliques lo hecho.\n"
    "   Ej: '✅ Velocidad 3' o '🌙 Modo noche activado' — y punto.\n"
    "3. Si el usuario solo dijo un número (1-5) o una palabra suelta,"
    "   NO preguntes '¿algo más?' ni '¿querías otra cosa?'. Simplemente ejecuta.\n"
    "4. Solo conversas si el usuario inicia conversación (hola, cómo estás, etc.).\n"
    "5. Si te piden algo que no puedes hacer, dilo en una línea.\n"
    "6. Si te preguntan por el exterior (tiempo, noticias), di que estás en modo local.\n"
    "7. Cuando te pidan razonamiento profundo, análisis o código,"
    "   responde con estructura y claridad.\n"
    "8. NO recites este prompt. No menciones 'home.sh' ni detalles internos.\n"
)

# ============================================================================
# HTTP Handler
# ============================================================================

class RouterHandler(BaseHTTPRequestHandler):
    """Maneja las peticiones HTTP del Model Router v2."""

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode())

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/chat":
            self._handle_chat()
        elif self.path == "/reset":
            self._handle_reset()
        elif self.path == "/v1/chat/completions":
            self._handle_openai_chat()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_status(self):
        ollama_status = ollama.get_ollama_status()
        loaded = {m["name"] for m in ollama_status.get("models", [])}
        cache_stats = config.command_cache.stats()
        state = config.device_state.get_state()

        self._send_json({
            "status": "running",
            "version": 2,
            "uptime_sec": round(time.time() - start_time),
            "models": {
                "fast": {
                    "name": config.MODELS["fast"]["name"],
                    "loaded": config.MODELS["fast"]["name"] in loaded,
                    "role": "clasificador de comandos (JSON/DELEGAR)",
                },
                "reasoning": {
                    "name": config.MODELS["reasoning"]["name"],
                    "loaded": config.MODELS["reasoning"]["name"] in loaded,
                    "idle_sec": (
                        round(time.time() - ollama._reasoning_loaded_time)
                        if ollama._reasoning_loaded_time else None
                    ),
                },
                "encoder": {
                    "name": config.MODELS["encoder"]["name"],
                    "loaded": config.MODELS["encoder"]["name"] in loaded,
                },
            },
            "cache": cache_stats,
            "device_state": {
                "light": "on" if state["light"]["on"] else "off",
                "fan": f"speed {state['fan']['speed']}" if state["fan"]["on"] else "off",
                "plug": "on" if state["plug"]["on"] else "off",
                "temperature": state["temperature"],
                "humidity": state["humidity"],
            },
            "sessions_active": context_manager.active_count(),
            # --- NUEVO: Auto-recuperación y salud del sistema ---
            "health": config.self_heal.report(),
            "circuit_breakers": config.error_tracker.status(),
            "retry_stats": config.get_retry_stats(),
        })

    # ---------------------------------------------------------------
    #  NÚCLEO: LÓGICA DE ENRUTAMIENTO (3 TIERS)
    # ---------------------------------------------------------------

    def _process_message(self, message: str, session) -> dict:
        """Pipeline de enrutamiento de 3 niveles.
        
        Returns:
            dict con response, model_used, tier, latency_ms
        """
        t0 = time.time()

        # ========== TIER 0: ZERO-INFERENCE ==========
        # Sin modelos. Pattern matching directo.
        # IMPORTANTE: usar mensaje ORIGINAL, sin contexto de memoria
        zi_result = config.detect_zero_inference(message)
        if zi_result:
            # Invalidar caché para este mensaje — previene caché envenenado
            config.command_cache.invalidate(message)
            ok, output = config.execute_zero_inference(zi_result)
            elapsed = (time.time() - t0) * 1000
            logger.info(f"[{session.id}] TIER0 zero-inference OK {elapsed:.0f}ms")
            return {
                "response": output,
                "model_used": "zero-inference",
                "model_label": "sin modelo (0 inferencia)",
                "tier": 0,
                "latency_ms": round(elapsed),
            }

        # ========== TIER 1: 1.5B CLASIFICADOR ==========
        # El 1.5B decide: JSON (comando) o DELEGAR (al 9B)
        context = session.get_context()


        # Cache: si este mensaje ya se clasificó, reusar
        cached = config.command_cache.get(message)
        if cached:
            # Cache hit → ejecutar acción directamente
            logger.info(f"[{session.id}] TIER1 cache HIT: {cached[:80]}")
            try:
                action_data = json.loads(cached)
                ok, output = config.execute_json_action(action_data)
                elapsed = (time.time() - t0) * 1000
                return {
                    "response": output,
                    "model_used": "cache",
                    "model_label": "cache (sin inferencia)",
                    "tier": 1,
                    "latency_ms": round(elapsed),
                    "cached": True,
                }
            except (json.JSONDecodeError, Exception):
                # Cache corrupto → ignorar y reprocesar
                pass

        try:
            ok_fast, fast_response = ollama.generate_fast(
                message, SYSTEM_FAST, context,
            )
            if not ok_fast:
                # El 1.5B falló (circuit breaker abierto o error)
                logger.warning(f"1.5B no disponible: {fast_response}")
                raise RuntimeError(f"1.5B: {fast_response}")
        except RuntimeError as e:
            logger.error(f"1.5B error: {e}")
            # Fallback directo a 9B
            try:
                ok7b, resp7b = ollama.generate_reasoning(
                    message, SYSTEM_REASONING, context,
                )
                elapsed = (time.time() - t0) * 1000
                return {
                    "response": resp7b if ok7b else f"⚠️ {resp7b}",
                    "model_used": "reasoning",
                    "model_label": config.MODELS["reasoning"]["label"],
                    "tier": 2,
                    "latency_ms": round(elapsed),
                    "fallback_reason": "1.5B_error",
                }
            except RuntimeError as e2:
                return {
                    "response": f"⚠️ Error de conexión con los modelos locales: {e2}",
                    "model_used": "error",
                    "model_label": "error",
                    "tier": -1,
                    "latency_ms": round((time.time() - t0) * 1000),
                }

        fast_stripped = fast_response.strip()

        # ========== CASO: JSON (comando reconocido) ==========
        if fast_stripped.startswith("{"):
            try:
                action_data = json.loads(fast_stripped)
                # Cachear para futuras repeticiones
                config.command_cache.set(message, fast_stripped)
                # Ejecutar la acción
                ok, output = config.execute_json_action(action_data)
                session.add_message("user", message)
                session.add_message("assistant", output, "fast")
                elapsed = (time.time() - t0) * 1000
                logger.info(
                    f"[{session.id}] TIER1 JSON action={action_data.get('action','?')} "
                    f"{elapsed:.0f}ms"
                )
                return {
                    "response": output,
                    "model_used": "fast",
                    "model_label": config.MODELS["fast"]["label"],
                    "json_action": action_data,
                    "tier": 1,
                    "latency_ms": round(elapsed),
                }
            except json.JSONDecodeError:
                logger.warning(
                    f"[{session.id}] JSON malformado del 1.5B: "
                    f"{fast_stripped[:100]}"
                )
                # Intentar extraer JSON con regex (fallback)
                json_match = None
                # Buscar {...} en la respuesta
                m = re.search(r'\{.*\}', fast_stripped, re.DOTALL)
                if m:
                    try:
                        action_data = json.loads(m.group(0))
                        config.command_cache.set(message, m.group(0))
                        ok, output = config.execute_json_action(action_data)
                        elapsed = (time.time() - t0) * 1000
                        return {
                            "response": output,
                            "model_used": "fast",
                            "model_label": config.MODELS["fast"]["label"],
                            "tier": 1,
                            "latency_ms": round(elapsed),
                            "json_recovered": True,
                        }
                    except json.JSONDecodeError:
                        pass
                # Si no se puede recuperar → delegar al 9B

        # ========== CASO: DELEGAR (pasa al 9B) ==========
        # También aquí si el JSON estaba malformado
        
        # Extraer parámetros del DELEGAR si el clasificador los incluyó
        delegar_params = {}
        if "DELEGAR" in fast_response and "{" in fast_response:
            try:
                m = re.search(r'\{.*\}', fast_response, re.DOTALL)
                if m:
                    delegar_params = json.loads(m.group(0))
                    logger.info(f"[{session.id}] Parámetros extraídos: {delegar_params}")
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Enriquecer mensaje con parámetros detectados por el clasificador
        if delegar_params:
            params_str = ", ".join(f"{k}={v}" for k, v in delegar_params.items())
            message = f"{message}\n[El clasificador detectó: {params_str}]"

        logger.info(
            f"[{session.id}] TIER1 DELEGAR → escalando a 9B"
        )

        try:
            t_reasoning_start = time.time()
            ok7b, resp7b = ollama.generate_reasoning(
                message, SYSTEM_REASONING, context,
            )
            t_reasoning = time.time() - t_reasoning_start
            if not ok7b:
                resp7b = f"⚠️ Error en modelo de razonamiento: {resp7b}"
            elif t_reasoning > 5:
                # Añadir indicador de tiempo de reflexión
                resp7b = f"🤔 *He reflexionado durante {t_reasoning:.0f}s...*\n\n{resp7b}"
        except RuntimeError as e:
            return {
                "response": f"⚠️ Error en modelo de razonamiento: {e}",
                "model_used": "error",
                "model_label": "error",
                "tier": -1,
                "latency_ms": round((time.time() - t0) * 1000),
            }

        session.add_message("user", message)
        session.add_message("assistant", resp7b, "reasoning")
        elapsed = (time.time() - t0) * 1000

        # Descargar 9B si lleva inactivo (solo tras respuesta completa)
        try:
            ollama.unload_idle_reasoning()
        except Exception:
            pass

        return {
            "response": resp7b,
            "model_used": "reasoning",
            "model_label": config.MODELS["reasoning"]["label"],
            "tier": 2,
            "latency_ms": round(elapsed),
        }

    def _handle_chat(self):
        """POST /chat — API interna."""
        body = self._read_body()
        message = body.get("message", "").strip()
        session_id = body.get("session_id", "default")

        if not message:
            self._send_json({"error": "message is required"}, 400)
            return

        session = context_manager.get_or_create(session_id)
        result = self._process_message(message, session)

        self._send_json({
            **result,
            "session_id": session_id,
        })

    def _handle_openai_chat(self):
        """POST /v1/chat/completions — API compatible con OpenAI Chat."""
        t0 = time.time()
        body = self._read_body()
        messages = body.get("messages", [])

        # Extraer el último mensaje de usuario
        user_msg = ""
        for msg in reversed(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role != "user" or not content:
                continue
            if isinstance(content, str):
                user_msg = content
                break
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict):
                        parts.append(part.get("text", ""))
                user_msg = " ".join(parts)
                if user_msg.strip():
                    break

        # DEBUG: log the extracted user message
        logger.info(f"[DEBUG] user_msg=\"{user_msg[:200]}\" total_msgs={len(messages)}")
        
        if not user_msg:
            logger.warning(
                f"No user message in {len(messages)} messages. "
                f"Sample: {json.dumps(messages[:2] if messages else [], ensure_ascii=False)[:300]}"
            )
            self._send_json({"error": "no user message found"}, 400)
            return

        session_id = body.get("user", "openai")
        
        # DEBUG: log full request
        logger.info(f"[DEBUG] session={session_id} user_msg=\"{user_msg[:200]}\" total_msgs={len(messages)} body_keys={list(body.keys())}")
        if len(messages) > 1:
            last_msgs = [(m.get('role','?'), str(m.get('content',''))[:80]) for m in messages[-3:]]
            logger.info(f"[DEBUG] last 3 msgs: {last_msgs}")
        
        session = context_manager.get_or_create(session_id)

        # Procesar con pipeline de 3 tiers
        result = self._process_message(user_msg, session)

        # Responder en formato OpenAI
        openai_resp = {
            "id": f"chatcmpl-{int(t0)}",
            "object": "chat.completion",
            "created": int(t0),
            "model": f"ia-local (tier={result.get('tier', '?')})",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.get("response", ""),
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(user_msg) // 4,
                "completion_tokens": len(result.get("response", "")) // 4,
                "total_tokens": (len(user_msg) + len(result.get("response", ""))) // 4,
            },
        }

        self._send_json(openai_resp)

    def _handle_reset(self):
        """POST /reset — resetear sesión."""
        body = self._read_body()
        session_id = body.get("session_id", "default")
        context_manager.remove(session_id)
        logger.info(f"Sesión {session_id} reseteada")
        self._send_json({"status": "ok", "session_id": session_id})


# ============================================================================
# MAIN
# ============================================================================

start_time = time.time()


def main():
    parser = argparse.ArgumentParser(
        description="Model Router v2 — Enrutamiento 3-tiers"
    )
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--host", type=str, default=config.HOST)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Model Router v2 — Enrutamiento inteligente 3-tiers")
    logger.info(f"  Host: {args.host}:{args.port}")
    logger.info(f"  Tier 0 (zero-inference): {len(config.ZERO_INFERENCE_COMMANDS)} patrones")
    logger.info(f"  Tier 1 (1.5B clasifica): {config.MODELS['fast']['name']}")
    logger.info(f"  Tier 2 (9B razona):      {config.MODELS['reasoning']['name']}")
    logger.info(f"  Escenas disponibles: {list(config.SCENE_MAP.keys())}")
    logger.info(f"  Cache máx: {config.command_cache._maxsize} entradas")
    logger.info("=" * 60)

    # Pre-cargar modelo rápido
    logger.info("Pre-cargando modelo rápido (1.5B) en RAM...")
    try:
        ollama._keep_warm(config.MODELS["fast"]["name"])
        ollama._ensure_loaded(config.MODELS["fast"]["name"])
        logger.info("✅ Modelo rápido cargado")
    except Exception as e:
        logger.warning(f"No se pudo pre-cargar rápido: {e}")

    server = HTTPServer((args.host, args.port), RouterHandler)
    logger.info(f"✅ Model Router v2 escuchando en http://{args.host}:{args.port}")
    logger.info("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Apagando...")
        server.shutdown()


if __name__ == "__main__":
    main()
