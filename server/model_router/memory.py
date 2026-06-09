"""Memoria conversacional semántica con bge-m3.

Permite que el router recuerde el contexto entre mensajes consecutivos
usando embeddings para encontrar referencias implícitas.

Ej: "y fuera?" → encuentra "qué temperatura hace en mi habitación?"
    → inyecta contexto: "el usuario preguntaba por temperatura interior,
       ahora quiere comparar con exterior"
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

from . import config

logger = logging.getLogger("model_router.memory")

OLLAMA_EMBED_URL = f"{config.OLLAMA_BASE_URL}/api/embed"
MEMORY_SIZE = 15  # últimos N mensajes recordados
SIMILARITY_THRESHOLD = 0.65  # coseno similitud mínimo para considerar relacionado


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed(text: str) -> Optional[list[float]]:
    """Genera embedding con bge-m3 vía Ollama."""
    try:
        body = json.dumps({
            "model": "bge-m3:latest",
            "input": text,
        }).encode()
        req = urllib.request.Request(
            OLLAMA_EMBED_URL,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
    except Exception as e:
        logger.debug(f"Embedding falló para memoria: {e}")
    return None


class ConversationMemory:
    """Memoria semántica de corto plazo usando bge-m3."""

    def __init__(self):
        self._entries: list[dict] = []  # [{text, embedding, timestamp}]

    def remember(self, text: str):
        """Almacena un mensaje en la memoria (sin embedding — lazy)."""
        self._entries.append({
            "text": text,
            "embedding": None,  # Se calcula bajo demanda en recall()
            "timestamp": time.time(),
        })
        if len(self._entries) > MEMORY_SIZE:
            self._entries = self._entries[-MEMORY_SIZE:]

    def recall(self, text: str) -> Optional[str]:
        """Busca el mensaje más relacionado semánticamente.

        Si la similitud supera el umbral, devuelve el texto del mensaje
        recuperado como contexto para la consulta actual.
        """
        if not self._entries or len(self._entries) < 2:
            return None

        current_embedding = _embed(text)
        if not current_embedding:
            return None

        best_sim = 0.0
        best_text = None

        for entry in self._entries[:-1]:  # excluir la propia consulta si ya se guardó
            # Lazy embedding: calcular si no existe
            if entry["embedding"] is None:
                entry["embedding"] = _embed(entry["text"])
                if entry["embedding"] is None:
                    continue
            sim = _cosine_similarity(current_embedding, entry["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_text = entry["text"]

        if best_sim > SIMILARITY_THRESHOLD and best_text:
            logger.info(
                f"🧠 Memoria: '{text[:40]}' → recuerda '{best_text[:40]}' "
                f"(sim={best_sim:.2f})"
            )
            return best_text

        return None


# Singleton global
conversation_memory = ConversationMemory()
