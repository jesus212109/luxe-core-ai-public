# Public Release Notes — Luxe Core AI

Repositorio público del TFG *Ecosistema Avanzado de Edge AI para Domótica Local*
(Universidad de Córdoba, 2025/2026). Incluye la memoria completa en `docs/`
y el código fuente del sistema, funcional y desplegable con hardware propio.

## Archivos sanitizados

Las credenciales reales de los dispositivos y servicios se han sustituido
por variables de entorno. Los bytes del protocolo BLE del ventilador se han
reemplazado por la documentación de la estructura del protocolo.

| Archivo | Cambio |
|---|---|
| `server/integrations/tuya_devices.py` | Device ID + Local Key → `TUYA_DEVICE_ID`, `TUYA_LOCAL_KEY` |
| `server/tools/telegram_send_voice.py` | Bot token → `TELEGRAM_BOT_TOKEN` |
| `server/tools/voice_transcribe.py` | Bot token → `TELEGRAM_BOT_TOKEN` |
| `scripts/fanlamp_bt.py` | Arrays de bytes → documentación del protocolo |
| `firmware/esp32_fanlamp/src/main.ino` | Ídem |

## Puesta en marcha

1. Copia `.env.example` a `.env` y asigna tus propias credenciales
2. Sigue el manual de usuario (`docs/appendices/anejo_a_usuario.tex`)

## Sobre el desarrollo

Este repositorio es una versión pública del proyecto. El desarrollo continúa en
un repositorio privado con el historial completo y las integraciones de hardware.
Si quieres conocer el estado actual, colaborar o tienes alguna pregunta, puedes
abrir un issue en este repositorio.

## Licencia

Ver fichero `LICENSE`.
