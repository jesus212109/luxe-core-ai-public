# 001 - Migración a Arquitectura Edge Local (Soberanía del Dato)

## Contexto del Cambio
Las fases iniciales del proyecto (descritas en `000_Prev_UCO_Remote_Architecture.md`) contemplaban el uso de servidores RTX de la Universidad de Córdoba mediante túneles VPN y proxies SSH. Aunque esto permitió validar modelos complejos, introdujo una fuerte dependencia externa y latencia, violando el principio fundamental de la domótica privada: la **Soberanía del Dato**.

## Decisión Arquitectónica
Se ha decidido migrar la totalidad del proyecto a una arquitectura 100% local (Edge AI), aprovechando el hardware disponible del usuario (Torre Ryzen para orquestación y modelos, y portátil para desarrollo).

### Microservicios en Python (El Cerebro)
- Se desplaza OpenClaw a una ejecución nativa en la red local (`server/`).
- Se integran los agentes directamente con una base de datos local SQLite (`data/luxe_core.db`) para registro de analíticas de confort (ASHRAE 55) y telemetría.
- Integración directa vía Wi-Fi local de dispositivos Tuya (Ventilador, Humidificador) usando `tinytuya`.
- Integración directa vía Bluetooth de sensores Xiaomi usando `bleak`.

### Firmware en C++ (El Músculo)
- El control de la máquina de aire acondicionado por conductos (General/Fujitsu) ya no es simulado o remoto. Se utilizará un puente hardware físico: **ESP32 DevKit V1** programado en C++ (`firmware/`).
- El ESP32 interactuará con un transceptor LIN (LINTTL3) para inyectar y leer tramas en el bus LIN de 3 hilos de la máquina HVAC.

## Consecuencias
1. **Privacidad Total:** Ningún dato sale de la red local.
2. **Baja Latencia:** Las órdenes viajan por la red local al ESP32 sin pasar por servidores universitarios.
3. **Refactorización del Repositorio:** El repositorio se ha dividido estrictamente en `server/` (Python) y `firmware/` (C++). Se eliminaron todos los scripts de proxy y configuración remota.
