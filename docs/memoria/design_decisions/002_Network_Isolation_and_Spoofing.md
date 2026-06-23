# 002 - Aislamiento de Red, Hotspot Spoofing y Firmware ATC

## Contexto del Cambio
La decisión 001 (`001_Local_Edge_Architecture.md`) ya cortó el cordón umbilical con los servidores de la UCO y trasladó toda la inferencia y el almacenamiento a la propia red doméstica. Sin embargo, durante las primeras pruebas de campo nos dimos cuenta de que esa "red doméstica" seguía siendo el mismo Wi-Fi del piso, compartido con teléfonos, portátiles personales, una Smart TV y, sobre todo, con dispositivos comerciales que llaman a sus *clouds* sin avisar (Xiaomi, Tuya, Alexa, etc.). En la práctica, cada bombilla o enchufe estaba abriendo un canal saliente hacia servidores en Europa o Asia, lo cual erosionaba la promesa de soberanía del dato que sostiene todo el TFG.

Hacía falta dar un paso más: aislar físicamente la infraestructura de OpenClaw del resto de la red de casa y dejarla operando como una isla.

## Decisión Arquitectónica
Se ha adoptado una arquitectura de **red 100% air-gapped** sobre un router TP-Link autónomo dedicado en exclusiva al ecosistema Luxe Core AI. Este router **no tiene salida a Internet**: no se enlaza al router del operador ni se le conecta vía WAN. Toda la comunicación entre la estación de trabajo (cerebro Python/OpenClaw), el ESP32 (puente LIN), los sensores BLE y los actuadores Tuya viaja exclusivamente por ese segmento aislado.

Esta decisión, que sobre el papel parece dramática, resuelve de un plumazo varios problemas a la vez: elimina cualquier exfiltración de telemetría hacia *clouds* de terceros, neutraliza un vector enorme de ataque (un dispositivo comprometido en la red doméstica principal ya no ve siquiera al sistema) y nos da control total sobre el direccionamiento IP, los rangos DHCP y la planificación de los nodos.

### Topología
- **Router TP-Link aislado:** sirve como AP Wi-Fi y switch para todo el ecosistema. WAN desconectada físicamente.
- **Subred dedicada:** `192.168.1.0/24`. La estación de trabajo ocupa la IP fija reservada para el orquestador; los actuadores Tuya quedan en `192.168.1.100` y siguientes.
- **Sin DNS externo:** no se configuran *forwarders*. Las consultas a Internet simplemente mueren en el router, lo cual es exactamente el comportamiento deseado.

## El Problema del Onboarding: Hotspot Spoofing
La arquitectura air-gapped tiene una pega evidente y bastante incómoda: los dispositivos del ecosistema cerrado de **Tuya** (en nuestro caso, el enchufe inteligente que mide consumo y el bombillo RGB) **exigen una conexión a Internet durante su emparejamiento inicial**. La aplicación móvil oficial intenta validar el dispositivo contra el *cloud* de Tuya antes de entregarnos la *Local Key*, y si el AP no tiene salida, el proceso falla en seco.

### Solución: Hotspot Spoofing Controlado
La técnica adoptada consiste en **encender temporalmente un hotspot móvil con el mismo SSID y contraseña** que el router air-gapped del ecosistema. El procedimiento, una vez ensayado, queda así:

1. Se levanta el hotspot del teléfono replicando exactamente las credenciales del AP aislado.
2. Se empareja el dispositivo Tuya con la aplicación oficial. El dispositivo "ve" Internet y completa el registro contra el *cloud* de Tuya.
3. Una vez aceptado, se utiliza la herramienta `tinytuya wizard` para descargar la `Local Key` asociada al `device_id`. Estas credenciales son las únicas que necesitaremos a partir de ese momento.
4. Se apaga el hotspot. El dispositivo, ya emparejado, cae automáticamente sobre el AP air-gapped (mismo SSID y password). Como pierde Internet pero conserva una IP local válida, opera en modo LAN.
5. A partir de aquí toda la comunicación se realiza vía `tinytuya` con el protocolo 3.5 directamente contra la IP local del dispositivo, sin pasar nunca más por el *cloud*.

El truco no es elegante, pero es **pragmático y reversible**: nos permite explotar dispositivos comerciales baratos sin renunciar al aislamiento. La `Local Key` queda almacenada únicamente en `firmware/Enchufe/devices.json`, fuera del control de Tuya.

## Sensores Xiaomi: Dos Rutas de Integración

El segundo problema lo plantean los higrómetros/termómetros **Xiaomi LYWSD03MMC**. El firmware original cifra los *advertisements* BLE con la *bind key* de la cuenta Xiaomi, lo cual implica volver a depender de la nube de Xiaomi para registrar el sensor y descifrar las tramas. Además, exige mantener una conexión BLE establecida o usar la app de Mijia para leer los valores.

### Ruta A: Flasheo a Firmware ATC (pvvx)

Se planificó reemplazar el *stock firmware* por el firmware abierto **ATC MiThermometer** (variante `pvvx`), flasheado vía OTA con la herramienta web `TelinkFlasher`. Este firmware:

- Emite *advertisements* BLE **sin cifrar** con un formato documentado, que cualquier scanner puede parsear.
- Trabaja en modo **stateless / connectionless**: la estación de trabajo se limita a escuchar pasivamente con `bleak`, sin necesidad de emparejar ni mantener conexión.
- Permite configurar el intervalo de *advertisement* y exponer batería, temperatura, humedad y *voltage* en cada trama.

### Ruta B: Lectura GATT Directa (descubierta 13/05/2026)

Durante las pruebas de campo se descubrió que el sensor LYWSD03MMC expone la característica **`ebe0ccc1`** dentro del servicio propietario de Xiaomi (`ebe0ccb0`), y que esta característica es **legible sin autenticación previa**. La característica devuelve 5 bytes con temperatura (int16 LE, $\times$100), humedad (uint8) y voltaje de batería (uint16 LE, mV).

Esta ruta, documentada en detalle en la Decisión de Diseño 003 (`003_BLE_Sensor_GATT_Discovery.md`), permite leer los sensores **sin modificar el firmware** y sin depender de la nube de Xiaomi, conectándose puntualmente por GATT desde el servidor.

**Se adopta la Ruta B como método principal de integración**, reservando la Ruta A para escenarios futuros con múltiples sensores simultáneos donde la lectura puramente pasiva (sin conexión GATT) aporte un beneficio tangible.

## Consecuencias Globales
1. **Soberanía del dato verificable:** el router aislado garantiza que ningún paquete pueda salir hacia Internet, independientemente de lo que un dispositivo comercial intente hacer en *background*.
2. **Onboarding documentado y reproducible:** el procedimiento de *hotspot spoofing* queda como parte del manual de despliegue del sistema; cualquier sensor o enchufe Tuya nuevo se incorporará siguiendo los mismos pasos.
3. **Telemetría BLE de bajo coste:** los sensores Xiaomi pasan a comportarse como balizas pasivas. No hay *pairing*, no hay reconexiones, no hay timeouts.
4. **Frontera clara entre "comodidad" y "control":** se asume que el coste de operar fuera del *cloud* del fabricante (perder la app, perder asistentes de voz nativos) es un precio justo por mantener el ecosistema cerrado sobre sí mismo.
5. **Implicación operativa:** el orquestador, al estar en la subred air-gapped, debe acceder a Internet (cuando lo necesite para actualizaciones o para el patrón de delegación descrito en `005_DelegationPattern.md` previo) a través de una segunda interfaz de red conmutada manualmente, no por puente con la red del ecosistema. Esta separación de planos es intencionada.
