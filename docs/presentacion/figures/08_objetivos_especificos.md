# Slide 8 — Objetivos Específicos e Indicadores

## Problema actual
- 2 columnas con enumerate + sublistas anidadas
- 3 objetivos específicos con 2-4 subitems cada uno + 4 indicadores

## Esquema visual propuesto

### Diagrama TikZ: "Rúbrica Visual de Cumplimiento"
3 tarjetas horizontales representando los 3 objetivos, con indicadores en la parte inferior como barras de progreso:

```
 ┌──────────────────────────────────────────────────────────────────┐
 │   OBJETIVO 1: Microservicios    │  OBJETIVO 2: HVAC LIN        │
 │   ┌──────────────────────┐      │  ┌──────────────────────┐     │
 │   │ OpenClaw systemd     │      │  │ ESP32 + LINTTL3      │     │
 │   │ Diagramas despliegue │      │  │ Firmware C++20       │     │
 │   │ ✅ Completado         │      │  │ ⏳ Pendiente          │     │
 │   └──────────────────────┘      │  └──────────────────────┘     │
 ├──────────────────────────────────┴──────────────────────────────┤
 │   OBJETIVO 3: IoT Heterogéneo                                    │
 │   ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
 │   │ Xiaomi BLE  │  │ Tuya Local   │  │ FanLamp Inv.         │  │
 │   │ ✅ RF-02    │  │ ✅ RF-03     │  │ ✅ RF-04             │  │
 │   └─────────────┘  └──────────────┘  └──────────────────────┘  │
 ├──────────────────────────────────────────────────────────────────┤
 │ INDICADORES:  ████████░░ 92% cobertura  │  ██████████ <2s lat  │
 │               ██████████ 99% uptime     │  ██████████ air-gap  │
 └──────────────────────────────────────────────────────────────────┘
```

### Texto a eliminar
- Las enumeraciones anidadas completas
- Solo mantener los nombres de objetivos como títulos de tarjeta
- Indicadores como barras de progreso

### Imagen AI generada
Prompt: "Three horizontal cards in a dashboard style showing project goals with progress bars and checkmarks. First card 'Microservices' shows green checkmark, second 'HVAC' shows clock pending icon, third 'IoT Integration' shows three green sub-checks. Clean corporate style, purple and teal accents. Flat UI design."
