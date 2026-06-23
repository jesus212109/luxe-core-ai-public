# Streaming para Tier 2 — TODO

## Problema
El Model Router es síncrono. Cuando Tier 1 delega a Tier 2 (Mistral 7B),
el usuario ve 45-75s de silencio hasta recibir la respuesta completa.

## Solución propuesta
Implementar streaming SSE en el endpoint `/v1/chat/completions` del Model Router:

1. Detectar `stream: true` en el body de la request
2. Emitir inmediatamente `🤔 Pensando...` como primer chunk SSE
3. Tunelizar los tokens de Ollama como chunks SSE sucesivos
4. Tier 0 y Tier 1: empaquetar respuesta como evento SSE final

## Mejora esperada
- El usuario ve actividad instantánea (sin silencio de 75s)
- Las palabras aparecen progresivamente (~800ms por palabra)
- Experiencia mucho más cercana a ChatGPT

## Riesgos
- OpenClaw debe soportar respuestas streaming del proveedor model_router
- La respuesta SSE debe cumplir el formato OpenAI chat/completions chunks
- Aumenta complejidad del router (~100 líneas extra)

## Prioridad
Media — la experiencia actual funciona, pero 75s de silencio es malo.
Hacer tras estabilizar los bugs actuales (outdoor, recovery messages, idioma).
