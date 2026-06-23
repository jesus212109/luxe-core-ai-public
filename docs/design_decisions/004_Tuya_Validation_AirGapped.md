# 004 — Validación de la Integración Tuya en Red Air-Gapped

## Contexto

La decisión 002 (`002_Network_Isolation_and_Spoofing.md`) estableció la arquitectura de red aislada y documentó el procedimiento de *Hotspot Spoofing* para el *onboarding* de dispositivos Tuya. El *smart plug* (enchufe inteligente) quedó emparejado con éxito mediante esta técnica, almacenándose su `device_id`, `local_key` y dirección IP en `firmware/Enchufe/devices.json` y referenciándose como constante `SMART_PLUG_CONFIG` en el módulo `server/integrations/tuya_devices.py`.

El 13 de mayo de 2026 se procedió a la validación *end-to-end* de este módulo sobre la red air-gapped real.

## Procedimiento de Validación

La validación siguió el plan documentado en `meta/TODO.md`:

1. **Comprobaciones previas:** verificación de conectividad con el AP aislado (`ip a | grep 192.168.1`), *ping* al dispositivo (`ping 192.168.1.100`), y *smoke tests* de sintaxis (`py_compile`, `import` de `SMART_PLUG_CONFIG`).

2. **Ejecución del comando de toggle:** `python -m server.integrations.tuya_devices`

3. **Verificación física:** el relé del enchufe emitió un clic audible confirmando el cambio de estado.

## Resultados

El módulo Tuya superó la validación sin errores en ambas direcciones:

```
[INFO] Current plug state: True
[INFO] Setting plug 192.168.1.100 -> OFF
[INFO] New plug state: False
```

Una segunda ejecución confirmó la alternancia:

```
[INFO] Current plug state: False
[INFO] Setting plug 192.168.1.100 -> ON
[INFO] New plug state: True
```

El tiempo de respuesta entre la orden y el cambio de estado efectivo fue inferior a 2 segundos, cumpliendo el requisito no funcional RNF-03.

## Decisiones de Diseño Ratificadas

1. **Protocolo 3.5 de `tinytuya` correcto.** La `local_key` embebida en el código es válida y la comunicación con el dispositivo a través del AP aislado funciona sin intermediación del *cloud* de Tuya.

2. **Direccionamiento IP estático.** El dispositivo mantiene la IP `192.168.1.100` de forma estable en la red aislada, lo que permite referenciarlo por IP sin necesidad de *service discovery* o mDNS.

3. **Interfaz programática.** El módulo expone la clase `TuyaSmartPlug` con métodos `status()`, `is_on()`, `set_state(on: bool)` y `toggle()`, además de la excepción personalizada `TuyaCommunicationError` para manejo de fallos de conectividad. Esta interfaz es suficiente para que el orquestador OpenClaw pueda controlar el enchufe mediante *tool calling*.

## Consecuencias

1. **RF-03 (Control de dispositivos Tuya): verificado.** El ecosistema puede activar y desactivar el enchufe inteligente de forma local.
2. **RNF-03 (Baja latencia): verificado.** El ciclo completo de lectura-escritura-verificación de estado está por debajo del umbral de 2 segundos.
3. **La integración Tuya está completa** y lista para ser invocada desde el bucle de control del orquestador.
4. **Las credenciales permanecen seguras.** La `local_key` no se transmite fuera del repositorio y está excluida de cualquier comunicación con el exterior por el aislamiento de red.
