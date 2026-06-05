# Luxe Core AI

<div align="center">
  <img src="https://img.shields.io/badge/C%2B%2B-20-blue?style=for-the-badge&logo=c%2B%2B" alt="C++20">
  <img src="https://img.shields.io/badge/Python-3.12-yellow?style=for-the-badge&logo=python" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Node.js-24-green?style=for-the-badge&logo=nodedotjs" alt="Node.js 24">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
</div>

<br />

<div align="center">
  <strong>Ecosistema Avanzado de Edge AI para Domótica Local</strong>
  <br />
  <em>Trabajo de Fin de Grado (TFG) — Grado en Ingeniería Informática @ Universidad de Córdoba</em>
  <br />
  <em>Autor: Jesús Fernández López | Tutor: Dr. Rafael Muñoz Salinas</em>
</div>

---

## ¿Qué es Luxe Core AI?

Un ecosistema de domótica inteligente **100% local** que no depende de Internet ni de
la nube. Modelos de lenguaje pequeños (1.5B–7B parámetros) ejecutándose en Ollama
sobre un servidor doméstico Ryzen toman decisiones en tiempo real, sin que los datos
del hogar salgan de la red local.

### ¿Por qué?

- **Privacidad real:** los patrones de comportamiento del hogar no viajan a servidores
  de terceros
- **Sin dependencia cloud:** si Internet falla, todo sigue funcionando
- **Interoperabilidad forzada:** integramos dispositivos que no fueron diseñados para
  trabajar juntos (Tuya, Xiaomi BLE, FanLamp de AliExpress)
- **Coste mínimo:** el ventilador costó 35€, el sensor 4€, el enchufe 8€. La
  inteligencia la pone el software, no el hardware

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                 OpenClaw Gateway (Node.js 24)            │
│                 http://192.168.1.50:18789               │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐ │
│  │ Telegram │  │ Dashboard│  │   Model Router v2      │ │
│  │  (bot)   │  │  (web)   │  │   (Python, :18790)     │ │
│  └──────────┘  └──────────┘  │                         │ │
│                               │  Tier 0: 462 patrones   │ │
│  ┌──────────────────────────┐ │  Tier 1: 1.5B clasif.  │ │
│  │      Ollama (local)      │ │  Tier 2: 7B razonador  │ │
│  │  qwen2.5-coder:1.5b      │ └───────────────────────┘ │
│  │  qwen2.5-coder:7b-instr  │                           │
│  │  bge-m3 (embeddings)     │                           │
│  └──────────────────────────┘                           │
│                                                         │
│  exec ─── server/tools/home.sh ─── dispositivos         │
└─────────────────────────────────────────────────────────┘
         │                    │                │
         ▼                    ▼                ▼
┌─────────────┐  ┌─────────────────┐  ┌──────────────┐
│ Tuya Smart  │  │ ESP32 FanLamp   │  │ Xiaomi BLE   │
│ Plug (LAN)  │  │ Bridge (USB)    │  │ Sensor (GATT)│
│             │  │                 │  │              │
│ extractor   │  │ 11 comandos BLE │  │ temp/hum/bat │
│ de pecera   │  │ advertisement   │  │ cada 60s     │
└─────────────┘  └─────────────────┘  └──────────────┘
```

### Model Router v2 — Enrutamiento inteligente de 3 niveles

| Nivel | Qué hace | Latencia | Cobertura |
|-------|----------|----------|-----------|
| **Tier 0** | 462 patrones exactos + 8 regex. Zero-inference. | <1ms (clasificación) | ~92% comandos |
| **Tier 1** | Clasificador `qwen2.5-coder:1.5b` (500MB RAM) | 300–500ms | ~6% comandos |
| **Tier 2** | Razonador `qwen2.5-coder:7b-instruct` (4.7GB, bajo demanda) | 5–30s | ~2% conversación |

El 92% de los comandos diarios ("enciende la luz", "temp", "netflix", "me voy al super") se
resuelven sin tocar ningún modelo de IA.

---

## Dispositivos integrados

| Dispositivo | Protocolo | Método | Estado |
|-------------|-----------|--------|--------|
| **Enchufe Tuya** | WiFi (LAN) | `tinytuya` protocolo 3.5, sin cloud | ✅ ON/OFF en <2s |
| **Sensor Xiaomi LYWSD03MMC** | BLE GATT | Lectura directa característica `ebe0ccc1` | ✅ temp/hum/bat |
| **FanLamp F8808** | BLE advertisements | ESP32 bridge vía USB serial | ✅ 11 comandos |
| **HVAC General/Fujitsu** | LIN bus | ESP32 + transceptor LINTTL3 | 🔜 Pendiente |

---

## Estructura del proyecto

```
luxe-core-ai/
├── server/
│   ├── model_router/        ← Model Router v2 (3-tier routing)
│   │   ├── router.py        ← Servidor HTTP (:18790)
│   │   ├── config.py        ← Tier 0 (462 patrones), cache, device state
│   │   ├── classifier.py    ← Clasificación semántica (bge-m3 embeddings)
│   │   ├── comfort.py       ← Comfort Advisor (índice NOAA, zonas ASHRAE)
│   │   ├── smart_advisor.py ← Smart Advisor (interior vs exterior)
│   │   └── context.py       ← Gestión de sesiones
│   ├── integrations/        ← Drivers de dispositivos (Python)
│   │   ├── tuya_devices.py  ← Enchufe Tuya (tinytuya, protocolo 3.5)
│   │   ├── ble_sensors.py   ← Sensor Xiaomi (bleak, GATT directo)
│   │   └── hvac_bridge.py   ← Puente HVAC (stub — trabajo futuro)
│   ├── tools/               ← Wrappers CLI invocados por OpenClaw
│   │   ├── home.sh          ← Router unificado de comandos
│   │   ├── tuya_set.py      ← Control absoluto enchufe (on/off)
│   │   ├── tuya_status.py   ← Lectura estado enchufe
│   │   ├── tuya_toggle.py   ← Alternar enchufe
│   │   └── sensor_daemon_wrapper.sh
│   └── requirements.txt     ← Solo tinytuya + bleak
├── scripts/
│   ├── fanlamp_control.py   ← Control FanLamp vía ESP32 bridge (ACTUAL)
│   └── fanlamp_bt.py        ← Control FanLamp directo BLE (LEGACY)
├── firmware/
│   ├── esp32_fanlamp/       ← PlatformIO: ESP32 bridge BLE para FanLamp
│   │   ├── src/main.ino     ← Firmware Arduino (11 comandos + scan Xiaomi)
│   │   └── platformio.ini
│   ├── Enchufe/             ← Configs y dumps de dispositivos Tuya
│   └── btsnoop_fanlamp.log  ← Captura BLE (ingeniería inversa FanLamp)
├── docs/                    ← Memoria TFG (LaTeX) + ADRs + figuras
│   ├── main.tex             ← Documento principal
│   ├── sections/            ← Capítulos 01–09
│   ├── appendices/          ← Anexos A, B, C
│   ├── figures/             ← Figuras TikZ compilables
│   ├── design_decisions/    ← 8 ADR (Architecture Decision Records)
│   └── references.bib       ← Bibliografía
├── meta/                    ← Roadmap, TODO, notas de validación
├── tests/                   ← Tests de integración
├── AGENTS.md                ← Contexto del proyecto para agentes IA
├── SOUL.md                  ← Personalidad del asistente
└── README.md                ← Este archivo
```

---

## Quick Start

### Requisitos
- Ubuntu 24.04 LTS
- Python 3.12+, Node.js 24+
- Grupo `dialout` para acceso serial al ESP32

### Instalación

```bash
# 1. Instalar OpenClaw gateway
curl -fsSL https://openclaw.ai/install.sh | bash

# 2. Dependencias Python (system python, sin venv)
pip install tinytuya bleak

# 3. Arrancar servicios
systemctl --user enable --now openclaw-gateway
systemctl --user enable --now model-router
systemctl --user enable --now sensor-daemon

# 4. Dashboard en http://192.168.1.50:18789
```

### Tests

```bash
# Test del Model Router
curl http://127.0.0.1:18790/status

# Test de integración completo
python3 tests/test_integration.py

# Test del enchufe Tuya
python3 server/tools/tuya_status.py

# Test del FanLamp (requiere ESP32 conectado)
python3 scripts/fanlamp_control.py 3     # velocidad 3
```

### Comandos rápidos

```bash
bash server/tools/home.sh light_on       # Enciende luz
bash server/tools/home.sh fan_speed 3    # Ventilador velocidad 3
bash server/tools/home.sh plug_on        # Enciende enchufe
bash server/tools/home.sh scan           # Lee sensor Xiaomi
bash server/tools/home.sh all_off        # Apaga todo
```

---

## Transición FanLamp: de `fanlamp_bt.py` a `fanlamp_control.py`

El control del ventilador FanLamp F8808 evolucionó en dos fases:

### Fase 1 — `fanlamp_bt.py` (legacy, descartado)

Control directo desde el PC mediante anuncios BLE usando `btmgmt` (herramienta
de `bluez`). Problemas:

- Requería `sudo` para parar/arrancar `bluetoothd`
- Dejaba el adaptador Bluetooth del servidor inutilizado para otras tareas (BLE scan del Xiaomi)
- Inestable: el bluetoothd del PC podía no recuperarse correctamente tras cada comando
- Latencia alta (~3s por comando)

### Fase 2 — ESP32 Bridge + `fanlamp_control.py` (actual)

Un **ESP32 DevKit V1** dedicado actúa como radio BLE externa:

1. **Firmware** (`firmware/esp32_fanlamp/src/main.ino`): Arduino/PlatformIO.
   El ESP32 expone un puerto serie USB (115200 baud) y espera comandos de
   1 carácter (`0`–`5`, `f`, `F`, `l`, `L`, `n`, `s`). Al recibir un comando,
   transmite el par de anuncios BLE (G1 + G2, 31 bytes cada uno) correspondiente.
   También escanea y lee el sensor Xiaomi vía GATT cuando recibe `s`.

2. **Script Python** (`scripts/fanlamp_control.py`): Traduce comandos legibles
   (`"off"`, `"fan_on"`, `"light_off"`, `"scan"`) a caracteres y los envía por
   USB serial. Implementa DTR reset para reiniciar el ESP32 entre operaciones
   y `drain_until_ok()` para sincronización tras boot.

3. **home.sh** (`server/tools/home.sh`): Capa de enrutamiento unificado.
   Usa `sg dialout` para ejecutar `fanlamp_control.py` con los permisos
   adecuados sin necesidad de `sudo`.

Ventajas del ESP32 bridge:
- El Bluetooth del servidor queda libre para el sensor Xiaomi
- Sin `sudo`, sin parar `bluetoothd`
- Latencia ~1.5s por comando (vs ~3s del método legacy)
- El ESP32 puede resetearse independientemente si se bloquea
- El mismo ESP32 servirá en el futuro como puente LIN para la HVAC

---

## Licencia

**Proprietary — All rights reserved**
Copyright © 2026 Jesús Fernández López
