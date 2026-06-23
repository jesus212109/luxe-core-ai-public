# Slide 3 — Resumen Ejecutivo

## Problema actual
- 2 columnas con 6 + 6 bullets (12 items total)
- Demasiado texto: frases completas con explicaciones

## Esquema visual propuesto

### Diagrama TikZ: "Panorama del Sistema"
Un esquema de arquitectura simplificada mostrando los 4 dispositivos conectados al servidor central:

```
                    ┌──────────────┐
                    │  Servidor    │
                    │  Ryzen 5     │
                    │  (Edge AI)   │
                    └──┬───┬───┬──┘
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐     ┌──────────────┐
    │ Enchufe  │    │  Sensor  │     │  FanLamp     │
    │  Tuya    │    │  Xiaomi  │     │  F8808       │
    │ (+humid) │    │  (BLE)   │     │  (BLE inv.)  │
    └──────────┘    └──────────┘     └──────────────┘
```

### Cifras clave (en cajas flotantes alrededor del diagrama):
- "462 patrones — 92% comandos <1ms"
- "0 € licencias"
- "Red 100% air-gapped"

### Texto a eliminar
- Las 2 columnas completas de bullets
- Mantener solo el bloque "¿Qué es Luxe Core AI?" como intro

### Imagen AI generada
Prompt: "A clean, minimalist isometric diagram of a home server rack connected to three IoT devices: a smart plug, a temperature sensor, and a ceiling fan. Tech blue and white color scheme. No text, just icons and connection lines. Flat design style."
