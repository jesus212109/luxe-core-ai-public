# Slide 13 — Model Router v2: Enrutamiento Inteligente

## Problema actual
- 2 columnas: izquierda con 3 niveles descritos con texto, derecha con 4 mecanismos en lista
- Demasiado texto explicativo

## Esquema visual propuesto

### Diagrama TikZ: "Flujo del Model Router v2" (ya existe fig_8_3.pdf)
Ampliar el diagrama existente y mover la explicación a anotaciones sobre el propio flujo:

```
                        ┌──────────┐
    Usuario ──────────→ │ ¿Patrón? │──SÍ──→ ⚡ Tier 0 (462 patrones, <1ms)
    Telegram            └────┬─────┘
                             │NO
                        ┌────▼─────┐
                        │¿Simple?  │──SÍ──→ 🧠 Tier 1 (qwen2.5 1.5B, 300ms)
                        └────┬─────┘
                             │NO
                        ┌────▼─────┐
                        │ Mistral  │─────→ 💬 Tier 2 (7B conversacional, 27-60s)
                        │   7B Q4  │
                        └──────────┘

   + LRU 200 entradas  +  Embeddings bge-m3  +  Circuit Breaker
```

### Datos clave (en callouts flotantes):
- Cada tier con un icono: ⚡ para Tier 0, 🧠 para Tier 1, 💬 para Tier 2
- Latencia mostrada como etiqueta en la flecha de salida

### Texto a eliminar
- Toda la columna derecha de "Mecanismos adicionales"
- La descripción textual de cada tier (reemplazada por anotaciones)

### Imagen AI generada
Prompt: "A flowchart diagram showing a 3-tier AI model router. User message enters from left, passes through three decision nodes: Pattern Matching (lightning icon), Classifier 1.5B (brain icon), Reasoner 7B (speech bubble icon). Each node shows latency numbers. Clean flat design, purple and cyan color scheme, tech aesthetic."
