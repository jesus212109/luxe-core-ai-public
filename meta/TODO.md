## Plan de validación — 2026-05-13

### 0. Comprobaciones previas ✅
- python → /usr/bin/python (3.14.4)
- tinytuya 1.18.0 ✅
- bleak 3.0.2 ✅
- Bluetooth hci0 presente ✅
- Red air-gapped: 192.168.1.101, enchufe 192.168.1.100 responde ✅
- Smoke tests (py_compile, import, --help): ✅ los 3 pasan

### 1. Tuya Smart Plug ✅ COMPLETO
- Alterna ON/OFF correctamente. El relé clica.
- La Local Key es válida.

### 2. FanLamp Pro BLE ❌ BLOQUEADO
- Dispositivo visible como "C21-61A" (A1:B3:13:9A:A6:1A).
- La conexión falla durante service discovery.
- bluetoothctl pair → `org.bluez.Error.AuthenticationFailed`
- **Causa:** el FanLamp requiere bonding con clave. Probablemente
  está vinculado en exclusiva a la app del fabricante.
- **Posible solución:** reset de fábrica + pairing fresco desde
  nuestro lado, o sniffing BLE de la app oficial para capturar la
  clave de enlace.

### 3. Xiaomi LYWSD03MMC ❓ PENDIENTE
- Visible en scan (A4:C1:38:84:03:1C, RSSI -50).
- Service data en UUID 0xFE95 con 12 bytes.
- **Sin manufacturer data** → parece firmware STOCK (no ATC).
- Conexión GATT: timeout en service discovery.
- **Posible solución:** flashear firmware ATC de pvvx, o extraer
  bind key de Mi Home para descifrar los advertisements.

### 4. Integración completa (golden path)
- Tuya: ✅
- BLE (FanLamp + Xiaomi): ❌ ambos requieren intervención manual
  (pairing / flash de firmware) antes de poder validar.

## Bugs encontrados y corregidos (sesión 2026-05-13)

### `fan_investigation.py`
1. **`--verbose` sin help text:** `add_argument("--verbose", "-v")`
   no tenía `help=`. Corregido con
   `help="Enable debug logging"`.

2. **FanLamp desconexión prematura:** el dispositivo tarda ~3s en
   establecer la conexión BLE pero tiene un supervision timeout muy
   corto (~<2s). Añadido `await asyncio.sleep(2.0)` tras conectar
   para dar tiempo a BlueZ a estabilizar. (Nota: esto palia el
   problema en condiciones ideales, pero el verdadero bloqueo es el
   bonding.)

### bleak 3.0.2 API changes
- `BLEDevice` ya no tiene atributo `.rssi` directo. En 3.x está en
  `device.details['props']['RSSI']`.
- `BleakScanner.discover()` sin `return_adv=True` solo devuelve
  `list[BLEDevice]`. Con `return_adv=True` devuelve
  `dict[str, tuple[BLEDevice, AdvertisementData]]`.

## Notas operativas (preservadas del original)
- No comites credenciales: si regeneras Local Key, actualiza
  `tuya_devices.py` y `firmware/Enchufe/devices.json` juntos.
- Air-gap real: verifica que la NIC del SSID aislado no sea ruta
  por defecto a Internet (`ip route`).
---

## FanLamp — bloqueo confirmado (16 mayo 2026)

El ESP32 se conecta al FanLamp real como BLE central y descubre todos sus servicios:
- **FEA1** (0xFEE7): read + notify — emite estado `07 60 11 00 1B 0D 00 C8 0D 03` (10 bytes)
- **FEC9** (0xFEE7): read — devuelve MAC `A1:B3:13:9A:A6:1A`
- **6487** (0x6287): write + notify — posible entrada de comandos
- **FF02** (0x01FF): write — posible entrada de comandos
- **FFF2** (0xD0FF): write — posible entrada de comandos

Se probaron >40 combinaciones de writes (hex, binario, MAC, secuencias)
en los 3 targets durante ventanas de pairing y en estado normal.
Ninguna produjo cambio de estado ni respuesta del ventilador.

**Conclusión:** el protocolo Tencent usa tramas estructuradas con formato
propietario (posiblemente CRC/cifrado). No es adivinable por fuerza bruta.

**Solución:** se necesita un sniffer BLE dedicado para capturar el tráfico
entre la app FanLamp Pro y el ventilador durante el pairing.

### Requisitos del sniffer BLE

Dispositivo: **nRF52840 Dongle** (o compatible)
- Chip: Nordic nRF52840
- Interfaz: USB-A
- Precio: ~8-12€ en AliExpress
- Firmware: nRF Sniffer for Bluetooth LE (gratuito, de Nordic Semi)
- Software: Wireshark + plugin nRF Sniffer (Linux, gratuito)

Búsqueda en AliExpress: "nRF52840 dongle" o "nRF52840 USB"
Modelos válidos: Nordic nRF52840 Dongle (PCA10059), MakerDiary nRF52840 MDK USB,
Waveshare nRF52840, o cualquier genérico con chip nRF52840.

Con esto, Wireshark captura el 100% del tráfico BLE aéreo entre el teléfono
y el ventilador durante el pairing, incluyendo el handshake Tencent completo.
