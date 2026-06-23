# Slide 17 — Auto-Recuperación y Tolerancia a Fallos

## Problema actual
- 4 bloques con listas en 2 columnas
- Circuit Breaker, Reintentos, SelfHealManager, Health Check — mucho texto repetitivo

## Esquema visual propuesto

### Diagrama TikZ: "Ciclo de Auto-Recuperación"
Un diagrama circular de estados mostrando el flujo de recuperación:

```
                    ┌──────────────┐
                    │   Ollama     │
                    │   caído      │
                    └──────┬───────┘
                           │ detecta (30s)
                    ┌──────▼───────┐
          ┌────────│ SelfHeal     │────────┐
          │        │ Manager      │        │
          ▼        └──────┬───────┘        ▼
   ┌──────────┐           │          ┌──────────┐
   │ Circuit  │     ┌─────▼─────┐    │  ESP32   │
   │ Breaker  │     │Reintentos │    │  USB     │
   │ OPEN 30s │     │backoff +  │    │ reset    │
   │ → CLOSED │     │jitter     │    │ DTR      │
   └──────────┘     └───────────┘    └──────────┘
```

### Texto a eliminar
- Los 4 bloques completos
- Solo mantener los nombres de cada mecanismo como etiquetas del diagrama

### Imagen AI generada
Prompt: "A circular self-healing system diagram showing autonomous recovery flow. Center node 'SelfHeal Manager' with three arrows going to 'Circuit Breaker' (3 states: closed/open/half-open), 'Retries' (exponential backoff), and 'ESP32 USB Reset'. Clean tech diagram with purple and teal nodes. Flat design with directional arrows."
