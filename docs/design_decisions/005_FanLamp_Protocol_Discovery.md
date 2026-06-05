# 005 — Protocolo de Control del Ventilador FanLamp F8808 mediante Anuncios BLE

## Contexto y Motivación

El ventilador de techo FanLamp Pro F8808 (Mikomika) adquirido en AliExpress por un coste inferior a 35€ representa el tercer dispositivo heterogéneo del ecosistema Luxe Core AI, tras el enchufe Tuya y el sensor Xiaomi. A diferencia de los anteriores, el ventilador no dispone de documentación pública sobre su protocolo de comunicación: el fabricante solo ofrece una aplicación móvil propietaria (FanLamp Pro) que se comunica con el dispositivo mediante Bluetooth Low Energy a través de un servicio con UUID `0000fee7-0000-1000-8000-00805f9b34fb`, asociado al ecosistema Tencent IoT.

El objetivo de esta decisión de diseño es documentar el proceso de **ingeniería inversa del protocolo de comunicación** que permitió controlar el ventilador desde la estación de trabajo local sin depender de la aplicación del fabricante ni de ningún servicio en la nube, **utilizando exclusivamente el hardware ya disponible** en el proyecto (ordenador portátil, ESP32 DevKit V1 y teléfono Android) y con **coste económico cero adicional**.

## Restricciones y Filosofía del Proyecto

Dos principios han guiado la investigación del protocolo:

1. **Economía real como factor limitante.** El autor es estudiante sin ingresos. Cada dispositivo del ecosistema ha sido seleccionado por su bajo coste (el ventilador es el modelo más económico de AliExpress, instalado personalmente) y la inversión en hardware auxiliar se ha mantenido en cero siempre que ha sido posible. Esto ha descartado deliberadamente soluciones más sencillas pero costosas, como un dongle analizador de protocolos BLE (nRF52840, ~10€) o un mando universal por infrarrojos.

2. **Aprender resolviendo problemas reales.** La heterogeneidad de protocolos (Wi-Fi propietario, Bluetooth Low Energy, bus LIN) es una característica deliberada del ecosistema, no un defecto. El proyecto se ha diseñado para demostrar que una capa de orquestación con inteligencia artificial (OpenClaw + modelos locales) puede unificar dispositivos que individualmente son "tontos" —como un humidificador de pecera controlado mediante un enchufe inteligente— y aportarles capacidad de razonamiento sin modificar su hardware.

## Descubrimiento del Protocolo

La investigación del protocolo del FanLamp F8808 se desarrolló a lo largo de más de 40 horas de trabajo, articulándose en las siguientes fases:

### Fase 1: Intento fallido de conexión GATT estándar (Días 1-2)

El enfoque inicial fue el más intuitivo: conectar al ventilador mediante Bluetooth Low Energy utilizando `bleak` desde el portátil y descubrir sus servicios GATT. Aunque el dispositivo se anunciaba correctamente en los escaneos BLE como `C21-61A` con los UUIDs `0000fee7` y `00003802`, todos los intentos de conexión resultaban en una desconexión automática tras aproximadamente 1.5 segundos durante la fase de *service discovery*. El ventilador exigía una autenticación propietaria (protocolo Tencent) antes de exponer sus servicios, y rechazaba cualquier intento de emparejamiento estándar con `AuthenticationFailed`.

Se probaron las siguientes vías sin éxito:
- Emparejamiento con los cinco agentes BlueZ (`NoInputNoOutput`, `DisplayYesNo`, `DisplayOnly`, `KeyboardOnly`, `KeyboardDisplay`)
- Captura del tráfico HCI desde el teléfono Android (Nothing Phone 2, Android 15) — el *firmware* del dispositivo **no incluye datos ACL de BLE** en el registro HCI
- Suplantación del ventilador (*spoofing*) desde el portátil mediante BlueZ D-Bus — los anuncios no llegaban a emitirse por limitaciones de la pila Bluetooth de Linux en los adaptadores Intel y Realtek disponibles

### Fase 2: Investigación de la aplicación móvil (Días 3-4)

Al no poder establecer una conexión GATT, se extrajo el APK de la aplicación FanLamp Pro desde el teléfono (`com.jingyuan.fan_lamp`, 60 MB) y se decompiló con `jadx`. La aplicación resultó estar desarrollada con Flutter (Dart compilado a código nativo ARM64), lo que limitó el análisis a las capas Java/Kotlin accesibles mediante decompilación.

El hallazgo clave se produjo al analizar la clase `com.allinktec.ble_plugin.BlePlugin.java`, que reveló que la aplicación **no utiliza conexiones GATT para enviar comandos al ventilador, sino anuncios BLE** (*BLE Advertisements*). El mecanismo es el siguiente:

1. La aplicación invoca métodos de la biblioteca nativa `com.alllink.encodelib.ToolV3` (implementada en `libencodeV3.so`, código ARM64 compilado)
2. Cada comando (encender ventilador, cambiar velocidad, apagar luz) se codifica como un array de 26 bytes
3. Estos 26 bytes se convierten en 13 UUIDs de 16 bits (cada par de bytes forma un UUID con formato `0000XXYY-0000-1000-8000-00805f9b34fb`)
4. Los UUIDs se emiten como datos de servicio en un anuncio BLE
5. El ventilador, que permanece en escucha pasiva, decodifica los UUIDs y ejecuta el comando

Este mecanismo tiene la ventaja de no requerir conexión GATT (el dispositivo y el controlador no necesitan emparejarse ni mantener una conexión activa), pero introduce un desafío adicional: **los comandos incluyen un contador de secuencia y un CRC variable** que impiden la simple reproducción de patrones capturados.

### Fase 3: Captura de patrones con ESP32 (Días 4-6)

Al no poder emitir anuncios BLE personalizados desde el portátil (los adaptadores Bluetooth del mismo rechazaban los *advertisements* crudos con error de permisos del kernel), se repurpuso el **ESP32 DevKit V1** —inicialmente adquirido para el puente LIN del HVAC— como **radio BLE programable**. El ESP32 se flasheó con firmware Arduino que actuaba en dos modos:

- **Modo escáner:** captura pasiva de todos los anuncios BLE cercanos, filtrando aquellos que contienen al menos 10 UUIDs (los comandos del ventilador tienen 13)
- **Modo reproductor:** emisión de anuncios BLE con conjuntos arbitrarios de UUIDs, replicando exactamente los patrones capturados

La captura de patrones se realizó en sesiones coordinadas con la aplicación móvil:

1. Se encendía el ESP32 en modo escáner
2. Se pulsaba un botón específico en la aplicación FanLamp Pro (por ejemplo, "Velocidad 3")
3. La aplicación emitía aproximadamente 20 anuncios con el comando codificado
4. El ESP32 capturaba los 13 UUIDs del comando

Se observó que los anuncios del teléfono alternaban entre dos grupos de UUIDs: un **Grupo 1** (que comienza con `08f0 8220`) asociado al control del ventilador, y un **Grupo 2** (que comienza con `f877 5fb6`) asociado al control de la luz. Para que el ventilador ejecutase un comando, era necesario emitir **ambos grupos alternadamente**, replicando el patrón de la aplicación.

Se identificó que el byte 3 (tercer UUID) del Grupo 1 codifica la velocidad o estado del ventilador:
- `4d`: apagado general
- `46`: velocidad 1
- `59`: velocidad 2
- `58`: velocidad 3
- `5b`: velocidad 4
- `5a`: velocidad 5

Los bytes 9-13 contienen un código de redundancia cíclica (CRC) que varía con el contador de secuencia (`tx_count` en la biblioteca nativa). Esto exigió que cada patrón capturado se reprodujese **íntegramente** (sin modificar ningún byte) para que el ventilador lo aceptase.

### Fase 4: Reproducción de comandos y control autónomo (Días 6-8)

La reproducción de comandos capturados confirmó que el protocolo funciona desde el ESP32 sin necesidad de la aplicación móvil. Se mapearon los siguientes comandos:

| Comando | Función | Patrón capturado |
|---------|---------|------------------|
| OFF general | Apaga ventilador y luz | G1=4d36 + G2 emparejado |
| Velocidad 1-5 | Ajusta velocidad del ventilador | G1 variable + G2 emparejado |
| Fan ON/OFF | Solo enciende/apaga ventilador | G1=3836 / G1=3236 |
| Light ON/OFF | Solo enciende/apaga luz | G1=3b36 / G1=3536 |
| Modo noche | Atenúa luz y ventilador | G1=3a36 + G2 emparejado |

### Fase 5: Eliminación del ESP32 con btmgmt (Día 9)

El objetivo de soberanía hardware implicaba poder prescindir del ESP32 como intermediario y enviar los comandos directamente desde el adaptador Bluetooth del portátil (y, en el futuro, de la torre servidora). La solución llegó al descubrir que la herramienta `btmgmt` del paquete `bluez` permite emitir anuncios BLE con datos crudos directamente desde la línea de comandos, siempre que el demonio `bluetoothd` (que compite por el control del adaptador) se detenga temporalmente.

El comando equivalente para apagar el ventilador es:

```bash
sudo systemctl stop bluetooth
sudo btmgmt power on
sudo btmgmt add-adv -d "0201051B03F0082082364DFD5F0632DB861E3A770F9180FFA221C6532B7C8B" -t 2 -c 1
# Alternar con el patrón G2
sudo systemctl start bluetooth
```

Este procedimiento se encapsuló en el script Python `fanlamp_bt.py`, que automatiza la parada de `bluetoothd`, la emisión alternada de patrones G1+G2 durante la ventana de transmisión, y la reactivación del servicio.

## Decisiones de Diseño y *Trade-offs*

### Decisión 1: No comprar hardware adicional de sniffing
Invertir 10€ en un dongle analizador BLE (nRF52840) habría reducido el tiempo de desarrollo de días a horas. Sin embargo, se optó por la vía de la ingeniería inversa con herramientas existentes (ESP32, jadx, Wireshark) porque:
- Refuerza el principio de **soberanía tecnológica**: el proyecto no depende de hardware especializado externo
- Maximiza el **aprendizaje**: el proceso de ingeniería inversa de un protocolo propietario es una competencia transferible a cualquier dispositivo IoT futuro
- Respeta la **restricción económica real** del contexto académico

### Decisión 2: Usar BLE Advertisements en lugar de GATT
El descubrimiento de que el ventilador usa anuncios BLE en lugar de conexiones GATT fue accidental (surgió del análisis del APK). Una vez conocido, se validó que era el enfoque correcto porque elimina la necesidad de mantener una conexión punto a punto, simplifica la arquitectura del controlador (basta con emitir un anuncio, sin gestionar estados de conexión), y es compatible con el estándar BLE sin requerir *pairing*.

### Decisión 3: Reproducir patrones íntegros en lugar de decodificar el CRC
La biblioteca `libencodeV3.so` implementa un CRC variable con contador de secuencia y generador de números aleatorios. Intentar replicar el algoritmo de codificación habría requerido ingeniería inversa de código ARM64 compilado. La alternativa pragmática de **capturar y reproducir patrones íntegros** —aunque limita cada comando a un único uso antes de que el contador lo invalide— fue suficiente para los 11 comandos necesarios (OFF, 5 velocidades, 2 estados de ventilador, 2 estados de luz, modo noche). Para un uso continuado, el script Python puede recargar los patrones desde la aplicación original periódicamente (por ejemplo, una vez al día), o en el futuro implementar el algoritmo CRC desde cero.

## Consecuencias

1. **El ventilador FanLamp F8808 está completamente integrado** en el ecosistema Luxe Core AI, controlable mediante scripts Python desde cualquier ordenador con adaptador Bluetooth y permisos de administrador.

2. **No se requiere la aplicación FanLamp Pro** para el funcionamiento diario. La aplicación solo se necesita si se desean capturar patrones frescos (por rotación de contador, opcional).

3. **El ESP32 DevKit V1 queda liberado** para su función original como puente LIN del sistema HVAC, sin conflicto de recursos.

4. **El protocolo de anuncios BLE es genérico** y podría aplicarse a otros dispositivos del ecosistema Tencent IoT que utilicen el mismo mecanismo (servicio `0000fee7`).

5. **El coste económico de la integración ha sido de 0€**, cumpliendo el objetivo de máxima eficiencia con recursos existentes.

## Validación

Todos los comandos fueron validados con el ventilador físico F8808 en la red air-gapped (`192.168.1.0/24`) el 16 de mayo de 2026. El script `fanlamp_bt.py` se ejecutó con éxito desde el portátil de desarrollo sin el ESP32 conectado, confirmando la independencia total del hardware auxiliar.
