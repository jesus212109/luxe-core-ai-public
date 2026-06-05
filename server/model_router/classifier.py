"""Clasificador de intenciones v2 — Embeddings precomputados + multi-intent.

Estrategia:
1. Precomputar TODOS los embeddings de intenciones al arrancar (thread bg)
2. Zero-inference tier (config.detect_zero_inference) — sin modelo
3. Clasificación rápida con coseno similarity contra cache de embeddings
4. Multi-intent detection para comandos compuestos
"""

import json
import logging
import re
import threading
import time
from typing import Optional

import numpy as np

from . import config

logger = logging.getLogger("model_router.classifier")

# ============================================================================
# CACHE DE EMBEDDINGS PRECOMPUTADOS
# ============================================================================

_PRECOMPUTED_EMBEDDINGS: dict[str, list[float]] = {}
_PRECOMPUTE_READY = threading.Event()

# Umbral de similitud coseno
SIMILARITY_THRESHOLD = 0.55  # Ligeramente más bajo para capturar variaciones naturales


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    if denom == 0:
        return 0.0
    return float(np.dot(a_np, b_np) / denom)


def _get_embedding(text: str, timeout: int = 5) -> Optional[list[float]]:
    """Obtiene embedding de bge-m3 vía Ollama."""
    payload = json.dumps({
        "model": config.MODELS["encoder"]["name"],
        "prompt": text,
    }).encode()
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(
            f"{config.OLLAMA_BASE_URL}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("embedding")
    except Exception as e:
        logger.warning(f"Embedding falló: {e}")
        return None


def _precompute_all_embeddings():
    """Precomputa embeddings para todos los intents conocidos en background."""
    all_keywords = {}

    # Recoger primer keyword de cada intent como representante
    for intent, keywords in config.FAST_INTENTS.items():
        if keywords:
            all_keywords[f"fast:{intent}"] = keywords[0]

    for intent, keywords in config.REASONING_INTENTS.items():
        if keywords:
            all_keywords[f"reasoning:{intent}"] = keywords[0]

    # También precomputar las escenas y consultas de zero-inference
    all_keywords["scene:night"] = "modo noche a dormir cama"
    all_keywords["scene:all_off"] = "apaga todo salir casa"
    all_keywords["scene:all_on"] = "enciende todo llegar casa"
    all_keywords["scene:relax"] = "modo relax descanso"
    all_keywords["scene:cine"] = "modo cine película"
    all_keywords["query:temperature"] = "temperatura ambiente sensor"
    all_keywords["query:status"] = "estado casa cómo está"

    total = len(all_keywords)
    loaded = 0

    for name, keyword in all_keywords.items():
        emb = _get_embedding(keyword, timeout=3)
        if emb:
            _PRECOMPUTED_EMBEDDINGS[name] = emb
            loaded += 1
        time.sleep(0.03)  # Rate limit suave

    logger.info(f"Embeddings precomputados: {loaded}/{total}")
    _PRECOMPUTE_READY.set()


# Iniciar precomputación en background
_thread = threading.Thread(target=_precompute_all_embeddings, daemon=True,
                           name="embed-precompute")
_thread.start()

# ============================================================================
# CLASIFICACIÓN HÍBRIDA
# ============================================================================

def _check_keywords(text: str, intent_map: dict) -> Optional[str]:
    """Busca keywords en el texto. Devuelve la primera intención que matchea."""
    text_lower = text.lower()
    best_intent = None
    best_length = 0
    for intent, keywords in intent_map.items():
        for kw in keywords:
            if kw in text_lower:
                # Preferir el match más largo (más específico)
                if len(kw) > best_length:
                    best_length = len(kw)
                    best_intent = intent
    return best_intent


def _classify_by_embedding(message: str) -> Optional[dict]:
    """Clasifica usando embeddings precomputados.
    
    Returns dict con intent/confidence/model o None si no hay suficientes datos.
    """
    if not _PRECOMPUTE_READY.is_set() or not _PRECOMPUTED_EMBEDDINGS:
        return None

    msg_emb = _get_embedding(message, timeout=3)
    if not msg_emb:
        return None

    best_name = None
    best_sim = 0.0

    for name, intent_emb in _PRECOMPUTED_EMBEDDINGS.items():
        sim = _cosine_similarity(msg_emb, intent_emb)
        if sim > best_sim:
            best_sim = sim
            best_name = name

    if best_name and best_sim >= SIMILARITY_THRESHOLD:
        prefix, intent_name = best_name.split(":", 1)
        model = "reasoning" if prefix == "reasoning" else "fast"
        return {
            "intent": intent_name,
            "model": model,
            "confidence": round(best_sim, 3),
            "method": "embedding",
        }

    return None


def _detect_multi_intent(message: str) -> Optional[list[str]]:
    """Detecta si el mensaje contiene múltiples comandos.
    
    Busca conectores como "y", ",", "además", "+" entre comandos.
    
    Returns:
        Lista de sub-comandos o None si es monocomando.
    """
    separators = [
        r'\by\b', r'\by\s*además\b', r'\bademás\b',
        r'\bdespués\b', r'\bluego\b', r'\btambién\b',
        r',', r'\.\s*\.', r'\b\+',
    ]

    # Normalizar: asegurar espacios alrededor de comas
    text = message.strip()
    text = re.sub(r'\s*,\s*', ' , ', text)
    text = re.sub(r'\s+', ' ', text)

    # Probar separadores
    for sep_pattern in separators:
        parts = re.split(sep_pattern, text, maxsplit=1)
        if len(parts) >= 2:
            # Verificar que ambas partes parecen comandos
            p1, p2 = parts[0].strip(), parts[-1].strip()
            if len(p1) > 3 and len(p2) > 3 and p1 != p2:
                # Limpiar comas residuales
                p1 = p1.replace(' , ', ' ').strip()
                p2 = p2.replace(' , ', ' ').strip()
                return [p1, p2]

    return None


def classify(message: str, use_embeddings: bool = True) -> dict:
    """Clasifica el mensaje y determina qué modelo usar.
    
    Pipeline completo:
    1. Zero-inference (sin modelo) — config.detect_zero_inference
    2. Keyword matching rápido
    3. Embedding similarity (precomputado)
    4. Fallback
    
    Returns:
        dict con:
          - intent: str | None
          - model: "fast" | "reasoning" | "auto"
          - confidence: float (0-1)
          - method: "keyword" | "embedding" | "fallback"
          - zero_inference: bool (si se resolvió sin modelo)
          - multi_intent: list[str] | None (sub-comandos)
    """
    result = {
        "intent": None,
        "model": "fast",
        "confidence": 0.5,
        "method": "fallback",
        "zero_inference": False,
        "multi_intent": None,
    }

    # --- Fase 0: Multi-intent detection ---
    multi = _detect_multi_intent(message)
    if multi:
        result["multi_intent"] = multi
        # Si tiene múltiples comandos, forzar fast (1.5B hará batch)
        result["intent"] = "multi_command"
        result["model"] = "fast"
        result["confidence"] = 0.8
        result["method"] = "multi_intent"
        return result

    # --- Fase 1: Keyword matching (rápido) ---
    fast_intent = _check_keywords(message, config.FAST_INTENTS)
    reasoning_intent = _check_keywords(message, config.REASONING_INTENTS)

    if reasoning_intent:
        result["intent"] = reasoning_intent
        result["model"] = "reasoning"
        result["confidence"] = 0.7
        result["method"] = "keyword"
        return result

    if fast_intent:
        result["intent"] = fast_intent
        result["model"] = "fast"
        result["confidence"] = 0.7
        result["method"] = "keyword"
        return result

    # --- Fase 2: Embedding similarity ---
    if use_embeddings:
        emb_result = _classify_by_embedding(message)
        if emb_result:
            result.update(emb_result)
            return result

    # --- Fallback ---
    result["intent"] = "unknown"
    result["confidence"] = 0.3
    result["method"] = "fallback"
    return result
