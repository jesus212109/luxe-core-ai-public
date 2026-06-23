"""Configuración del Model Router v2 — Zero-inference + clasificación inteligente."""

import json
import logging
import os
import re
import subprocess
import time
import threading
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger("model_router.config")

# ============================================================================
# MODELOS
# ============================================================================

MODELS = {
    "fast": {
        "name": "qwen2.5-coder:1.5b",
        "label": "rápido (1.5B)",
        "keep_alive": -1,           # Siempre en RAM
        "context_window": 8192,     # Prompt del sistema (~14KB) necesita >= 8K
        "max_tokens": 256,          # Solo JSON corto o "DELEGAR"
        "num_thread": 8,
        "ram_mb": 500,
        "temperature": 0.0,         # Determinista
        "role": "clasificador de comandos, NLU determinista",
    },
    "reasoning": {
        "name": "mistral:7b-instruct-q4_K_M",
        "label": "razonador (7B)",
        "keep_alive": "10m",
        "context_window": 4096,
        "max_tokens": 2048,
        "num_thread": 6,
        "ram_mb": 4500,
        "temperature": 0.3,
        "idle_unload_sec": 60,
        "role": "razonamiento, análisis, troubleshooting, conversación",
    },
    "encoder": {
        "name": "bge-m3:latest",
        "label": "encoding (bge-m3)",
        "keep_alive": -1,
        "context_window": 8192,
        "role": "embeddings para clasificación semántica",
    },
}

# ============================================================================
# SERVIDOR
# ============================================================================

HOST = "127.0.0.1"
PORT = 18790
MAX_SESSIONS = 50
MAX_CONTEXT_MESSAGES = 20

OLLAMA_BASE_URL = "http://localhost:11434"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME_SH_PATH = os.path.join(PROJECT_ROOT, "server/tools/home.sh")

# ============================================================================
# INTENTOS / CLASIFICACIÓN
# ============================================================================

# --- Intenciones que se resuelven con el modelo rápido ---
FAST_INTENTS = {
    "device_control": [
        "enciende", "apaga", "prende", "apagar", "encender",
        "sube", "baja", "aumenta", "disminuye",
        "temperatura", "termostato", "luz", "luz de",
        "ventilador", "fan", "speed", "velocidad",
        "timer", "temporizador", "cuenta atrás",
        "luz on", "luz off", "fan on", "fan off",
        "enchufe", "plug", "conecta", "desconecta",
        "modo", "scene", "escena", "rutina",
        "hace calor", "hace frío", "qué calor", "qué frío",
        "noche", "dormir", "cama", "descansar",
        "todo on", "todo off", "todo apagado",
        "he llegado", "vuelvo a casa", "salgo de casa",
        "cine", "película", "relax", "lectura", "leer",
        "fiesta", "estudio", "estudiar",
    ],
    "status_query": [
        "estado", "status", "cómo está", "qué tal",
        "temperatura ambiente", "humedad", "sensor",
        "encendido", "apagado", "consumo",
        "cómo está la casa", "cómo está todo",
        "está encendida", "está apagada",
    ],
    "simple_qa": [
        "qué es", "quién es", "dónde está", "cuándo",
        "qué hora", "qué día", "hola", "gracias",
        "buenos días", "buenas tardes", "buenas noches",
    ],
    "greeting": [
        "hola", "hey", "buenas", "qué tal", "saluda",
    ],
}

# --- Intenciones que requieren modelo de razonamiento ---
REASONING_INTENTS = {
    "code_generation": [
        "escribe código", "programa", "script", "función",
        "código python", "código c++", "algoritmo",
        "implementa", "desarrolla",
    ],
    "analysis": [
        "analiza", "compara", "evalúa", "diagnostica",
        "por qué", "explícame", "cómo funciona",
        "investiga", "averigua", "determina",
    ],
    "planning": [
        "plan", "estrategia", "arquitectura", "diseña",
        "organiza", "estructura", "sistema",
    ],
    "troubleshooting": [
        "error", "fallo", "bug", "problema", "no funciona",
        "exception", "traceback", "se rompió",
    ],
}

# ============================================================================
# ESCENAS — Mapeo de nombre de escena → lista de acciones de home.sh
# ============================================================================

SCENE_MAP = {
    "night": {
        "home_actions": [("night", [])],
        "description": "Modo noche: luz apagada, ventilador al mínimo",
    },
    "all_off": {
        "home_actions": [("all_off", [])],
        "description": "Todo apagado",
    },
    "all_on": {
        "home_actions": [("all_on", [])],
        "description": "Todo encendido",
    },
    "relax": {
        "home_actions": [("light_on", []), ("fan_speed", ["1"])],
        "description": "Modo relax: luz encendida, ventilador suave",
    },
    "cine": {
        "home_actions": [("light_off", []), ("fan_off", [])],
        "description": "Modo cine: luz apagada, ventilador apagado",
    },
    "lectura": {
        "home_actions": [("light_on", []), ("fan_speed", ["2"])],
        "description": "Modo lectura: luz encendida, ventilador medio",
    },
    "fiesta": {
        "home_actions": [("light_on", []), ("fan_speed", ["3"])],
        "description": "Modo fiesta: luz encendida, ventilador medio",
    },
    "estudio": {
        "home_actions": [("light_on", []), ("fan_speed", ["1"])],
        "description": "Modo estudio: luz encendida, ventilador suave",
    },
}

# ============================================================================
# ZERO-INFERENCE TIER — Comandos tan directos que no necesitan modelo
# ============================================================================

def _build_zero_inference():
    """Construye el diccionario de comandos de cero inferencia.
    
    Returns dict:
        "normalized_pattern" → ("home_action", [args], description)
    """
    commands = {}

    # --- LUZ ---
    light_on_variants = [
        # Directos
        "enciende la luz", "enciende las luces", "luz", "luces",
        "luz on", "luces on", "enciende luz", "enciende luces",
        "prende la luz", "prende las luces", "prende luz",
        "luz encendida", "luces encendidas",
        "enciende", "enciéndelo", "enciéndela",
        "dame luz", "quiero luz", "pon la luz",
        # Localizaciones
        "enciende la luz del salón", "enciende la luz de la habitación",
        "luz del salón", "luz de la habitación",
        "luz salón", "luz habitación",
        "enciende la luz de la cocina", "luz de la cocina",
        "enciende la luz de arriba", "luz de arriba",
        # Lámpara / iluminación
        "enciende la lámpara", "lámpara", "lámpara on",
        "lámpara encendida", "prende la lámpara",
        "iluminación", "iluminación on",
        "ilumina", "ilumíname", "alumbra", "alúmbrame",
        # Imperativos y peticiones
        "pon las luces", "ponme la luz", "pon luz",
        "activa la luz", "activa las luces",
        "necesito luz", "necesito la luz",
        "enciende la luz por favor", "luz por favor",
        "se fue la luz", "vuelve la luz",
        "enciende eso", "enciéndelo ya",
        "claridad", "que haya luz", "que se vea",
        # Inglés mezclado
        "light on", "light", "turn on the light",
        "turn on lights",
    ]
    for v in light_on_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("light_on", [], "💡 Luz encendida")

    light_off_variants = [
        # Directos
        "apaga la luz", "apaga la luz por favor", "apagar la luz", "apagar la luz por favor", "apaga las luces", "luz off", "luces off",
        "apaga luz", "apaga luces", "luz apagada", "luces apagadas",
        "apaga", "apágalo", "apagala", "apágalas",
        "oscuro", "a oscuras", "oscuridad",
        "quita la luz", "quita las luces",
        # Localizaciones
        "apaga la luz del salón", "apaga la luz de la habitación",
        "apaga la luz de la cocina", "apaga la luz de arriba",
        # Lámpara / iluminación
        "apaga la lámpara", "lámpara off", "lámpara apagada",
        "iluminación off", "iluminación apagada",
        "desconecta la luz", "desconecta las luces",
        # Imperativos y peticiones
        "corta la luz", "corta las luces",
        "no quiero luz", "no necesito luz",
        "sin luz", "que no haya luz",
        "elimina la luz", "basta de luz",
        "se acabó la luz", "apagón",
        # Inglés mezclado
        "light off", "turn off the light",
        "turn off lights",
    ]
    for v in light_off_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("light_off", [], "💡 Luz apagada")

    # --- VENTILADOR ---
    fan_on_variants = [
        # Directos
        "enciende el ventilador", "ventilador", "ventilador on",
        "pon el ventilador", "ventilador encendido",
        "enciende ventilador", "prende el ventilador",
        "activa el ventilador", "ventilador activado",
        # Aire / ventilación
        "enciende el aire", "aire", "aire on",
        "pon el aire", "ponme el aire", "ponme el ventilador",
        "activa el aire", "prende el aire",
        # Imperativos
        "quiero aire", "necesito aire", "necesito ventilador",
        "dame aire", "dame ventilador", "ventílame",
        "refréscame", "ventilación", "ventilame",
        "corre el ventilador", "corre el aire",
        "pon el fan", "fan on", "fan",
        # Inglés mezclado
        "turn on the fan",
    ]
    for v in fan_on_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("fan_on", [], "🌀 Ventilador encendido")

    fan_off_variants = [
        # Directos
        "apaga el ventilador", "ventilador off", "ventilador apagado",
        "ponlo al 0",
        "para el ventilador", "ventilador para",
        "apaga ventilador", "desactiva el ventilador",
        "ventilador desactivado", "detén el ventilador",
        "quita el ventilador",
        # Aire / ventilación
        "apaga el aire", "aire off", "para el aire",
        "quita el aire", "corta el aire", "corta el ventilador",
        "desactiva el aire",
        # Imperativos
        "no quiero aire", "no quiero ventilador",
        "sin aire", "basta de aire", "basta de ventilador",
        "para ya el aire", "detén el aire",
        "se acabó el aire", "suficiente aire",
        "apaga el fan", "fan off",
        # Inglés mezclado
        "turn off the fan",
    ]
    for v in fan_off_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("fan_off", [], "🌀 Ventilador apagado")

    # --- ENCHUFE ---
    plug_on_variants = [
        "enciende el enchufe", "enchufe", "enchufe on",
        "enchufe encendido", "conecta el enchufe",
        "prende el enchufe", "enchufe conectado",
        "activa el enchufe", "toma de corriente on",
        "enchufa", "enchúfalo", "enchúfala",
        "conecta la corriente", "corriente on",
        "pon el enchufe", "pon la corriente",
        "dame corriente", "activa la corriente",
        "conecta", "conecta el aparato",
        "plug on", "turn on the plug",
        # humificador = enchufe (mismo dispositivo)
        "enciende el humificador", "humificador", "humificador on",
        "humificador encendido", "prende el humificador",
        "activa el humificador", "pon el humificador",
    ]
    for v in plug_on_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("plug_on", [], "🔌 Enchufe encendido")

    plug_off_variants = [
        "apaga el enchufe", "enchufe off", "enchufe apagado",
        "desconecta el enchufe", "enchufe desconectado",
        "apaga enchufe", "quita el enchufe",
        "desenchufa", "desenchúfalo", "desenchúfala",
        "desconecta", "desconecta la corriente",
        "corta la corriente", "corriente off",
        "quita la corriente", "sin corriente",
        "no quiero enchufe", "basta de enchufe",
        "plug off", "turn off the plug",
        # humificador = enchufe (mismo dispositivo)
        "apaga el humificador", "humificador off", "humificador apagado",
        "desconecta el humificador", "para el humificador",
    ]
    for v in plug_off_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("plug_off", [], "🔌 Enchufe apagado")

    # --- ESCENAS DIRECTAS ---
    night_variants = [
        "modo noche", "noche", "a dormir", "buenas noches",
        "pon la luz en modo noche", "luz modo noche", "pon modo noche",
        "hora de dormir", "modo dormir", "modo nocturno",
        "me voy a la cama", "me voy a dormir", "quiero dormir",
        "a descansar", "me voy a descansar", "hora de descansar",
        # Más coloquiales
        "me voy a tumbar", "me voy a echar",
        "me acuesto", "a acostarse", "hora de acostarse",
        "me retiro a descansar", "me voy al sobre",
        "a mimir", "hora de mimir", "a la cama",
        "me voy a tumbar a descansar en la cama",
        "a sobar", "a dormir la siesta", "a echar la siesta",
        "me echo una siesta", "siesta",
        "buenas noches luxe",
    ]
    for v in night_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_night", [], "🌙 Modo noche")

    all_off_variants = [
        # Directos
        "apaga todo", "todo off", "todo apagado",
        "apagar todo", "apaga la casa", "apagar la casa",
        "apágalo todo", "apagamos",
        # Salir de casa
        "cierra la casa", "me voy", "salgo de casa", "me voy de casa",
        "salir de casa", "me marcho", "me piro",
        "hasta luego", "adiós", "me ausento",
        "salgo", "me voy ya", "marchando",
        # Salir a sitios concretos
        "me voy a comer", "me voy a cenar", "me voy a desayunar",
        "me voy al baño", "me voy a clase", "me voy a la calle",
        "me voy a la uni", "me voy a la universidad",
        "me voy a trabajar", "me voy al trabajo",
        "me voy a comprar", "me voy al super",
        "me voy a hacer la compra", "me voy de compras",
        "me voy al gimnasio", "me voy a entrenar",
        "me voy de paseo", "me voy a pasear",
        "me voy a dar una vuelta", "me voy al médico",
        # Señales de abandono
        "se acabó", "fin", "terminamos", "cerramos",
        "apaga la casa por favor", "todo fuera",
        # Inglés mezclado
        "all off", "turn everything off", "shut down everything",
    ]
    for v in all_off_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_all_off", [], "🔌 Todo apagado")

    all_on_variants = [
        # Llegadas
        "enciende todo", "todo on", "todo encendido",
        "encender todo", "enciende la casa",
        "he llegado", "vuelvo a casa", "ya estoy en casa",
        "estoy en casa", "llegué", "acabo de llegar",
        "he vuelto", "ya estoy aquí", "estoy de vuelta",
        "he llegado de clase", "he llegado de comer",
        "he llegado de la calle", "he llegado de la uni",
        "he llegado del trabajo", "he llegado de comprar",
        "ya estoy", "estoy aquí",
        # Apertura
        "abre la casa", "abrir la casa",
        "enciéndelo todo", "prende todo",
        "vamos para casa", "de vuelta",
        "he entrado", "estoy dentro",
        # Inglés
        "all on", "turn everything on",
    ]
    for v in all_on_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_all_on", [], "💡🌀 Todo encendido")

    # --- MODO RELAX ---
    relax_variants = [
        "modo relax", "relax", "modo descanso",
        "a relajarse", "quiero relajarme", "me relajo",
        "tranquilo", "tranqui", "modo tranquilo",
        "modo calma", "relajado", "a relajarme",
    ]
    for v in relax_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_relax", [], "🧘 Modo relax")

    # --- MODO CINE ---
    cine_variants = [
        "modo cine", "cine", "ver película", "ver peli",
        "a ver la tele", "modo película", "modo peli",
        "voy a ver una peli", "voy a ver una película",
        "a ver una serie", "vamos a ver la tele",
        "netflix", "hora de serie", "maratón de series",
        "modo tele", "voy a ver la tele",
        "peli", "película", "serie",
        "modo netflix", "hora de peli",
    ]
    for v in cine_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_cine", [], "🎬 Modo cine")

    # --- MODO LECTURA ---
    lectura_variants = [
        "modo lectura", "lectura", "leer", "a leer",
        "quiero leer", "modo leer", "a leer un rato",
        "voy a leer", "hora de leer", "modo libro",
        "ponte a leer", "a leer un libro",
    ]
    for v in lectura_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_lectura", [], "📖 Modo lectura")

    # --- MODO TRABAJO / ESTUDIO ---
    estudio_variants = [
        "modo estudio", "estudio", "estudiar", "a estudiar",
        "modo trabajar", "trabajar", "a trabajar",
        "modo trabajo", "hora de estudiar", "voy a estudiar",
        "me pongo a trabajar", "me pongo a estudiar",
        "hora de currar", "a currar", "a programar",
        "modo programación", "modo programar", "programar",
        "hora de programar", "work mode",
    ]
    for v in estudio_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_estudio", [], "💻 Modo trabajo/estudio")

    # --- MODO FIESTA ---
    fiesta_variants = [
        "modo fiesta", "fiesta", "de fiesta",
        "modo party", "party", "de marcha",
        "a celebrar", "vamos de fiesta", "pachanga",
        "modo celebración", "celebración",
        "modo discoteca", "discoteca",
    ]
    for v in fiesta_variants:
        commands[re.sub(r'\s+', ' ', v.strip().lower())] = ("scene_fiesta", [], "🎉 Modo fiesta")

    # --- CONSULTAS DIRECTAS ---
    query_variants = {
        # Temperatura
        "temperatura": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "qué temperatura hace": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "temperatura ambiente": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "sensor": ("query_temp", [], "🌡️ Consultando sensores..."),
        "sensor de temperatura": ("query_temp", [], "🌡️ Consultando sensores..."),
        "qué temperatura": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "temp": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "cuántos grados hace": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "cuántos grados": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "grados": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "dime la temperatura": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "mide la temperatura": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "lectura del sensor": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "qué tal el sensor": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "qué temperatura hay": ("query_temp", [], "🌡️ Consultando temperatura..."),
        "temperatura de la casa": ("query_temp", [], "🌡️ Consultando temperatura..."),
        # Estado general
        "estado": ("query_status", [], "📊 Consultando estado..."),
        "cómo está la casa": ("query_status", [], "📊 Consultando estado..."),
        "cómo está todo": ("query_status", [], "📊 Consultando estado..."),
        "status": ("query_status", [], "📊 Consultando estado..."),
        "qué tal la casa": ("query_status", [], "📊 Consultando estado..."),
        "cómo va la casa": ("query_status", [], "📊 Consultando estado..."),
        "cómo vamos": ("query_status", [], "📊 Consultando estado..."),
        "qué pasa en casa": ("query_status", [], "📊 Consultando estado..."),
        "dime cómo está la casa": ("query_status", [], "📊 Consultando estado..."),
        "cómo va todo": ("query_status", [], "📊 Consultando estado..."),
        "qué hay": ("query_status", [], "📊 Consultando estado..."),
        "resumen": ("query_status", [], "📊 Consultando estado..."),
        "informe": ("query_status", [], "📊 Consultando estado..."),
        "está encendida la luz": ("query_status", [], "📊 Consultando estado..."),
        "está el ventilador encendido": ("query_status", [], "📊 Consultando estado..."),
        # Enchufe
        "estado del enchufe": ("query_plug", [], "🔌 Consultando enchufe..."),
        "cómo está el enchufe": ("query_plug", [], "🔌 Consultando enchufe..."),
        "enchufe estado": ("query_plug", [], "🔌 Consultando enchufe..."),
        "el enchufe está encendido": ("query_plug", [], "🔌 Consultando enchufe..."),
        # Notificaciones
        "notificaciones": ("query_notif", [], "📬 Revisando notificaciones..."),
        "qué hay de nuevo": ("query_notif", [], "📬 Revisando notificaciones..."),
        "novedades": ("query_notif", [], "📬 Revisando notificaciones..."),
        "avisos": ("query_notif", [], "📬 Revisando notificaciones..."),
        "alertas": ("query_notif", [], "📬 Revisando notificaciones..."),
        # Confort
        "confort": ("query_comfort", [], "🛋️ Analizando confort..."),
        "recomendaciones": ("query_comfort", [], "🛋️ Analizando confort..."),
        "qué me recomiendas": ("query_comfort", [], "🛋️ Analizando confort..."),
        "sensación térmica": ("query_comfort", [], "🛋️ Analizando confort..."),
        "estoy a gusto": ("query_comfort", [], "🛋️ Analizando confort..."),
        "qué me aconsejas": ("query_comfort", [], "🛋️ Analizando confort..."),
        "aconsejame": ("query_comfort", [], "🛋️ Analizando confort..."),
        # Exterior
        "temperatura exterior": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "qué temperatura hace fuera": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "temperatura fuera": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "qué tiempo hace": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "tiempo en la calle": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "clima exterior": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "temperatura en la calle": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "qué temperatura hay fuera": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "hace en la calle": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "en la calle": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "calle que temperatura": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "y fuera": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "fuera": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "tiempo": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "clima": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "meteorología": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "qué tiempo va a hacer": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "pronóstico": ("query_outdoor", [], "🌍 Consultando exterior..."),
        "va a llover": ("query_outdoor", [], "🌍 Consultando exterior..."),
        # Análisis completo
        "análisis": ("query_full", [], "🔍 Análisis completo del ambiente..."),
        "confort completo": ("query_full", [], "🔍 Análisis completo del ambiente..."),
        "cómo está el ambiente": ("query_full", [], "🔍 Análisis completo del ambiente..."),
        "análisis completo": ("query_full", [], "🔍 Análisis completo del ambiente..."),
        "analiza la casa": ("query_full", [], "🔍 Análisis completo del ambiente..."),
        "diagnóstico": ("query_full", [], "🔍 Análisis completo del ambiente..."),
    }
    for v, action in query_variants.items():
        commands[v.lower()] = action

    return commands

ZERO_INFERENCE_COMMANDS = _build_zero_inference()

# Patrones regex para comandos con parámetros variables (velocidad)
SPEED_PATTERNS = [
    # "velocidad 0" = apagar
    (re.compile(r'(?:velocidad|speed)\s*0'), "fan_off"),
    # "velocidad 3", "ventilador al 5", "velocidad N"
    (re.compile(r'(?:velocidad|ventilador\s*(?:al|a\s*la)?|speed)\s*(\d)'), "fan_speed"),
    # "pon el ventilador al 3", "pon ventilador velocidad 5"
    (re.compile(r'(?:pon\s*(?:el|la)?\s*(?:ventilador|velocidad)\s*(?:al|a\s*la)?)\s*(\d)'), "fan_speed"),
    # "ponlo al 3", "ponla al 5", "ponle al 2"
    (re.compile(r'pon(?:lo|la|le)\s*(?:al|a\s*la)?\s*(\d)'), "fan_speed"),
    # "sube el ventilador" / "baja el ventilador"
    (re.compile(r'(?:sube|baja|aumenta|disminuye)\s*(?:el|la)?\s*(?:ventilador|velocidad|aire)?'), "fan_adjust"),
    # "ventilador más rápido/lento/mínimo/máximo"
    (re.compile(r'(?:ventilador|aire|velocidad)\s*(?:más|al)\s*(?:rápido|lento|mínimo|máximo|alta|baja|fuerte|suave|flojo)'), "fan_adjust_extreme"),
    # "hace calor" / "qué frío"
    (re.compile(r'(?:hace|qué)\s*(calor|frío)'), "temp_reaction"),
    # "más fuerte" / "más flojo" / "más rápido"
    (re.compile(r'(?:más|menos|ponlo|dale)\s*(?:fuerte|flojo|rápido|lento|suave|aire|caña|marcha|velocidad)'), "fan_adjust_extreme"),
    # "al 0" → apagar
    (re.compile(r'^al\s*0$'), "fan_off"),
    # "al 1", "al 2", etc.
    (re.compile(r'^al\s*(\d)$'), "fan_speed"),
    # Dígito suelto: "0" → apagar, "1"-5" → velocidad del ventilador
    (re.compile(r'^0$'), "fan_off"),
    (re.compile(r'^([1-5])$'), "fan_speed"),
]

# ============================================================================
# GESTOR DE ESTADO DE DISPOSITIVOS (en RAM)
# ============================================================================

class DeviceStateManager:
    """Mantiene el último estado conocido de cada dispositivo.
    
    Esto permite responder consultas instantáneamente sin tocar hardware,
    y recordar últimos estados (p.ej. última velocidad del ventilador).
    Thread-safe para acceso concurrente desde múltiples sesiones.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "fan": {"on": False, "speed": 0, "last_speed": 3},
            "light": {"on": False, "last_on": False},
            "plug": {"on": False, "last_on": False},
            "temperature": None,       # °C
            "humidity": None,          # %
            "battery_mv": None,        # Sensor battery mV
            "last_scan_time": None,
        }

    # --- Mutators with auto-persistence ---

    def set_fan_speed(self, speed: int):
        with self._lock:
            self._state["fan"]["on"] = speed > 0
            self._state["fan"]["speed"] = speed
            if speed > 0:
                self._state["fan"]["last_speed"] = speed

    def set_fan_on(self):
        with self._lock:
            speed = self._state["fan"]["last_speed"]
            self._state["fan"]["on"] = True
            self._state["fan"]["speed"] = speed

    def set_fan_off(self):
        with self._lock:
            if self._state["fan"]["on"] and self._state["fan"]["speed"] > 0:
                self._state["fan"]["last_speed"] = self._state["fan"]["speed"]
            self._state["fan"]["on"] = False
            self._state["fan"]["speed"] = 0

    def set_light_on(self):
        with self._lock:
            self._state["light"]["on"] = True
            self._state["light"]["last_on"] = True

    def set_light_off(self):
        with self._lock:
            self._state["light"]["on"] = False

    def set_plug_on(self):
        with self._lock:
            self._state["plug"]["on"] = True
            self._state["plug"]["last_on"] = True

    def set_plug_off(self):
        with self._lock:
            self._state["plug"]["on"] = False

    def update_sensor(self, temperature: float = None, humidity: float = None,
                      battery_mv: int = None):
        """Actualiza los datos del sensor en RAM (desde un scan exitoso)."""
        with self._lock:
            if temperature is not None:
                self._state["temperature"] = temperature
            if humidity is not None:
                self._state["humidity"] = humidity
            if battery_mv is not None:
                self._state["battery_mv"] = battery_mv
            self._state["last_scan_time"] = time.time()

    def set_sensor(self, temp: float, hum: float, battery_mv: Optional[int] = None):
        with self._lock:
            self._state["temperature"] = temp
            self._state["humidity"] = hum
            self._state["battery_mv"] = battery_mv
            self._state["last_scan_time"] = time.time()

    # --- Accessors ---

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def get_fan_status(self) -> str:
        with self._lock:
            s = self._state["fan"]
            if s["on"]:
                return f"🌀 Ventilador encendido a velocidad {s['speed']}"
            return "🌀 Ventilador apagado"

    def get_light_status(self) -> str:
        with self._lock:
            return "💡 Luz encendida" if self._state["light"]["on"] else "💡 Luz apagada"

    def get_plug_status(self) -> str:
        with self._lock:
            return "🔌 Enchufe encendido" if self._state["plug"]["on"] else "🔌 Enchufe apagado"

    def get_summary(self) -> str:
        """Devuelve resumen legible del estado de la casa."""
        with self._lock:
            parts = []
            parts.append(self._get_light_status_nolock())
            parts.append(self._get_fan_status_nolock())
            parts.append(self._get_plug_status_nolock())
            if self._state["temperature"] is not None:
                parts.append(f"🌡️ {self._state['temperature']:.1f}°C")
            if self._state["humidity"] is not None:
                parts.append(f"💧 {self._state['humidity']:.0f}% HR")
            return " | ".join(parts)

    def _get_light_status_nolock(self) -> str:
        return "💡 Luz encendida" if self._state["light"]["on"] else "💡 Luz apagada"

    def _get_fan_status_nolock(self) -> str:
        s = self._state["fan"]
        if s["on"]:
            return f"🌀 Ventilador a velocidad {s['speed']}"
        return "🌀 Ventilador apagado"

    def _get_plug_status_nolock(self) -> str:
        return "🔌 Enchufe encendido" if self._state["plug"]["on"] else "🔌 Enchufe apagado"


# Singleton
device_state = DeviceStateManager()


# ============================================================================
# CACHE DE COMANDOS (LRU)
# ============================================================================

class CommandCache:
    """Cache LRU para evitar llamar al modelo con comandos repetidos.
    
    Almacena: mensaje_normalizado → (acción_json, timestamp)
    """

    def __init__(self, maxsize: int = 100):
        self._cache = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[str]:
        """Devuelve la acción cacheada o None."""
        normalized = self._normalize(key)
        with self._lock:
            if normalized in self._cache:
                self._cache.move_to_end(normalized)
                self._hits += 1
                return self._cache[normalized]
            self._misses += 1
            return None

    def set(self, key: str, value: str):
        normalized = self._normalize(key)
        with self._lock:
            self._cache[normalized] = value
            self._cache.move_to_end(normalized)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def invalidate(self, key: str):
        """Elimina una entrada del caché (útil si se detecta mala clasificación)."""
        normalized = self._normalize(key)
        with self._lock:
            if normalized in self._cache:
                del self._cache[normalized]
                return True
            return False

    def clear(self):
        """Limpia todo el caché."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 1),
            }

    @staticmethod
    def _normalize(key: str) -> str:
        """Normaliza el texto para usar como clave de cache."""
        return re.sub(r'\s+', ' ', key.strip().lower())


# Singleton
command_cache = CommandCache(maxsize=200)


# ============================================================================
# EJECUCIÓN DE ACCIONES VÍA HOME.SH
# ============================================================================

# Mapa de respuestas raw → mensajes amigables
NICE_RESPONSES = {
    # Acciones canónicas
    "light_on": "💡 Luz encendida",
    "light_off": "💡 Luz apagada",
    "fan_on": "🌀 Ventilador encendido",
    "fan_off": "🌀 Ventilador apagado",
    "plug_on": "🔌 Enchufe encendido",
    "plug_off": "🔌 Enchufe apagado",
    "night": "🌙 Modo noche",
    "all_off": "🔌 Todo apagado",
    "fan_off": "🌀 Ventilador apagado",
    "light_off": "💡 Luz apagada",
    "off": "🔌 Todo apagado",
    "all_on": "💡🌀 Todo encendido",
    # Respuestas del ESP32 (FanLamp)
    "0": "🔌 Todo apagado",
    "1": "🌀 Ventilador a velocidad 1",
    "2": "🌀 Ventilador a velocidad 2",
    "3": "🌀 Ventilador a velocidad 3",
    "4": "🌀 Ventilador a velocidad 4",
    "5": "🌀 Ventilador a velocidad 5",
    "f": "🌀 Ventilador encendido (restaurando última velocidad)",
    "F": "🌀 Ventilador apagado (solo ventilador)",
    "l": "💡 Luz encendida",
    "L": "💡 Luz apagada",
    "n": "🌙 Modo noche",
    "on": "🌀 Ventilador encendido",
    # Posibles respuestas del ESP32 (speed prefix)
    "sp1": "🌀 Ventilador a velocidad 1",
    "sp2": "🌀 Ventilador a velocidad 2",
    "sp3": "🌀 Ventilador a velocidad 3",
    "sp4": "🌀 Ventilador a velocidad 4",
    "sp5": "🌀 Ventilador a velocidad 5",
    # Vacío
    "": "✅ Hecho",
}


def _nice_output(raw: str, default_nice: str) -> str:
    """Convierte respuesta raw del hardware en mensaje amigable.
    
    Maneja:
    - Respuestas cortas del ESP32 ("sp3", "l", "0", etc.)
    - Respuestas JSON del sensor BLE
    - Respuestas del enchufe Tuya ("plug: ON", "plug: OFF")
    - Respuestas multilínea (múltiples comandos ejecutados)
    - Filtra líneas de boot del ESP32 (ets, rst:, load:, etc.)
    """
    stripped = raw.strip()
    if not stripped:
        return default_nice
    
    # Filtrar líneas de boot del ESP32 que se cuelan en el output
    BOOT_PATTERNS = [
        "ets Jul", "rst:0x", "configsip:", "clk_drv:",
        "mode:DIO", "mode:DOUT", "mode:QIO", "mode:QOUT",
        "load:0x3fff", "entry 0x", "SPIWP:0x",
        "ho 0 tail", "chksum 0x", "waiting for",
        "SW_CPU_RESET", "POWERON_RESET", "SPI_FAST_FLASH_BOOT",
    ]
    lines = stripped.split("\n")
    clean_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Saltar líneas de boot del ESP32
        if any(pattern in line_stripped for pattern in BOOT_PATTERNS):
            continue
        # Saltar líneas que son solo "OK" (boot confirmación, no es respuesta de comando)
        if line_stripped == "OK":
            continue
        clean_lines.append(line_stripped)
    
    if clean_lines:
        stripped = "\n".join(clean_lines)
    else:
        return default_nice
    
    # Si es un JSON (p.ej. scan), procesarlo primero — antes del chequeo multilínea
    # PERO: si el default NO es de sensor (no estamos escaneando), ignorar JSON de sensor
    if stripped.startswith("{"):
        if "sensor" in default_nice.lower() or "escane" in default_nice.lower():
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    sensors = data.get("sensors", [])
                    if sensors:
                        s = sensors[0]
                        temp = s.get("temperature_c", "?")
                        hum = s.get("humidity_pct", "?")
                        bat = s.get("battery_mv", "")
                        msg = f"🌡️ {temp}°C | 💧 {hum}%"
                        if bat:
                            msg += f" | 🔋 {bat}mV"
                        if data.get("rssi"):
                            msg += f" | 📶 {data['rssi']}dBm"
                        return msg
                    return f"📡 Lectura de sensor"
            except (json.JSONDecodeError, IndexError):
                pass
        else:
            # JSON en comando NO-scan → contaminación del sensor daemon → ignorar
            return default_nice
    
    # Respuesta directa conocida
    if stripped in NICE_RESPONSES:
        return NICE_RESPONSES[stripped]
    
    # Respuesta multilínea (varios comandos ejecutados)
    lines = stripped.split("\n")
    if len(lines) > 1:
        nice_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line in NICE_RESPONSES:
                nice_lines.append(NICE_RESPONSES[line])
            elif line.startswith("plug:"):
                nice_lines.append(line.replace("plug:", "🔌").strip())
            else:
                nice_lines.append(line)
        if nice_lines:
            return " | ".join(nice_lines)
    
    # Respuesta del enchufe Tuya
    if stripped.startswith("plug:"):
        return stripped.replace("plug:", "🔌").strip()
    
    # Para respuestas de speed como "sp3","sp5" con otras palabras
    import re
    for prefix in ["sp1", "sp2", "sp3", "sp4", "sp5"]:
        if prefix in stripped:
            return NICE_RESPONSES.get(prefix, default_nice)
    
    # Texto libre
    return stripped


def _update_state_from_scan(raw_output: str) -> None:
    """Extrae datos del sensor del output JSON y actualiza device_state."""
    try:
        # El output puede tener el prefijo [RECUPERADO...]
        clean = raw_output
        if clean.startswith("[RECUPERADO"):
            idx = clean.find("] ")
            if idx > 0:
                clean = clean[idx + 2:]
        data = json.loads(clean.strip())
        if isinstance(data, dict):
            sensors = data.get("sensors", [])
            if sensors:
                s = sensors[0]
                device_state.update_sensor(
                    temperature=s.get("temperature_c"),
                    humidity=s.get("humidity_pct"),
                    battery_mv=s.get("battery_mv"),
                )
    except (json.JSONDecodeError, KeyError, IndexError):
        pass


SENSOR_DAEMON_CACHE = "/tmp/latest_sensor.json"
SENSOR_DAEMON_MAX_AGE = 120  # segundos — máximo tiempo sin lectura fresca


def _read_daemon_cache() -> dict | None:
    """Lee la última lectura del daemon de sensores.
    
    Returns:
        dict con temperature_c, humidity_pct, battery_mv, timestamp, o None.
    """
    try:
        if not os.path.exists(SENSOR_DAEMON_CACHE):
            return None
        mtime = os.path.getmtime(SENSOR_DAEMON_CACHE)
        if time.time() - mtime > SENSOR_DAEMON_MAX_AGE:
            return None  # Dato demasiado viejo
        with open(SENSOR_DAEMON_CACHE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _run_home_command(action: str, args: list[str] = None, timeout: int = 15) -> tuple[bool, str]:
    """Ejecuta un comando de home.sh y devuelve (éxito, output formateado)."""
    if args is None:
        args = []
    cmd = ["bash", HOME_SH_PATH, action] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": f"{PROJECT_ROOT}/server"},
        )
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode == 0:
            return True, output
        else:
            return False, f"⚠️ Error ({result.returncode}): {output}"
    except subprocess.TimeoutExpired:
        return False, "⏰ Timeout ejecutando comando"
    except FileNotFoundError:
        return False, f"⚠️ home.sh no encontrado en {HOME_SH_PATH}"
    except Exception as e:
        return False, f"⚠️ {e}"


def execute_json_action(action_data: dict) -> tuple[bool, str]:
    """Ejecuta una acción a partir del JSON devuelto por el clasificador 1.5B.
    
    Args:
        action_data: dict con {"action": ..., "params": {...}}
    
    Returns:
        (success: bool, mensaje: str)
        Si hubo retry exitoso, el mensaje incluye nota de auto-recuperación.
    """
    action = action_data.get("action", "")
    params = action_data.get("params", {})
    messages = []

    def _wrap(ok: bool, nice_msg: str, raw_out: str) -> tuple[bool, str]:
        """Envuelve el mensaje con nota de recuperación si aplica."""
        clean = raw_out
        note = ""
        # Extraer TODOS los prefijos [RECUPERADO...] y quedarnos solo con uno
        while "[RECUPERADO" in clean:
            s = clean.find("[RECUPERADO")
            e = clean.find("] ", s)
            if e > 0:
                note = f"🔧 {clean[s:e+1]} → "
                clean = clean[e+2:]
            else:
                break
        formatted = _nice_output(clean.strip(), nice_msg)
        if note:
            return True, f"{note}{formatted}"
        return ok, formatted

    # --- Acciones individuales (con retry automático) ---
    if action == "light_on":
        ok, out = _run_home_command_with_retry("light_on")
        if ok:
            device_state.set_light_on()
        return _wrap(ok, _nice_output(out, "💡 Luz encendida"), out)

    elif action == "light_off":
        ok, out = _run_home_command_with_retry("light_off")
        if ok:
            device_state.set_light_off()
        return _wrap(ok, _nice_output(out, "💡 Luz apagada"), out)

    elif action == "fan_on":
        ok, out = _run_home_command_with_retry("fan_on")
        if ok:
            device_state.set_fan_on()
        return _wrap(ok, _nice_output(out, "🌀 Ventilador encendido"), out)

    elif action == "fan_off":
        ok, out = _run_home_command_with_retry("fan_off")
        if ok:
            device_state.set_fan_off()
        return _wrap(ok, _nice_output(out, "🌀 Ventilador apagado"), out)

    elif action == "fan_speed":
        speed = int(params.get("speed", 1))
        if 0 <= speed <= 5:
            ok, out = _run_home_command_with_retry("fan_speed", [str(speed)])
            if ok:
                device_state.set_fan_speed(speed)
                # Registrar velocidad manual para SmartAdvisor
                from model_router.comfort import ComfortAdvisor
                ComfortAdvisor.record_manual_speed(speed)
            return _wrap(ok, _nice_output(out, f"🌀 Ventilador a velocidad {speed}"), out)
        return False, f"⚠️ Velocidad {speed} no válida (0-5)"

    elif action == "plug_on":
        ok, out = _run_home_command_with_retry("plug_on")
        if ok:
            device_state.set_plug_on()
        return _wrap(ok, _nice_output(out, "🔌 Enchufe encendido"), out)

    elif action == "plug_off":
        ok, out = _run_home_command_with_retry("plug_off")
        if ok:
            device_state.set_plug_off()
        return _wrap(ok, _nice_output(out, "🔌 Enchufe apagado"), out)

    elif action == "plug_status":
        ok, out = _run_home_command_with_retry("plug_status")
        return _wrap(ok, _nice_output(out, "📊 Consultando enchufe..."), out)

    # --- Escenas ---
    elif action == "scene":
        scene = params.get("scene", "")
        
        # Actualizar presencia con escenas de llegada/salida
        if scene == "all_on":
            from model_router.smart_advisor import PresenceDetector
            PresenceDetector.set_home(True)
        elif scene == "all_off":
            from model_router.smart_advisor import PresenceDetector
            PresenceDetector.set_home(False)
        
        if scene in SCENE_MAP:
            scene_config = SCENE_MAP[scene]
            all_ok = True
            had_recovery = False
            for ha_action, ha_args in scene_config["home_actions"]:
                ok, out = _run_home_command_with_retry(ha_action, ha_args)
                msg = _nice_output(out, ha_action)
                if ok and out.startswith("[RECUPERADO"):
                    had_recovery = True
                    end = out.find("] ")
                    if end > 0:
                        msg = f"🔧 {out[:end+1]} → {msg}"
                messages.append(msg)
                if not ok:
                    all_ok = False
            summary = " | ".join(messages)
            if had_recovery:
                summary = "🔧 [Auto-recuperado] " + summary
            return all_ok, summary or scene_config["description"]
        return False, f"⚠️ Escena '{scene}' desconocida"

    elif action == "query":
        query_type = params.get("type", "status")
        if query_type == "temperature":
            # 1. Leer del daemon de sensores (siempre fresco, 0ms)
            daemon_reading = _read_daemon_cache()
            if daemon_reading:
                from model_router.comfort import ComfortAdvisor
                ts = daemon_reading.get("timestamp", "")
                return True, ComfortAdvisor.format_simple(
                    daemon_reading["temperature_c"],
                    daemon_reading["humidity_pct"],
                    timestamp=ts,
                )
            
            # 2. Fallback: RAM de esta sesión
            state = device_state.get_state()
            if state["temperature"] is not None:
                from model_router.comfort import ComfortAdvisor
                return True, ComfortAdvisor.format_simple(
                    state["temperature"],
                    state["humidity"],
                )
            
            # 3. Último recurso: BLE scan
            else:
                ok, out = _run_home_command_with_retry("scan", timeout=25)
                if ok:
                    _update_state_from_scan(out)
                return _wrap(ok, _nice_output(out, "📡 Escaneando sensores..."), out)

        elif query_type == "comfort":
            # Consulta de confort completa con recomendaciones
            daemon_reading = _read_daemon_cache()
            if daemon_reading:
                from model_router.comfort import ComfortAdvisor
                return True, ComfortAdvisor.format_full(
                    daemon_reading["temperature_c"],
                    daemon_reading["humidity_pct"],
                    timestamp=daemon_reading.get("timestamp", ""),
                )
            state = device_state.get_state()
            if state["temperature"] is not None:
                from model_router.comfort import ComfortAdvisor
                return True, ComfortAdvisor.format_full(
                    state["temperature"],
                    state["humidity"],
                )
            return False, "⚠️ No hay datos del sensor. Prueba 'temperatura' primero."

        elif query_type == "outdoor":
            # Temperatura exterior (Córdoba, Fátima) — usa caché, no bloquea
            import json, os, time
            cache_path = "/tmp/outdoor_weather.json"
            outdoor = None
            if os.path.exists(cache_path):
                try:
                    with open(cache_path) as f:
                        outdoor = json.load(f)
                except Exception:
                    pass
            # Si no hay caché, intentar fetch rápido (timeout corto)
            if not outdoor:
                try:
                    from model_router.smart_advisor import WeatherClient
                    outdoor = WeatherClient.get_current()
                except Exception:
                    pass
            if outdoor:
                comfort = None
                if outdoor["temperature_c"] >= 30:
                    zone_emoji = "🟣" if outdoor["temperature_c"] >= 34 else "🔴" if outdoor["temperature_c"] >= 31 else "🟠"
                elif outdoor["temperature_c"] >= 26:
                    zone_emoji = "🟡"
                elif outdoor["temperature_c"] >= 23:
                    zone_emoji = "🟢"
                else:
                    zone_emoji = "🟢"
                return True, (
                    f"🌍 **Exterior** (Córdoba, Fátima)\n"
                    f"{zone_emoji} {outdoor['temperature_c']:.0f}°C | 💧 {outdoor['humidity_pct']:.0f}% HR\n"
                    f"☀️ {outdoor['weather']} | 🌬️ {outdoor['wind_kmh']:.0f} km/h | UV {outdoor['uv_index']:.0f}\n"
                    f"🌡️ Sensación: {outdoor['feels_like_c']:.0f}°C"
                )
            return False, "⚠️ No se pudo obtener la temperatura exterior."

        elif query_type == "full":
            # Análisis completo: interior + exterior + ventana + recomendaciones
            from model_router.smart_advisor import SmartAdvisor
            return True, SmartAdvisor.format_response()

        elif query_type == "notifications":
            # Leer notificaciones pendientes del daemon
            notif_path = "/tmp/luxe_notifications.jsonl"
            if not os.path.exists(notif_path):
                return True, "📬 No hay notificaciones pendientes."
            try:
                with open(notif_path) as f:
                    lines = f.readlines()
                if not lines:
                    return True, "📬 No hay notificaciones pendientes."
                # Leer las últimas 5
                recent = []
                for line in lines[-5:]:
                    n = json.loads(line.strip())
                    ts = n.get("timestamp", "")[:16].replace("T", " ")
                    if n.get("type") == "action":
                        emoji = "⚡"
                        detail = " | ".join(n.get("executed", []))
                    else:
                        emoji = "❓"
                        detail = " | ".join(n.get("notifications", []))[:120]
                    zone = n.get("comfort", {}).get("emoji", "")
                    recent.append(f"{emoji} [{ts}] {zone} {detail}")
                return True, "📬 **Notificaciones**\n" + "\n".join(recent)
            except Exception as e:
                return False, f"⚠️ Error leyendo notificaciones: {e}"

        elif query_type == "status":
            return True, device_state.get_summary()

        elif query_type == "plug_status":
            state = device_state.get_state()
            status = "🔌 Enchufe encendido" if state["plug"]["on"] else "🔌 Enchufe apagado"
            return True, status

        return False, f"⚠️ Consulta '{query_type}' no soportada"

    # --- Comando batch (múltiples acciones) ---
    elif action == "batch":
        commands = params.get("commands", [])
        if not commands:
            return False, "⚠️ Batch vacío"
        all_ok = True
        for cmd in commands:
            ok, out = execute_json_action(cmd)
            messages.append(out)
            if not ok:
                all_ok = False
        return all_ok, " | ".join(messages) + " ✅"

    return False, f"⚠️ Acción desconocida: {action}"


def execute_zero_inference(pattern_match: tuple) -> tuple[bool, str]:
    """Ejecuta un comando de cero-inferencia.
    
    Args:
        pattern_match: (action_type, args) desde ZERO_INFERENCE_COMMANDS
                      o (action_type, [arg1, ...]) desde regex patterns
    
    Returns:
        (success, mensaje)
    """
    action_type = pattern_match[0] if isinstance(pattern_match, tuple) else None
    args = pattern_match[1] if isinstance(pattern_match, tuple) and len(pattern_match) > 1 else []

    if not action_type:
        return False, "⚠️ Patrón no reconocido"

    # Caso especial: fan_speed con args
    if action_type == "fan_speed" and args:
        speed = int(args[0])
        if 1 <= speed <= 5:
            return execute_json_action({
                "action": "fan_speed",
                "params": {"speed": speed}
            })
        return False, f"⚠️ Velocidad {speed} no válida (1-5)"

    # Caso especial: fan_adjust
    if action_type == "fan_adjust" or action_type == "fan_adjust_extreme":
        if args and args[0]:
            return execute_json_action({
                "action": "fan_speed",
                "params": {"speed": int(args[0])}
            })
        return execute_json_action({"action": "fan_speed", "params": {"speed": 3}})

    # Caso especial: temp_reaction
    if action_type == "temp_reaction":
        if args and args[0] == "frío":
            return execute_json_action({"action": "fan_off"})
        return execute_json_action({"action": "fan_speed", "params": {"speed": 3}})

    # Mapear tipos de zero-inference a acciones
    mapping = {
        "light_on": ("light_on", []),
        "light_off": ("light_off", []),
        "fan_on": ("fan_on", []),
        "fan_off": ("fan_off", []),
        "plug_on": ("plug_on", []),
        "plug_off": ("plug_off", []),
        "scene_night": ("scene", {"scene": "night"}),
        "scene_all_off": ("scene", {"scene": "all_off"}),
        "scene_all_on": ("scene", {"scene": "all_on"}),
        "scene_relax": ("scene", {"scene": "relax"}),
        "scene_cine": ("scene", {"scene": "cine"}),
        "scene_lectura": ("scene", {"scene": "lectura"}),
        "scene_estudio": ("scene", {"scene": "estudio"}),
        "scene_fiesta": ("scene", {"scene": "fiesta"}),
        "query_temp": ("query", {"type": "temperature"}),
        "query_status": ("query", {"type": "status"}),
        "query_plug": ("query", {"type": "plug_status"}),
        "query_comfort": ("query", {"type": "comfort"}),
        "query_notif": ("query", {"type": "notifications"}),
        "query_full": ("query", {"type": "full"}),
        "query_outdoor": ("query", {"type": "outdoor"}),
    }

    if action_type in mapping:
        mapped = mapping[action_type]
        if action_type.startswith("scene_") or action_type.startswith("query_"):
            return execute_json_action({"action": mapped[0], "params": mapped[1]})
        else:
            return execute_json_action({"action": mapped[0]})

    return False, f"⚠️ Zero-inference: {action_type} no mapeado"


# ============================================================================
# DETECCIÓN DE PATRONES (zero-inference tier + regex)
# ============================================================================

def detect_zero_inference(message: str) -> Optional[tuple]:
    """Intenta detectar un comando directo sin usar modelos.
    
    Returns:
        (action_type, args) para ejecutar con execute_zero_inference, o None
    """
    # Normalizar: minúsculas + quitar puntuación + espacios
    clean = re.sub(r'[,;:!¡¿?._\-]', '', message.lower())
    normalized = re.sub(r'\s+', ' ', clean).strip()

    # 1. Exact match contra ZERO_INFERENCE_COMMANDS
    if normalized in ZERO_INFERENCE_COMMANDS:
        return ZERO_INFERENCE_COMMANDS[normalized]

    # 2. Patrones regex para velocidad (ANTES del substring match)
    #    IMPORTANTE: los regex son más específicos y deben tener prioridad
    #    Ej: "ventilador 3" debe ser fan_speed 3, NO fan_on por substring
    for regex, action_type in SPEED_PATTERNS:
        m = regex.search(normalized)
        if m:
            if action_type == "fan_speed":
                speed = int(m.group(1))
                if speed == 0:
                    return ("fan_off", [])
                if 1 <= speed <= 5:
                    return ("fan_speed", [str(speed)])
                return None
            elif action_type == "fan_off":
                return ("fan_off", [])
            elif action_type == "fan_adjust":
                # "sube" → speed up, "baja" → slow down
                word = m.group(0)
                if any(w in word for w in ["sube", "aumenta", "más"]):
                    return ("fan_speed", ["3"])  # default medium-high
                else:
                    return ("fan_speed", ["1"])  # default low
            elif action_type == "fan_adjust_extreme":
                word = m.group(0)
                # Palabras que indican velocidad MÁXIMA
                if any(w in word for w in ["máximo", "rápido", "alta", "fuerte", "caña", "marcha", "más fuerte", "más rápido", "dale"]):
                    return ("fan_speed", ["5"])
                # Palabras que indican velocidad MÍNIMA
                else:
                    return ("fan_speed", ["1"])
            elif action_type == "temp_reaction":
                feeling = m.group(1)
                if feeling == "calor":
                    return ("fan_speed", ["3"])
                else:  # frío
                    return ("fan_off", [])

    # 3. Substring match (comandos con palabras extras, e.g. "por favor")
    #    Solo para comandos que sean claramente directos
    #    Buscamos frases clave como "enciende la luz" dentro del texto
    
    # Pre-filtro: si el mensaje habla de exterior, solo patrones outdoor
    outdoor_keywords = ["fuera", "exterior", "calle", "externo", "externa", "afuera"]
    is_outdoor_query = any(kw in normalized for kw in outdoor_keywords)
    
    best_match = None
    best_len = 0
    for pattern, action in ZERO_INFERENCE_COMMANDS.items():
        if len(pattern) >= 4 and pattern in normalized:
            # Si es consulta outdoor, ignorar patrones indoor (temp interior, etc.)
            if is_outdoor_query and "outdoor" not in str(action):
                continue
            if len(pattern) > best_len:
                best_match = action
                best_len = len(pattern)
    if best_match:
        return best_match

    return None


# === LEGACY (para compatibilidad) ===

# Mantener DEVICE_ACTIONS legacy por si algún otro módulo lo usa
DEVICE_ACTIONS = [
    {
        "keywords": ["apaga", "apagar", "off", "cena", "dormir", "noche"],
        "targets": ["luz", "enchufe", "plug", "lámpara"],
        "description": "Apagar smart plug",
        "command": ["python3", "-c", f"import sys; sys.path.insert(0, '{PROJECT_ROOT}/server'); from integrations.tuya_devices import TuyaSmartPlug; plug = TuyaSmartPlug(); plug.set_state(False); print('💡 Smart Plug APAGADO')"],
    },
    {
        "keywords": ["enciende", "encender", "prende", "on", "activa"],
        "targets": ["luz", "enchufe", "plug", "lámpara"],
        "description": "Encender smart plug",
        "command": ["python3", "-c", f"import sys; sys.path.insert(0, '{PROJECT_ROOT}/server'); from integrations.tuya_devices import TuyaSmartPlug; plug = TuyaSmartPlug(); plug.set_state(True); print('💡 Smart Plug ENCENDIDO')"],
    },
]


def find_action(message: str, intent: str = "") -> dict | None:
    """Legacy: buscar acción por keywords."""
    text_lower = message.lower()
    best_match = None
    best_score = 0
    for action in DEVICE_ACTIONS:
        kw_match = any(kw in text_lower for kw in action["keywords"])
        tgt_match = any(tg in text_lower for tg in action["targets"])
        if kw_match and tgt_match:
            score = (
                sum(1 for kw in action["keywords"] if kw in text_lower) +
                sum(1 for tg in action["targets"] if tg in text_lower)
            )
            if score > best_score:
                best_score = score
                best_match = action
    return best_match


def execute_action(action: dict) -> tuple[bool, str]:
    """Legacy: ejecutar acción de DEVICE_ACTIONS."""
    if action.get("requires_tty") and not os.access("/dev/ttyUSB0", os.RDWR):
        return False, "⚠️ ESP32 no accesible (/dev/ttyUSB0 sin permisos)"
    try:
        result = subprocess.run(
            action["command"],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PYTHONPATH": f"{PROJECT_ROOT}/server"},
        )
        if result.returncode == 0:
            return True, result.stdout.strip() or result.stderr.strip()
        else:
            return False, result.stderr.strip() or result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "⏰ Timeout ejecutando comando"
    except Exception as e:
        return False, str(e)


# ============================================================================
# SISTEMA DE AUTO-RECUPERACIÓN (Circuit Breaker + Health Checks)
# ============================================================================

class CircuitBreakerState:
    """Estados del circuit breaker."""
    CLOSED = "CLOSED"       # Funcionando normalmente
    OPEN = "OPEN"           # Falla continua → cortocircuito
    HALF_OPEN = "HALF_OPEN" # Probando si ya se recuperó


class CircuitBreaker:
    """Circuit breaker por subsistema.
    
    Evita llamar repetidamente a subsistemas caídos.
    Después de N fallos seguidos, abre el circuito y no vuelve a intentar
    hasta pasado el cooldown. Entonces prueba con HALF_OPEN.
    """

    FAILURE_THRESHOLD = 3       # Fallos consecutivos antes de abrir
    COOLDOWN_SECONDS = 30       # Tiempo de espera antes de reintentar
    HALF_OPEN_SUCCESS_LIMIT = 2 # Éxitos consecutivos para cerrar

    def __init__(self, name: str, logger):
        self.name = name
        self.logger = logger
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = 0.0
        self._lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        """Ejecuta una función con protección de circuit breaker.
        
        Returns (result, success_bool) o lanza CircuitBreakerOpenError.
        """
        with self._lock:
            now = time.time()
            if self.state == CircuitBreakerState.OPEN:
                if now - self.last_failure_time > self.COOLDOWN_SECONDS:
                    self.logger.info(f"🔁 [{self.name}] Circuito HALF_OPEN — probando...")
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.success_count = 0
                    self.last_state_change = now
                else:
                    remaining = int(self.COOLDOWN_SECONDS - (now - self.last_failure_time))
                    raise CircuitBreakerOpenError(
                        f"[{self.name}] circuito abierto ({remaining}s restantes)"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result, True
        except Exception as e:
            self._on_failure()
            return e, False

    def _on_success(self):
        with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.HALF_OPEN_SUCCESS_LIMIT:
                    self.logger.info(f"✅ [{self.name}] Recuperado — circuito CERRADO")
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change = time.time()
            else:
                # CLOSED: resetear contador de fallos
                self.failure_count = 0

    def _on_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitBreakerState.HALF_OPEN or \
               (self.state == CircuitBreakerState.CLOSED and
                self.failure_count >= self.FAILURE_THRESHOLD):
                old_state = self.state
                self.state = CircuitBreakerState.OPEN
                self.last_state_change = time.time()
                self.logger.warning(
                    f"🔴 [{self.name}] Circuito ABIERTO "
                    f"({self.failure_count} fallos consecutivos)"
                )

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "failures": self.failure_count,
                "successes": self.success_count,
                "last_failure_ago": round(time.time() - self.last_failure_time, 1)
                    if self.last_failure_time else None,
            }


class CircuitBreakerOpenError(Exception):
    """El circuit breaker está abierto — no se intenta la llamada."""
    pass


# ============================================================================
# ERROR TRACKER — Circuit breakers para todos los subsistemas
# ============================================================================

class ErrorTracker:
    """Gestiona circuit breakers para cada subsistema crítico."""

    SUBSYSTEM_OLLAMA_FAST = "ollama_fast"        # 1.5B API
    SUBSYSTEM_OLLAMA_REASONING = "ollama_reasoning" # 7B API
    SUBSYSTEM_ESP32 = "esp32"                    # /dev/ttyUSB0 serial
    SUBSYSTEM_TUYA = "tuya"                      # Enchufe vía LAN
    SUBSYSTEM_HOME_SH = "home_sh"                # Script wrapper

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, name: str) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, logger)
            return self._breakers[name]

    def call(self, subsystem: str, func, *args, **kwargs):
        """Ejecuta función con circuit breaker. Reintenta automáticamente.
        
        Returns:
            On success: (resultado, True)
            On circuit open: levanta CircuitBreakerOpenError
            On failure tras retry: (excepción, False)
        """
        cb = self._get_or_create(subsystem)
        return cb.call(func, *args, **kwargs)

    def status(self) -> dict:
        with self._lock:
            return {
                name: cb.status()
                for name, cb in self._breakers.items()
            }


# Singleton
error_tracker = ErrorTracker()


# ============================================================================
# HOME.SH CON REINTENTO AUTOMÁTICO
# ============================================================================

_retry_logger = logging.getLogger("model_router.retry")

# Acciones que dependen del ESP32 (necesitan /dev/ttyUSB0)
_ESP32_ACTIONS = {"fan_on", "fan_off", "fan_speed"}
_ESP32_BOOT_KEYWORDS = ["ets Jul", "rst:0x", "configsip:", "clk_drv:", "mode:DIO", "mode:DOUT", "mode:QIO", "mode:QOUT", "load:0x3fff", "entry 0x", "SPIWP:0x", "SW_CPU_RESET", "POWERON_RESET", "SPI_FAST_FLASH_BOOT"]

def _check_esp32_available() -> bool:
    """Health check proactivo: ¿está el ESP32 conectado?"""
    return os.path.exists("/dev/ttyUSB0")


def _reset_esp32_usb():
    """Intenta reiniciar el dispositivo USB del ESP32 (unbind/rebind).
    
    Esto resuelve el error "device disconnected or multiple access on port"
    que ocurre cuando el ESP32 se queda en estado inconsistente.
    """
    import subprocess
    try:
        # Buscar el dispositivo CH340/CP210x (típicos de ESP32)
        result = subprocess.run(
            ["find", "/sys/bus/usb/devices/", "-name", "idVendor"],
            capture_output=True, text=True, timeout=3,
        )
        for vendor_file in result.stdout.strip().split("\n"):
            if not vendor_file:
                continue
            try:
                vid = open(vendor_file).read().strip()
                # CH340: 1a86, CP210x: 10c4
                if vid in ("1a86", "10c4"):
                    dev_dir = os.path.dirname(vendor_file)
                    # Intentar unbind + bind
                    subprocess.run(
                        ["sudo", "tee", f"/sys/bus/usb/drivers/usb/unbind"],
                        input=dev_dir, capture_output=True, text=True, timeout=3,
                    )
                    time.sleep(1)
                    subprocess.run(
                        ["sudo", "tee", f"/sys/bus/usb/drivers/usb/bind"],
                        input=dev_dir, capture_output=True, text=True, timeout=3,
                    )
                    time.sleep(2)
                    _retry_logger.info(f"✅ USB reset completado para {dev_dir}")
                    return
            except (OSError, IOError):
                continue
    except Exception as e:
        _retry_logger.warning(f"No se pudo resetear USB: {e}")

# Estadísticas globales de reintentos — expuestas en /status
RETRY_STATS = {
    "total_attempts": 0,       # Intentos totales (incluye primer intento)
    "total_retries": 0,        # Reintentos exitosos (2º, 3º intento)
    "total_failures": 0,       # Fallos tras agotar reintentos
    "by_action": {},           # {"fan_speed": {"attempts": N, "retries": N, "failures": N}}
}
_retry_stats_lock = threading.Lock()


def get_retry_stats() -> dict:
    """Snapshot thread-safe de estadísticas de reintentos."""
    with _retry_stats_lock:
        import copy
        return copy.deepcopy(RETRY_STATS)


def _run_home_command_with_retry(
    action: str,
    args: list[str] = None,
    max_retries: int = 2,
    timeout: int = 15,
) -> tuple[bool, str]:
    """Ejecuta home.sh con auto-retry y backoff exponencial.
    
    Estrategia:
    - Error de timeout o ESP32 ocupado → reintenta (hasta max_retries)
    - Error de validación (velocidad inválida) → falla inmediato
    - Error de permiso (no dialout) → NO reintenta
    
    Backoff: 1s, 3s, 7s (exponencial con jitter)
    """
    NO_RETRY_KEYWORDS = ["no válida", "no accesible", "no encontrado", "Permission denied"]
    
    # Errores de puerto serie que SÍ son reintentables (transitorios)
    SERIAL_RETRY_KEYWORDS = [
        "device disconnected",       # ESP32 se reinició a mitad de operación
        "multiple access on port",    # Otro proceso bloqueó el puerto
        "returned no data",           # ESP32 no respondió a tiempo
        "SerialException",
    ]

    # --- Health check proactivo para ESP32 ---
    if action in _ESP32_ACTIONS and not _check_esp32_available():
        _retry_logger.warning(f"⛔ ESP32 no disponible — '{action}' cancelado")
        return False, "⚠️ ESP32 no conectado (/dev/ttyUSB0 no encontrado). ¿Está encendido el puente?"

    last_error = ""
    retried = False
    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Si el error anterior fue de puerto serie, intentar reset USB
            if any(kw in last_error for kw in SERIAL_RETRY_KEYWORDS):
                _retry_logger.info(f"🔌 Detectado error serie — intentando reset USB...")
                _reset_esp32_usb()
            # Backoff exponencial con jitter
            import random
            delay = min(2 ** attempt + random.uniform(0, 1), 8)
            _retry_logger.info(
                f"🔄 Reintento {attempt}/{max_retries} para '{action}' "
                f"en {delay:.1f}s..."
            )
            time.sleep(delay)
            retried = True

        ok, out = _run_home_command(action, args, timeout=timeout)

        if ok:
            # Registrar estadística de éxito
            with _retry_stats_lock:
                RETRY_STATS["total_attempts"] += attempt + 1
                if retried:
                    RETRY_STATS["total_retries"] += 1
                by_a = RETRY_STATS["by_action"].setdefault(action, {"attempts": 0, "retries": 0, "failures": 0})
                by_a["attempts"] += attempt + 1
                if retried:
                    by_a["retries"] += 1
            if retried:
                _retry_logger.info(f"✅ Recuperado '{action}' en intento {attempt + 1}")
                return True, out  # Ya no añadimos prefijo [RECUPERADO] aquí
            return True, out

        last_error = out

        # No reintentar errores de validación/permisos
        if any(kw in out for kw in NO_RETRY_KEYWORDS):
            _retry_logger.warning(f"⛔ Error permanente en '{action}': {out[:60]}")
            break

    # Registrar fallo final
    with _retry_stats_lock:
        RETRY_STATS["total_attempts"] += max_retries + 1
        RETRY_STATS["total_failures"] += 1
        by_a = RETRY_STATS["by_action"].setdefault(action, {"attempts": 0, "retries": 0, "failures": 0})
        by_a["attempts"] += max_retries + 1
        by_a["failures"] += 1
    _retry_logger.warning(
        f"⚠️ '{action}' falló tras {max_retries + 1} intentos: {last_error[:80]}"
    )
    return False, last_error


# ============================================================================
# SELF-HEAL MANAGER — Monitor de salud en background
# ============================================================================

class SelfHealManager:
    """Monitor de salud que corre en background.
    
    Cada N segundos:
    1. Verifica que Ollama responde
    2. Verifica que el modelo rápido está cargado
    3. Verifica que el ESP32 está conectado
    4. Intenta recargar modelos caídos
    
    Todo automático, sin intervención del usuario.
    """

    CHECK_INTERVAL = 30  # segundos entre chequeos

    def __init__(self):
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="self-heal",
        )
        self._running = True
        self._ollama_down = False
        self._esp32_down = False
        self._last_ollama_ok = 0.0
        self._last_esp32_ok = 0.0

    def start(self):
        self._thread.start()
        logger.info("🔧 Self-heal manager iniciado (check cada 30s)")

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(self.CHECK_INTERVAL)
            self._check_ollama()
            self._check_esp32()

    def _check_ollama(self):
        """Verifica que Ollama responde y el modelo rápido está cargado."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/ps",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                loaded = [m["name"] for m in data.get("models", [])]

                # Verificar modelo rápido
                fast_model = MODELS["fast"]["name"]
                if fast_model not in loaded:
                    logger.info(f"🔁 Recargando {fast_model}...")
                    self._load_model_with_retry(fast_model)
                else:
                    if self._ollama_down:
                        logger.info(f"✅ Ollama recuperado — {fast_model} disponible")
                    self._ollama_down = False
                    self._last_ollama_ok = time.time()
        except Exception as e:
            if not self._ollama_down:
                logger.warning(f"⚠️ Ollama no responde: {e}")
                self._ollama_down = True

    def _check_esp32(self):
        """Verifica que /dev/ttyUSB0 existe y es accesible."""
        exists = os.path.exists("/dev/ttyUSB0")
        if exists:
            if self._esp32_down:
                logger.info("✅ ESP32 reconectado (/dev/ttyUSB0 disponible)")
            self._esp32_down = False
            self._last_esp32_ok = time.time()
        else:
            if not self._esp32_down:
                logger.warning("⚠️ ESP32 desconectado (/dev/ttyUSB0 no existe)")
                self._esp32_down = True

    def _load_model_with_retry(self, model_name: str, max_retries: int = 3):
        """Carga un modelo en Ollama con reintentos."""
        import urllib.request
        for attempt in range(max_retries):
            try:
                payload = json.dumps({
                    "model": model_name,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": -1,
                    "options": {"num_predict": 1},
                }).encode()
                req = urllib.request.Request(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    logger.info(f"✅ {model_name} cargado")
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 5 * (attempt + 1)
                    logger.warning(
                        f"⚠️ No se pudo cargar {model_name} "
                        f"(intento {attempt + 1}/{max_retries}): {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"❌ No se pudo cargar {model_name} tras {max_retries} intentos")

    def report(self) -> dict:
        """Estado actual de salud."""
        return {
            "ollama": {
                "status": "healthy" if not self._ollama_down else "down",
                "last_ok": round(time.time() - self._last_ollama_ok, 1)
                    if self._last_ollama_ok else None,
            },
            "esp32": {
                "status": "connected" if not self._esp32_down else "disconnected",
                "port": "/dev/ttyUSB0" if os.path.exists("/dev/ttyUSB0") else None,
                "last_ok": round(time.time() - self._last_esp32_ok, 1)
                    if self._last_esp32_ok else None,
            },
            "circuit_breakers": {
                name: cb.state
                for name, cb in error_tracker._breakers.items()
            },
        }


# Singleton — se inicia automáticamente al importar
self_heal = SelfHealManager()
self_heal.start()
