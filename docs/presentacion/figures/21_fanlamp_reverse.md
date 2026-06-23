# Slide 21 — FanLamp F8808: Ingeniería Inversa del Protocolo

## Problema actual
- Imagen + 5 bullets + tabla de comandos (5 columnas)
- Mucha información densa

## Esquema visual propuesto

### Diagrama TikZ: "Proceso de Ingeniería Inversa"
Un diagrama timeline de 3 pasos con la tabla de comandos debajo como "resultado":

```
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ ① APK FanLamp│ ──→ │ ② jadx       │ ──→ │ ③ BLE ads    │
   │  ~60 MB      │     │ decompilar   │     │ 13 UUIDs     │
   │ Flutter/ARM │     │ Dart→Java    │     │ por comando  │
   └──────────────┘     └──────────────┘     └──────┬───────┘
                                                     │
   ┌─────────────────────────────────────────────────▼──────────────┐
   │  Comandos descubiertos:                                       │
   │  ┌─────┬──────────┬───────────┬───────────┬─────────┐        │
   │  │ OFF │ FAN ON/OFF│ LIGHT ON/OFF│ VEL 1-5 │ NIGHT   │        │
   │  └─────┴──────────┴───────────┴───────────┴─────────┘        │
   └──────────────────────────────────────────────────────────────┘
```

### Texto a eliminar
- Los 5 bullets de la columna derecha
- Solo mantener las 3 fases del proceso + la tabla de comandos como resultado

### Imagen AI generada
Prompt: "A 3-step reverse engineering process diagram: 1) APK file icon with Flutter logo, 2) decompiler jadx tool icon, 3) BLE advertisement waves icon. Below: a table showing 5 discovered commands (OFF, FAN, LIGHT, SPEED 1-5, NIGHT). Clean tech diagram, purple and teal color scheme. Flat vector style with arrows connecting steps."
