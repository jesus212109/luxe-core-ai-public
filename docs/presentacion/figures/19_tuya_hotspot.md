# Slide 19 — Integración Tuya: Control Local y Hotspot Spoofing

## Problema actual
- Imagen + lista de protocolo + bloque con enumerate de 4 pasos
- La imagen es grande (5cm) y ocupa media diapositiva

## Esquema visual propuesto

### Diagrama TikZ: "Flujo de Hotspot Spoofing"
Un diagrama de secuencia horizontal de 4 pasos con la imagen del enchufe al final:

```
   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
   │ ① AP    │ → │ ② Cloud │ → │ ③ Extraer│ → │ ④ Air-  │
   │  Móvil  │    │  Tuya   │    │ Local Key│    │  Gapped │
   └─────────┘    └─────────┘    └─────────┘    └──┬──────┘
                                                    │
                                              ┌─────▼──────┐
                                              │ [enchufe]  │
                                              │ 192.168... │
                                              │ tinytuya   │
                                              └────────────┘
```

### Texto a eliminar
- La lista de protocolo (`status()`, `toggle()`, etc.)
- El bloque de enumerate con los 4 pasos textuales
- Mantener solo la imagen del enchufe + el diagrama de 4 pasos

### Imagen AI generada
Prompt: "A 4-step horizontal process diagram showing: 1) mobile hotspot icon, 2) cloud connection icon, 3) key extraction icon, 4) local network icon with a smart plug device at the end. Connection arrows between steps. Clean flat design, minimal text, purple and teal accents."
