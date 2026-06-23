# Firmware — Luxe Core AI

## esp32_fanlamp/
Firmware para el ESP32 DevKit V1. Actúa como puente BLE para controlar el ventilador FanLamp F8808 y como lector de sensores Xiaomi LYWSD03MMC.

**Nota sobre datos omitidos:** Los arrays de bytes que codifican los comandos BLE del ventilador FanLamp se han omitido de esta versión pública por tratarse de protocolo propietario obtenido mediante ingeniería inversa. El fichero `main.ino` contiene la estructura del firmware y la documentación del protocolo, pero sin los valores concretos de los anuncios BLE.

## Enchufe/ (omitido en esta versión pública)
El directorio `firmware/Enchufe/` se ha omitido porque contenía las *Local Keys* de dispositivos Tuya. Para configurar tu propio dispositivo, consulta `.env.example` en la raíz del proyecto y la documentación en la memoria.

Consulta `docs/PUBLIC_RELEASE_NOTES.md` para más detalles.
