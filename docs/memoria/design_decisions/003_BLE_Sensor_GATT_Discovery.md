# 003 — Lectura GATT Directa del Sensor Xiaomi LYWSD03MMC

## Contexto del Cambio

La decisión 002 (`002_Network_Isolation_and_Spoofing.md`) planificaba flashear los sensores Xiaomi LYWSD03MMC con el firmware abierto ATC de pvvx para poder leer temperatura y humedad desde los *advertisements* BLE sin cifrar. Este plan, aunque correcto en su planteamiento, exigía un paso de flasheo OTA que introducía fricción operativa: requería un navegador Chromium con Web Bluetooth, una ventana de *deep sleep* del sensor muy ajustada (apenas 30 segundos tras reinserción de pila), y dependía de que el firmware *stock* aceptase la conexión OTA sin autenticación previa.

Durante las pruebas de campo del 13 de mayo de 2026, se constató que la herramienta web `TelinkMiFlasher.html` no conseguía detectar el sensor en el entorno del portátil de desarrollo, y que el *adb backup* del teléfono (Nothing Phone 2) no permitía extraer la *bind key* de Mi Home por las restricciones de permisos de Android 15. Ambos caminos —flasheo y extracción de clave— quedaban bloqueados.

## Descubrimiento de la Ruta GATT

La investigación dio un giro cuando se conectó al sensor LYWSD03MMC mediante `bleak` y se obtuvo un volcado completo de sus servicios GATT. El sensor expone, entre otros, el servicio propietario de Xiaomi (`ebe0ccb0-7a0a-4b0c-8a1a-6ff2997da3a6`) con la característica `ebe0ccc1`, que resultó ser legible **sin autenticación previa**. Esta característica devuelve 5 bytes con la siguiente estructura:

| Byte | Tipo | Descripción |
|------|------|-------------|
| 0-1 | `int16` (LE, signed) | Temperatura $\times$ 100 |
| 2 | `uint8` | Humedad relativa (%) |
| 3-4 | `uint16` (LE) | Voltaje de batería (mV) |

La primera lectura arrojó `cb093bef0b`, que decodificada produce:

- **Temperatura:** $0\mathrm{x}09\mathrm{cb} = 2507 \rightarrow 25.07^\circ\mathrm{C}$
- **Humedad:** $0\mathrm{x}3\mathrm{b} = 59\%$
- **Batería:** $0\mathrm{x}0\mathrm{bef} = 3055\ \mathrm{mV}$

Lecturas posteriores confirmaron la estabilidad de la decodificación: 25.11°C, 25.07°C, 25.08°C con humedad constante del 59% y batería entre 3048–3055 mV.

## Decisión Arquitectónica

Se ha optado por **leer los sensores Xiaomi mediante conexión GATT periódica** en lugar de flashear el firmware ATC. Los fundamentos de esta decisión son:

1. **Soberanía del dato preservada.** La lectura GATT no requiere *bind key* de Xiaomi, no pasa por la nube de Mi Home y no depende de la aplicación del fabricante. El sensor entrega sus datos directamente al portátil sin intermediarios.

2. **Cero modificación del hardware.** El sensor permanece con su firmware de fábrica. No se pierde la garantía, no hay riesgo de *brick*, y el procedimiento es reversible en cualquier momento. Si en el futuro se desea flashear ATC, el camino sigue abierto.

3. **Implementación más simple.** El módulo `ble_sensors.py` pasó de ser un *stub* de 16 líneas a una implementación funcional de 150 líneas que:
   - Escanea dispositivos con prefijo `LYWSD` mediante `bleak`.
   - Conecta al sensor y lee la característica `ebe0ccc1`.
   - Decodifica temperatura, humedad y voltaje.
   - Expone una clase `BLESensorManager` con métodos `discover_sensors()` y `read_sensor()`.

4. **Compatibilidad con la arquitectura de microservicios.** El módulo de sensores BLE es un componente desacoplado que el orquestador puede invocar periódicamente sin mantener conexiones persistentes, siguiendo el patrón de *polling* ligero ya empleado en el módulo Tuya.

## *Trade-off* Asumido

La conexión GATT requiere que el puerto BLE del servidor esté disponible durante unos segundos cada ciclo de lectura (conexión + lectura + desconexión $\approx$ 12 segundos). Durante ese intervalo, el sensor no puede ser leído por otro dispositivo BLE. Este *trade-off* es aceptable en un escenario de domótica local con un único punto central de recolección de datos.

El firmware ATC, en contraste, ofrece un modo puramente *stateless* (el sensor emite, el servidor escucha sin conectar), que elimina este acoplamiento temporal. Se mantiene como opción de mejora futura si la frecuencia de lectura necesitase aumentar o si se añadiesen más sensores al ecosistema.

## Consecuencias

1. **RF-02 (Lectura de sensores ambientales): verificado.** El ecosistema puede leer temperatura y humedad de los sensores Xiaomi sin dependencias externas.
2. **Código de integración BLE completamente operativo** en `server/integrations/ble_sensors.py`, pendiente únicamente de integrar con el bucle principal del orquestador OpenClaw.
3. **Documentación del protocolo GATT de Xiaomi** registrada para referencia futura y para la memoria del TFG.
4. **El plan de flasheo ATC se aplaza, no se cancela.** La ruta GATT es el camino funcional inmediato; la ruta ATC permanece como optimización para un escenario con múltiples sensores o requisitos de ultra-baja latencia.

## Validación

La integración fue validada con el sensor físico `A4:C1:38:84:03:1C` (LYWSD03MMC) en el entorno de red air-gapped, con los siguientes resultados:

```
$ python -m server.integrations.ble_sensors
Found sensor: LYWSD03MMC (A4:C1:38:84:03:1C) RSSI=-32
A4:C1:38:84:03:1C: 25.00°C  59%  3048mV
```
