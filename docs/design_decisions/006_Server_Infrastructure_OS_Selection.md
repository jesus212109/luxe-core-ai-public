# 006 — Infraestructura de Servidor y Selección del Sistema Operativo

## Contexto del Cambio

El ecosistema Luxe Core AI requiere la ejecución continua de modelos de lenguaje locales (Ollama con `qwen3-coder` en cuantización Q4_K_M, ~8 GB de RAM en inferencia) y del framework orquestador OpenClaw. Durante la fase de desarrollo, estas cargas han coexistido en el portátil del autor junto con las herramientas de ingeniería (Arduino CLI para compilación ESP32, `pandoc`/`pdflatex` para la memoria, editores de código). Esta coexistencia es insostenible en producción por tres razones:

1. **Competencia de recursos:** los picos de inferencia del LLM saturan la RAM y la CPU, degradando tanto la experiencia de desarrollo como la latencia de respuesta del orquestador.
2. **Inestabilidad operativa:** un reinicio del portátil (cambio a Windows, suspensión, actualización del sistema) interrumpe el bucle de control domótico, dejando el hogar sin inteligencia de supervisión.
3. **Movilidad del desarrollador:** el autor necesita libertad para desplazarse con el portátil sin que el sistema domótico deje de funcionar.

La solución pasa por desacoplar físicamente el entorno de desarrollo del entorno de producción mediante un **servidor dedicado**.

## Decisión Arquitectónica

Se despliega un **servidor dedicado** (torre con APU Ryzen y 16 GB de RAM) que aloja de forma exclusiva:

- **Ollama** con los modelos `qwen3-coder` (primario) y `llama3.2` (fallback)
- **OpenClaw** como orquestador agéntico (gateway en puerto 18789)
- **Scripts de control** de los dispositivos IoT (Tuya, BLE, FanLamp)
- **SQLite** para la base de datos de telemetría ASHRAE 55
- **Cockpit** para administración web ligera (puerto 9090)

El portátil conserva exclusivamente las herramientas de desarrollo (Arduino CLI, LaTeX, Git, editores) y se comunica con el servidor mediante SSH con autenticación por llaves RSA. El despliegue de nuevo código se realiza mediante `git pull` desde el repositorio central.

### Topología

```
Portátil (dev)              Servidor (producción)
Fedora/WSL                 Ubuntu Server 24.04 LTS
┌──────────────────┐       ┌─────────────────────────┐
│ VS Code          │  SSH  │ OpenClaw + Ollama       │
│ Arduino CLI      │◄─────►│ Scripts control IoT     │
│ LaTeX            │  RSA  │ SQLite (ASHRAE 55)      │
│ Git              │       │ Cockpit (:9090)         │
│ OpenCode/Claude  │       │ Bluetooth (FanLamp)     │
└──────────────────┘       └─────────────────────────┘
                                    │
                          Red air-gapped 192.168.1.0/24
                          (router TP-Link sin WAN)
```

## Selección del Sistema Operativo: Ubuntu Server 24.04 LTS

El servidor ejecuta **Ubuntu Server 24.04 LTS (Noble Numbat)** en modo _headless_ (sin interfaz gráfica). Los criterios de selección fueron:

1. **Soporte nativo para el ecosistema OpenClaw.** Python 3.11+, Node.js 22, `bluez` (BLE), `systemd` y todas las dependencias del orquestador están empaquetadas y verificadas en los repositorios oficiales de Ubuntu, eliminando la necesidad de compilación desde fuentes o gestores de paquetes auxiliares.

2. **Entorno _headless_ mínimo.** La ausencia de entorno de escritorio libera ~500-800 MB de RAM que se destinan directamente al _inference engine_ de Ollama. Los 16 GB del sistema permiten ejecutar el modelo principal (`qwen3-coder`, ~8 GB en Q4_K_M) con margen para el sistema operativo, la base de datos y los buffers de E/S.

3. **Ciclo de soporte extendido.** Los 5 años de actualizaciones de seguridad (hasta 2029) permiten operar en la red air-gapped con actualizaciones planificadas y controladas, sin presión de migraciones forzosas por fin de vida del sistema operativo.

### Justificación de la Versión: 24.04 LTS frente a 26.04 LTS

En el momento del despliegue coexisten dos versiones LTS: la consolidada **24.04** (abril 2024) y la recién publicada **26.04** (abril 2026). Se opta por la penúltima versión por tres razones técnicas críticas en un entorno sin conectividad permanente a Internet:

1. **Madurez del ecosistema de dependencias.** Ollama, Python, `bluez`/`btmgmt` y `systemd` llevan más de dos años en producción sobre 24.04, con ciclos completos de estabilización de APIs y corrección de errores. La versión 26.04, con semanas de vida, introduce versiones renovadas cuyo comportamiento en entornos air-gapped no ha sido validado por la comunidad.

2. **Disponibilidad de _wheels_ binarios precompilados.** Librerías Python con dependencias nativas (`bleak`, `tinytuya`, `dbus-python`) disponen de ruedas binarias estables para las versiones de Python y GLIBC presentes en 24.04. Ubuntu 26.04 incorpora versiones más recientes de GLIBC que pueden carecer de _wheels_ compatibles, forzando compilación desde fuentes —imposible sin acceso a repositorios externos en la red air-gapped.

3. **Mitigación del riesgo de fallos de juventud.** Los primeros meses de una LTS concentran la mayor densidad de informes de errores críticos. Operar sobre 24.04 —cuyo flujo de correcciones ya está estabilizado— reduce el riesgo de encontrar un fallo en un componente del sistema que, en un entorno air-gapped, requeriría intervención física.

## Alternativas Descartadas

### Linux Mint (XFCE/Cinnamon)

Linux Mint incluye un entorno de escritorio (XFCE o Cinnamon) que consume 400-700 MB de RAM en reposo en servicios gráficos que nunca se utilizan en un servidor gestionado por SSH. Esta memoria, sustraída a los modelos de lenguaje, reduce directamente la calidad de inferencia disponible. Adicionalmente, los paquetes gráficos introducen una superficie de mantenimiento (actualizaciones del _display manager_, configuraciones de compositor) sin valor para el ecosistema.

### CachyOS / Arch Linux (_Rolling Release_)

Las distribuciones _rolling release_ actualizan paquetes de forma continua sin versiones congeladas. En un entorno air-gapped, esto representa un riesgo inaceptable:

- Una actualización del kernel o de `bluez` puede romper la compatibilidad con el adaptador Bluetooth USB que controla el FanLamp.
- Una actualización de Python puede invalidar _wheels_ binarios de bibliotecas críticas (`bleak`, `dbus-python`), cuya resolución exigiría acceso a Internet.
- La ausencia de un punto de restauración estable (sin versiones LTS) significa que cualquier actualización fallida podría requerir reinstalación completa del sistema.

La estabilidad a largo plazo es un requisito no funcional (RNF-04), y las distribuciones _rolling release_ son incompatibles con este requisito por su filosofía de diseño.

## Herramientas de Gestión

### Cockpit (Monitorización Web)

Se despliega Cockpit en el puerto 9090 como interfaz de administración ligera. Fue seleccionado frente a Webmin por su integración nativa con `systemd` y su consumo mínimo en reposo (<50 MB sin sesiones activas). Permite monitorizar servicios (Ollama, OpenClaw, `bluetoothd`), uso de CPU/RAM, y acceder a una terminal web. Está empaquetado en los repositorios oficiales de Ubuntu.

### SSH con Llaves RSA

La comunicación portátil→servidor se realiza mediante SSH con autenticación por par de llaves RSA, permitiendo:

- `scp` / `git pull` para despliegue de nuevo código
- `ssh <servidor> sudo python fanlamp_bt.py off` para control remoto
- Reenvío de puertos para acceder a Cockpit (:9090) y al gateway de OpenClaw (:18789)

### Herramientas de Asistencia de Código

OpenCode y Claude Code se ejecutan nativamente en el servidor, aprovechando su capacidad de cómputo (APU Ryzen, 16 GB RAM). Se controlan remotamente desde el portátil mediante la sesión SSH, combinando la potencia del servidor con la comodidad del entorno de desarrollo.

## Consecuencias

1. **El servidor opera 24/7 independientemente del portátil.** El ecosistema domótico no se interrumpe cuando el autor está fuera de casa o usando Windows.
2. **Los 16 GB de RAM se dedican íntegramente a la inferencia.** Sin entorno gráfico ni herramientas de desarrollo compitiendo, el LLM dispone de ~12 GB efectivos para el modelo y el _context window_.
3. **Ubuntu Server 24.04 LTS proporciona estabilidad predecible.** Sin sorpresas de actualizaciones _rolling_ ni roturas de dependencias, el mantenimiento del servidor se reduce a _patches_ de seguridad planificados.
4. **La arquitectura de dos nodos es escalable.** En el futuro, el servidor puede ampliarse con GPU dedicada para inferencia sin afectar al flujo de desarrollo.
