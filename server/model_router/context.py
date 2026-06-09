"""Gestor de contextos de sesión del Model Router.

Cada sesión mantiene:
- Historial de mensajes (role: user/assistant, content, model_used)
- Timestamps de última actividad
- Modelo activo actual
"""

import time
import threading
import logging
from typing import Optional

from . import config

logger = logging.getLogger("model_router.context")


class Session:
    """Una sesión de conversación."""

    def __init__(self, session_id: str):
        self.id = session_id
        self.messages: list[dict] = []
        self.active_model: Optional[str] = None  # "fast" | "reasoning"
        self.created_at = time.time()
        self.last_activity = time.time()

    def add_message(self, role: str, content: str, model_used: str = "fast"):
        """Añade un mensaje al historial."""
        self.messages.append({
            "role": role,
            "content": content,
            "model_used": model_used,
            "timestamp": time.time(),
        })
        self.last_activity = time.time()
        self._trim()

    def _trim(self):
        """Recorta el historial si excede el máximo."""
        if len(self.messages) > config.MAX_CONTEXT_MESSAGES * 2:
            # Elimina los pares más antiguos (user+assistant)
            excess = len(self.messages) - config.MAX_CONTEXT_MESSAGES * 2
            # Asegurar que eliminamos pares completos
            excess = (excess // 2) * 2
            self.messages = self.messages[excess:]

    def get_context(self, max_chars: int = 8000) -> str:
        """Construye el contexto para el prompt del modelo."""
        lines = []
        for msg in self.messages:
            label = "Usuario" if msg["role"] == "user" else "Asistente"
            lines.append(f"{label}: {msg['content']}")
        context = "\n".join(lines)
        if len(context) > max_chars:
            context = context[-max_chars:]
            context = "[...contexto anterior truncado...]\n" + context
        return context

    @property
    def age_seconds(self) -> float:
        return time.time() - self.last_activity

    @property
    def is_expired(self, max_idle: int = 600) -> bool:
        """Sesión expirada si ha estado inactiva más de max_idle segundos."""
        return self.age_seconds > max_idle


class ContextManager:
    """Gestiona múltiples sesiones concurrentes."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="ctx-cleanup",
        )
        self._cleanup_thread.start()

    def get_or_create(self, session_id: str) -> Session:
        """Obtiene una sesión existente o crea una nueva."""
        with self._lock:
            if session_id not in self._sessions:
                if len(self._sessions) >= config.MAX_SESSIONS:
                    # Eliminar la sesión más vieja
                    oldest = min(
                        self._sessions.values(),
                        key=lambda s: s.last_activity,
                    )
                    del self._sessions[oldest.id]
                    logger.info(f"Sesión {oldest.id} eliminada por límite")
                self._sessions[session_id] = Session(session_id)
            return self._sessions[session_id]

    def remove(self, session_id: str):
        """Elimina una sesión."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _cleanup_loop(self):
        """Limpia sesiones expiradas cada 60 segundos."""
        while True:
            time.sleep(60)
            with self._lock:
                expired = [
                    sid for sid, s in self._sessions.items()
                    if s.is_expired
                ]
                for sid in expired:
                    del self._sessions[sid]
                    logger.debug(f"Sesión {sid} limpiada por inactividad")
                if expired:
                    logger.info(f"Limpiadas {len(expired)} sesiones expiradas")


# Singleton global
context_manager = ContextManager()
