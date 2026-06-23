# Slide 4 — Motivación Edge AI

## Problema actual
- 2 columnas: izquierda con 2 listas de 4+4 bullets, derecha con 2 bloques
- Mucho texto explicativo dentro de los bullets

## Esquema visual propuesto

### Diagrama TikZ: "Modelos Locales vs Cloud"
Comparativa visual de 3 modelos pequeños locales en CPU vs modelos grandes en GPU/cloud:

```
   ┌─────────────────────┐      ┌─────────────────────┐
   │   LOCAL (Edge AI)   │      │   CLOUD (GPT-4o)    │
   │                     │      │                     │
   │  qwen2.5 1.5B       │      │  30B+ parámetros    │
   │  ┌───┐              │      │  ┌──────────────┐   │
   │  │CPU│  300-500ms   │      │  │GPU $5000+    │   │
   │  └───┘              │      │  └──────────────┘   │
   │                     │      │                     │
   │  mistral 7B Q4      │  VS  │  Requiere Internet  │
   │  ┌───┐  27-60s      │      │  Datos en servers   │
   │  │CPU│              │      │  externos           │
   │  └───┘              │      │                     │
   └─────────────────────┘      └─────────────────────┘
```

### Texto a eliminar
- Las listas de bullets completas de ambas columnas
- Mantener solo los nombres de modelos + latencias como datos clave

### Imagen AI generada
Prompt: "Side-by-side comparison infographic: left side shows a small home server tower running AI locally with lock icon for privacy, right side shows cloud servers with data traveling up to the cloud. Clean tech illustration, blue and teal color scheme. Flat vector style."
