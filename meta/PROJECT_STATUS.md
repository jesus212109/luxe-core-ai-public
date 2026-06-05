# Luxe Core AI — Estado del Proyecto (2026-05-30)

## Contexto Académico
- **Autor:** Jesús Fernández López (UCO, Ingeniería Informática)
- **Tutor:** Dr. Rafael Muñoz Salinas
- **TFG:** Ecosistema Avanzado de Edge AI para Domótica Local

## Infraestructura
- **Arquitectura:** 100% Local — Node.js 24 (OpenClaw npm) + Python 3.12 (drivers) + C++20 (ESP32 HVAC)
- **Servidor:** Torre Ryzen (Ubuntu 24.04 LTS, headless)
- **Gateway:** OpenClaw npm v2026.5.27, puerto 18789 (LAN 192.168.1.0/24)
- **Red:** Subred air-gapped `192.168.1.0/24` (router TP-Link sin WAN)
- **Ollama:** localhost:11434 (modelos: qwen3-coder, llama3.2, bge-m3)

## Módulos

| Módulo | Estado | Detalle |
|--------|--------|---------|
| Tuya Smart Plug | ✅ Completo | `server/integrations/tuya_devices.py` — `tinytuya` 3.5 |
| Xiaomi BLE sensor | ✅ Completo | `server/integrations/ble_sensors.py` — GATT `ebe0ccc1` vía ESP32 bridge serial (workaround limitación Realtek) |
| FanLamp F8808 | ✅ Completo | `scripts/fanlamp_control.py` — ESP32 bridge serial (antes bloqueado por Realtek BT). ESP32 ahora también lee sensor Xiaomi vía GATT |
| OpenClaw Orchestrator | ✅ Desplegado | Gateway Node.js, Telegram + web nativos, exec tools |
| ESP32 HVAC Bridge | ❌ Pendiente | `server/integrations/hvac_bridge.py` (stub). ESP32 ocupado con FanLamp + Xiaomi BLE (dual-purpose) |
| LaTeX Memoria | 🔶 Avanzado | Cap. 1–9 redactados, apéndices TODO, ADR-008 añadido |

## Próximos pasos (orden prioridad)
1. Desarrollar firmware ESP32 para HVAC LIN bus (esphome-fujitsu-halcyon, ESP32 ocupado con FanLamp+Xiaomi, requiere compartir roles o dispositivo adicional)
2. Redactar apéndices del TFG (manual de usuario, listado de código, pruebas)
3. DNS persistente: /etc/systemd/resolved.conf.d/dns.conf
