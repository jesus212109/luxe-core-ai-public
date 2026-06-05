# ADR-008: Migración del SDK Python CMDOP al Framework OpenClaw npm

**Fecha:** 2026-05-27
**Estado:** Implementado

## Contexto

El proyecto Luxe Core AI inició su fase de orquestación utilizando el SDK Python
de OpenClaw/CMDOP (`pip install openclaw`), que es un wrapper del SDK `cmdop`.
Este SDK requiere autenticación cloud para ciertas funcionalidades y despliega
una pila de dependencias Python de más de 30 GB que incluye paquetes como
`tenacity`, `pydantic`, `fastapi`, `uvicorn`, etc.

Paralelamente, existe un producto independiente también llamado OpenClaw pero
distribuido como paquete npm (`@openclaw/lobster`) instalable mediante
`curl openclaw.ai/install.sh`. Este producto es 100% local, 100% open source,
sin dependencias cloud, y proporciona de forma nativa:

- Canal Telegram
- Dashboard web
- Búsqueda web (Gemini API)
- Ejecución de herramientas externas (exec)
- Gestión de agentes y skills

## Decisión

Migrar todo el stack de orquestación desde el SDK Python CMDOP al framework
Node.js OpenClaw npm. El stack resultante es:

| Capa | Tecnología | Función |
|------|-----------|---------|
| Orquestador | Node.js 24 + OpenClaw npm | Gateway, agentes, canales de usuario |
| Drivers de dispositivo | Python 3.12 + tinytuya/bleak | Control físico de Tuya, BLE, FanLamp |
| Firmware | C++20 (ESP32) | Puente LIN bus HVAC |

## Consecuencias

### Positivas
- Reducción del tamaño del stack de ~30 GB (venv Python) a ~10 MB.
- Eliminación de dependencias cloud: el gateway es 100% local.
- Canales de usuario (Telegram, web) nativos, sin scripts Python auxiliares.
- El dashboard web es accesible desde la LAN sin SSH tunneling.

### Negativas
- El equipo de desarrollo debe tener Node.js 24 instalado (además de Python 3.12).
- Los scripts de control Python deben envolverse en tools invocables por exec.

### Archivos afectados
- **Eliminados:** `server/venv/`, `server/telegram_channel.py`,
  `server/gemini_search_tool.py`, `server/gemini_proxy_client.py`,
  `server/community_skill_loader.py`, `server/ephemeral_sandbox.py`,
  `server/config/`, `server/database/db_manager.py`, `server/agents/`,
  `server/skills/`, `scripts/setup_client.sh`, `scripts/start_client.sh`,
  `scripts/bootstrap_env.sh`, `environment.yml`, `firmware/esp32_sketches/`.
- **Creados:** `server/tools/` (wrappers CLI), `server/requirements.txt`.
- **Actualizados:** `AGENTS.md`, `README.md`, capítulos 5, 6, 8, 9 de la
  memoria, `references.bib`.
