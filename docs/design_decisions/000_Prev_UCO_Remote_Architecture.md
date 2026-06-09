# Decision 001: Hybrid Environment (Conda + uv)
**Fecha:** 2026-04-21
**Contexto:** Necesidad de aislar binarios de C++ y paquetes de Python en una partición con cuota de disco alta (/opt3).
**Decisión:** Usar Conda para el toolchain de C++ (gcc/cmake) y 'uv' para la resolución ultrarrápida de dependencias de Python.
**Consecuencia:** Entorno reproducible, ejecución remota eficiente y cumplimiento de las restricciones de espacio del servidor de la UCO.


# Decision 002: Identidad Corporativa EPSC y Estética Documental
**Fecha:** 2026-04-21
**Contexto:** Necesidad de alinear la memoria del TFG con el Manual de Identidad Corporativa de la Escuela Politécnica Superior de Córdoba (EPSC) y la Universidad de Córdoba (UCO), asegurando un acabado profesional, moderno y normativo.

## Decisiones Técnicas y Estéticas

1. **Paleta de Colores Oficiales (EPSC)**:
   Se han desterrado los colores genéricos en favor de los valores hexadecimales oficiales de la escuela, inyectados globalmente en LaTeX vía el paquete `xcolor`:
   - `EPSCDark` (`#280091`): Usado para títulos de capítulo, nombre del proyecto en portada y textos de jerarquía principal.
   - `EPSCMedium` (`#4C5CC5`): Usado para subtítulos, enlaces interactivos y líneas separadoras de cabecera.
   - `EPSCLight` (`#3FCFD5`) y `EPSCGreen` (`#00B299`): Reservados para énfasis en tablas, diagramas y figuras futuras.

2. **Diseño de Portada y Zonas de Protección**:
   - Se ha descartado el comando estándar `\maketitle` para construir un entorno `titlepage` personalizado mediante `TikZ`.
   - **Esquinas Geométricas**: Se utilizan los recursos corporativos `topRightCorner.pdf` y `bottomLeftCorner.pdf` posicionados de forma absoluta en el documento (`remember picture, overlay`).
   - **Logotipos**:
     - El **Logo de la EPSC** (`logo_epsc.pdf`) se ubica estrictamente en la esquina superior derecha. Se le ha aplicado un desplazamiento (`xshift=-1.5cm, yshift=-5cm`) para evitar solapamientos con el gráfico de la esquina y respetar su zona de respiro visual. Formato vectorial exigido para mantener máxima resolución en la impresión.
     - El **Logo de la UCO** (`logo_uco.pdf`) se ubica en la esquina inferior derecha (`xshift=-1.5cm, yshift=2cm`).
   - **Tipografía y Jerarquía**: Uso de tipografía en versalitas (`\scshape`) para los nombres de las instituciones, y delimitadores horizontales (`\rule`) para enmarcar el título oficial del proyecto (*Ecosistema Avanzado de Edge AI para Domótica Local*), reservando la marca *Luxe Core AI* para fases comerciales posteriores ajenas a la memoria académica.

3. **Tipografía Global**:
   - Fuente principal: **Libertine**. Proporciona un equilibrio excelente entre la elegancia de una fuente con serifa clásica y una lectura ágil en pantalla e impresión.
   - Microtipografía: Activación del paquete `microtype` para un justificado óptico superior sin *overfull hboxes*.

**Consecuencia:** El documento `main.pdf` cumple rigurosamente con la normativa visual para su entrega en secretaría, albergando una presencia estética de alto nivel que respalda la calidad técnica del *software* desarrollado.


# Luxe Core AI - Bitácora de Decisiones de Diseño

## Fecha: 22 de Abril de 2026

### FASE 1 & 2: Higiene del Entorno y Dependencias
* **Aislamiento de HOME y Protección de Cuota:** 
  Se identificó que los módulos de Node (`.npm`) y la caché y configuración de OpenClaw (`.openclaw`) estaban escribiendo directamente en `/home/i22ferlj/`, saturando la cuota asignada. Se movieron hacia la partición aislada `/opt3/data/i22ferlj/` y se generaron enlaces simbólicos (symlinks). Esto mantiene la operatividad de los binarios mientras asegura que todo consumo de disco recaiga sobre `/opt3`.
* **Corrección de Rutas Locales (NPM):** 
  La dependencia `@larksuiteoapi/node-sdk` provocaba fallos por permisos globales. Se resolvió forzando un `prefix` en `.npmrc` hacia `/opt3/data/i22ferlj/.npm-global`.

### FASE 3: Despliegue IA Local (OpenClaw) y Configuración de Modelos
* **Soberanía Computacional:** Se desactivaron los plugins nativos `feishu` y `google` para garantizar que no existan fugas de datos hacia ecosistemas cloud no autorizados.
* **Modelo Principal (Qwen3-Coder):**
  * Se corrigió el endpoint del orquestador, apuntando explícitamente a Ollama (`ollama/qwen3-coder`) en lugar del endpoint de nube (`openai/`).
  * **Verificación de Cuantización:** Se confirmó mediante `ollama show` que el modelo local de 30.5B parámetros está cuantizado en formato **Q4_K_M** (4-bits) ocupando 18GB en memoria, logrando el equilibrio perfecto entre precisión y viabilidad de inferencia Edge en servidor local.
* **Sistema de Delegación (Fallback / Dual):** 
  Se añadió `ollama/llama3.2` (modelo de ~3B) como modelo de *fallback/dual* en la configuración de agentes. Esto permite rutear de forma dinámica operaciones de razonamiento menores, evitando saturar la memoria VRAM y manteniendo al Qwen reservado para tareas de lógica de software complejas.
* **Espacio Latente (Embeddings):** 
  Se designó el modelo **bge-m3** sirviendo desde Ollama como motor para vectorización y RAG local.

### FASE 4: Capacidades Adicionales
* **Acceso Controlado a la Web:**
  Se ha asegurado la disponibilidad del plugin **`browser`** (`@openclaw/browser`) que actúa como herramienta de consulta on-demand. El LLM puede decidir de forma autónoma utilizarlo para inyectar contexto fresco (buscar APIs nuevas, información de la fecha o documentación) cuando el contexto local no le resulte suficiente, sin comprometer el control del entorno.
* **Ejecución y Monitoreo:**
  El proceso Gateway de OpenClaw se encuentra ejecutándose como servicio interno (demonio local) de forma sana y controlada, empleando `gateway.mode=local`.


# 004_SandboxAndSkills.md

## Diseño y decisiones de los nuevos módulos del proyecto Open Claw

### 1️⃣ `ephemeral_sandbox.py`

- **Objetivo**: Proveer un entorno de ejecución **stateless** y limitado en red para scripts de calibración de hardware IoT desde el nodo central (Qwen3).
- **Detección de VLAN**: Se lee `/proc/net/route` para obtener la IP del gateway por defecto y se realiza una petición HTTP ligera a `http://<gateway>/api/vlan`.  Si la respuesta incluye `{ "supported": true }` se considera que el router soporta VLAN y se habilita la gestión dinámica.  De lo contrario se activa una restricción por software basada en la variable de entorno `PROVISION_IP_RANGE`.
- **Restricción por software**: Cuando no hay VLAN, el sandbox solo permite conexiones a direcciones dentro del CIDR de aprovisionamiento (`192.168.0.0/24` por defecto).  Se verifica cooperativamente mediante líneas especiales de registro (`[CONNECT] <host>`).  En un entorno de producción se podría reemplazar por reglas `iptables`/`nftables`.
- **Timeout estricto**: `subprocess.run(..., timeout=self.timeout_seconds)` con valor por defecto de 30 s.  Un `RuntimeError` se lanza si se supera.
- **Zero‑Trust**: La clase construye un entorno de ejecución minimalista (solo variables `PATH`, `HOME`, `LANG`, `LC_ALL`).  No persiste archivos ni caches y el proceso hijo termina después de la llamada.
- **Uso**: `sandbox = EphemeralSandbox(); rc, out, err = sandbox.run_script('calibrate.py')`.

### 2️⃣ `gemini_search_tool.py`

- **Objetivo**: Encapsular la **API Gemini** como una herramienta de búsqueda externa disponible para el nodo central.
- **Diseño**: Clase `GeminiSearchTool` sin estado; cada llamada a `search(query)` construye una petición `POST` a `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent` con la clave `GEMINI_API_KEY` leída del entorno.
- **Respuesta estructurada**: Se devuelve un diccionario JSON con dos claves: `query` y `results`. Cada resultado contiene `title` y `snippet`, facilitando que Qwen3 analice la información sin parsing avanzado.
- **Manejo de errores**: `RuntimeError` para errores de red, códigos HTTP != 200 y JSON malformado.  Los callers pueden capturarlos y decidir cómo proceder.
- **Seguridad**: No se ejecuta código arbitrario; solo se realiza I/O de red controlada.

### 3️⃣ `community_skill_loader.py`

- **Objetivo**: Permitir la **carga dinámica** de skills de la comunidad de forma segura (Zero‑Trust).
- **Manifest de confianza**: Un archivo JSON (`trusted_skills.json`) mapea URLs exactas a **checksum SHA‑256**. Sólo las URLs presentes son aceptadas.
- **Descarga & verificación**:
  1. Se descarga el archivo a un directorio cache `.skill_cache` bajo el repositorio.
  2. Se calcula su SHA‑256 y se compara con el valor del manifest.
  3. Si coincide, se importa con `importlib.util` en un `ModuleType` aislado.
- **Restricciones de API**:
  - El módulo debe exponer una función `run(**params)` callable.
  - Se asegura que exista una docstring; si falta, se inserta un placeholder.
- **Inyección en Qwen3**: El docstring extraído (`module.__doc__`) puede enviarse al modelo para que conozca la capacidad de la skill sin ejecutar código.
- **Sin reinicio**: El loader devuelve el módulo ya importado; el backend puede usarlo inmediatamente.
- **Ejemplo de uso**:
  ```python
  loader = CommunitySkillLoader('config/trusted_skills.json')
  skill = loader.load('https://example.com/skills/temp_monitor.py')
  result = skill.run({'sensor_id': 5})
  ```

---

### Principios de **Zero‑Trust** aplicados
1. **Verificación de origen** mediante checksums firmados.
2. **Entorno limitado** (sandbox, timeout, variables de entorno).
3. **Sin estado**: cada ejecución es independiente; se borran caches temporales.
4. **Minimización de dependencias**: solo librerías estándar de Python.
5. **Auditoría**: logs de eventos críticos (detected gateway, VLAN support, checksum mismatches) pueden ser dirigidos a un logger externo.

### Próximos pasos recomendados
- Añadir reglas `iptables` en producción para reforzar la restricción de IP cuando no hay VLAN.
- Integrar el `GeminiSearchTool` como **skill** dentro de OpenClaw (registro en `openclaw.skills`).
- Mantener el manifest `trusted_skills.json` bajo control de versiones y revisiones de seguridad.


# 005_DelegationPattern.md

## Patrón de Delegación de Herramienta Agentic (Agentic Tool Delegation)

### Contexto y Problema

El sistema Open Claw se despliega en el Centro de Datos de la UCO (Universidad
de Córdoba). Este entorno tiene **salida a internet restringida** por política
institucional: permite descargar paquetes (pip/conda/npm) y modelos (Ollama),
pero **bloquea las llamadas API salientes a servicios externos** como Gemini.

La Tarea 2 del MVP requiere que el Nodo Central (Qwen3) pueda buscar
información en internet a través de Gemini. Esta necesidad colisiona
directamente con la restricción de red del servidor.

---

### Solución: Delegación Transparente de Herramienta

En lugar de forzar la apertura de puertos en el servidor (inviable sin
permisos de administración), se implementa un **patrón de delegación**
donde las llamadas costosas en red se desplazan al cliente que ya tiene
conectividad.

```
┌──────────────────────────────────────┐
│         SERVIDOR UCO (sin internet)  │
│                                      │
│  Qwen3 ──► GeminiSearchTool.search() │
│                │                     │
│                ▼                     │
│         [modo=delegate]              │
│         Emite marcador en stdout:    │
│  ###DELEGATE###{"query":"..."}###END###│
└─────────────────┬────────────────────┘
                  │  SSH / pipe / TCP
                  ▼
┌──────────────────────────────────────┐
│     MÁQUINA LOCAL (con internet)     │
│                                      │
│  gemini_proxy_client.py              │
│         │                            │
│         ├─ Detecta ###DELEGATE###    │
│         ├─ Llama a Gemini API  ──────┼──► api.google.com
│         └─ Devuelve DELEGATE_RESPONSE│
└──────────────────────────────────────┘
```

---

### Ficheros implementados

| Fichero | Ubicación | Descripción |
|---------|-----------|-------------|
| `gemini_search_tool.py` | `python/` | Módulo del servidor. Auto-detecta modo. |
| `gemini_proxy_client.py` | `python/` | Script para ejecutar **en local**. |

---

### Modos de Operación de `gemini_search_tool.py`

#### 1. `DIRECT` (servidor con internet)
El módulo llama directamente a la API de Gemini.  
Se activa si el probe TCP a `generativelanguage.googleapis.com:443` tiene éxito en **2 segundos**.

#### 2. `DELEGATE` (servidor sin internet — caso UCO)
El módulo **emite un bloque especial en `stdout`** con el formato:
```
###DELEGATE###{"type":"DELEGATE_REQUEST","tool":"gemini_search","query":"..."}###END###
```
El cliente-proxy detecta este marcador, ejecuta la llamada a Gemini
localmente y devuelve la respuesta como:
```
###DELEGATE_RESPONSE###{"type":"DELEGATE_RESPONSE","query":"...","results":[...]}###END###
```

#### 3. `OFFLINE` (sin red y sin cliente)
Devuelve resultados vacíos de forma estructurada para no romper el flujo
de agentes. El sistema continúa operando con la información que ya tiene.

#### Forzar un modo
```bash
export GEMINI_MODE=delegate   # delegate | direct | offline
```

---

### Transporte: Modos del Cliente-Proxy

#### Modo `pipe` (más sencillo para el TFG)
```bash
# En tu terminal local:
export GEMINI_API_KEY="tu_clave_gemini"

ssh i22ferlj@servidor.uco.es \
  "conda run -n openclaw_hybrid python3 /opt3/data/i22ferlj/luxe-core-ai/python/mi_backend.py" \
  | python3 /opt3/data/i22ferlj/luxe-core-ai/python/gemini_proxy_client.py --mode pipe
```
Ventajas: **cero configuración de red extra**, funciona sobre SSH estándar.  
Desventajas: requiere que el backend imprima sus datos a `stdout`.

#### Modo `socket` (para demonio siempre activo)
```bash
# En local (escucha TCP en el puerto 9876):
python3 gemini_proxy_client.py --mode socket --port 9876

# En el servidor, abrir un túnel SSH inverso:
ssh -R 9876:localhost:9876 i22ferlj@servidor.uco.es
```
El backend del servidor se conecta a `localhost:9876` (que en realidad
es el túnel SSH hacia tu máquina) para enviar/recibir la delegación.

---

### Seguridad (Zero-Trust)

| Riesgo | Mitigación |
|--------|-----------|
| Inyección de payload malicioso por el servidor | El cliente solo procesa bloques `DELEGATE_REQUEST` con estructura validada; campos inesperados se ignoran. |
| Exfiltración de datos vía delegación | El proxy solo envía el campo `query` (cadena de texto) a Gemini; nunca datos sensibles del entorno del servidor. |
| Intercepción del canal SSH | El tráfico viaja sobre SSH (cifrado). En producción se puede añadir firma HMAC al bloque JSON. |
| Bucle infinito de delegaciones | El proxy no acepta `DELEGATE_REQUEST` que contengan a su vez marcadores de delegación. |

---

### Impacto en el MVP del TFG

**Funcionalidades preservadas:**
- ✅ `ephemeral_sandbox.py` — 100% local, no requiere internet.
- ✅ `community_skill_loader.py` — las skills se suben al servidor manualmente; el loader no necesita internet en caliente.
- ✅ `gemini_search_tool.py` — funciona en modo delegación a través del canal SSH existente.

**Lo que cambia respecto al diseño original:**
- El desarrollador debe tener el `gemini_proxy_client.py` corriendo en su
  máquina cuando el sistema necesite buscar información externa.
- En la **defensa del TFG**, esto se puede presentar como una virtud
  arquitectónica: el servidor nunca habla directamente con internet,
  toda la información externa pasa por el nodo controlado por el
  desarrollador → principio de "acceso mínimo y supervisado".

---

### Próximos pasos recomendados

1. **Añadir firma HMAC** al bloque de delegación para verificar la integridad
   del canal (evita ataques de suplantación si el SSH se compromete).
2. **Modo WebSocket** como tercer transporte para permitir comunicación
   bidireccional persistente sin re-establecer el túnel SSH.
3. **Cache de respuestas** en el proxy para no repetir llamadas idénticas
   a Gemini en la misma sesión (ahorra cuota de API).


# 006_TelegramAndEdgeTerminals.md

## Canal Telegram y Arquitectura de Terminales Edge Domóticos

### Contexto

El sistema Open Claw necesita una interfaz de usuario accesible desde cualquier
lugar. Al mismo tiempo, debe ser capaz de enviar comandos a hardware IoT
(ESP32) ubicado en el domicilio del usuario, mientras el procesamiento pesado
ocurre en el servidor de la UCO.

Esta decisión de diseño documenta cómo se integra el canal de Telegram y cómo
el nodo proxy-client evoluciona a **Terminal Edge** completo.

---

### Arquitectura Completa del Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SERVIDOR UCO (sin internet)                        │
│                                                                         │
│   Llama 3.2 (Edge)   →   Qwen3 (Core)   →   Genera comando/respuesta   │
│                                                     │                   │
│               recibe petición del usuario           │                   │
└─────────────────────────────┬───────────────────────┼───────────────────┘
                              │ SSH tunnel             │
                              │ (bidireccional)        │
┌─────────────────────────────▼───────────────────────▼───────────────────┐
│                    NODO EDGE LOCAL (tu casa / RPi / PC)                 │
│                                                                         │
│  telegram_channel.py   ←→   gemini_proxy_client.py                      │
│        │                           │                                    │
│        │ Bot API                   │ Gemini API                         │
│        ▼                           ▼                                    │
│   Telegram ←────────────────── Internet                                 │
│        │                                                                │
│        │ MQTT / HTTP local                                               │
│        ▼                                                                │
│   ESP32 / Sensores / Actuadores (red LAN doméstica)                     │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  💡 LED · 🌡️ Sensor · 🔌 Enchufe inteligente · etc.
```

---

### Protocolo de Comandos de Actuador

Cuando Qwen3 decide ejecutar una acción física, emite un bloque especial
en su salida (análogo al bloque de delegación Gemini):

```
###ACTUATOR###{"device":"led_sala","action":"brightness","value":50,"protocol":"http","endpoint":"http://192.168.1.100/led","chat_id":123456}###END###
```

El nodo Edge intercepta este bloque, ejecuta la petición HTTP/MQTT al ESP32
y notifica al usuario en Telegram.

**Campos del comando de actuador:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `device` | string | Nombre descriptivo del dispositivo |
| `action` | string | Tipo de acción (`brightness`, `toggle`, `setTemp`, …) |
| `value` | any | Valor a aplicar |
| `protocol` | string | `http` (REST) o `mqtt` (futuro) |
| `endpoint` | string | URL o topic del dispositivo |
| `chat_id` | int | Chat de Telegram al que devolver la confirmación |

---

### Configuración del Bot de Telegram (paso a paso)

> **No se necesita número de teléfono.** Solo la cuenta de Telegram.

1. Abre Telegram → busca `@BotFather` → `/newbot`
2. Elige nombre y usuario para el bot (ej: `OpenClawBot`)
3. Copia el token: `123456789:AAF...`
4. Define la variable de entorno:
   ```bash
   export TELEGRAM_BOT_TOKEN="123456789:AAF..."
   ```
5. Descubre tu `chat_id`:
   ```bash
   python3 python/telegram_channel.py --setup
   # Envía cualquier mensaje al bot → aparecerá tu chat_id
   ```
6. Lanza el canal con tu ID autorizado:
   ```bash
   export GEMINI_API_KEY="tu_clave"
   python3 python/telegram_channel.py --allowed TU_CHAT_ID
   ```

---

### Seguridad del Canal Telegram

| Riesgo | Mitigación implementada |
|--------|------------------------|
| Cualquier usuario puede controlar el sistema | `TELEGRAM_ALLOWED_CHAT_IDS` filtra en la primera capa |
| Inyección de comandos vía texto de Telegram | El texto se envuelve en JSON con `source: telegram`; el servidor nunca ejecuta texto crudo |
| Comandos a actuadores con IPs arbitrarias | El campo `endpoint` solo debería aceptar IPs del rango LAN (`192.168.x.x`); validación a añadir en v2 |
| MITM en el canal SSH | Tráfico cifrado por SSH. Se puede reforzar con `StrictHostKeyChecking=yes` |

---

### ¿Esto responde a la pregunta "¿hay límite físico?"

**No.** El patrón proxy-client/Edge es extensible a cualquier canal:

| Canal | Estado |
|-------|--------|
| Gemini Search | ✅ Implementado |
| Telegram | ✅ Implementado |
| Actuadores ESP32 (HTTP) | ✅ Implementado (simulación) |
| WhatsApp | ⚠️ Limitación de ToS de Meta, no arquitectónica |
| MQTT real | 🔜 Próxima iteración |
| Notificaciones push (app móvil) | 🔜 Futuro (Firebase o Pushover) |

El servidor UCO **siempre recibe y procesa peticiones** — nunca inicia
conexiones salientes. El nodo Edge es quien tiene los canales activos.
Esto es **exactamente** la arquitectura Edge-Core del TFG.

---

### Flujo de ejemplo: "Pon la luz LED al 50%"

```
1. Usuario escribe en Telegram: "Pon la luz LED al 50%"
2. telegram_channel.py recibe el mensaje (chat_id: XXXX)
3. Lo envuelve: {"source":"telegram","chat_id":XXXX,"text":"Pon la luz LED al 50%"}
4. Lo inyecta al SSH tunnel → Servidor UCO
5. Llama 3.2 (Edge) clasifica la intención: [DOMOTICA_LED]
6. Qwen3 (Core) genera el comando:
   ###ACTUATOR###{"device":"led_sala","action":"brightness","value":50,
                  "protocol":"http","endpoint":"http://192.168.1.100/led",
                  "chat_id":XXXX}###END###
7. telegram_channel.py intercepta el bloque ACTUATOR
8. Hace POST a http://192.168.1.100/led con {action:"brightness",value:50}
9. ESP32 recibe y aplica el cambio de brillo
10. Telegram responde: "✅ Comando enviado a led_sala: brightness = 50"
```

---

### Próximos pasos

1. Añadir validación de rango de IP en los comandos de actuador (LAN only).
2. Implementar soporte MQTT con `paho-mqtt` en el nodo Edge.
3. Añadir un hilo separado en `TelegramChannel.run()` para leer el servidor
   de forma no-bloqueante (modelo productor-consumidor).
4. Crear un `device_registry.json` con el mapa de dispositivos disponibles
   para que Qwen3 conozca qué hardware existe en cada ubicación.


# 007_OpenClawDeployment.md

## Despliegue del Gateway OpenClaw y Resolución de Dependencias de Runtime

### Contexto
Para el TFG, es necesario acceder a la interfaz web (Dashboard) de OpenClaw para gestionar agentes y visualizar el estado del sistema. Sin embargo, el entorno del servidor de la UCO presenta restricciones de versión de Node.js y limitaciones de red (firewall).

---

### Desafíos y Soluciones

#### 1. Versión de Node.js (v22+)
**Problema:** OpenClaw requiere Node.js v22.12+, pero la versión por defecto del sistema es la v18.19.
**Solución:** Se utiliza el binario de Node.js v22 empaquetado dentro del entorno Conda `openclaw_hybrid` (`/opt3/data/i22ferlj/miniconda3/envs/openclaw_hybrid/bin/node`). 
**Ejecución:** Se antepone el uso de `conda run -n openclaw_hybrid` para asegurar que el path de Node sea el correcto.

#### 2. Proveedor Ollama (Autenticación Local)
**Problema:** El gateway no registraba los modelos de Ollama (`qwen3-coder`, `llama3.2`) a pesar de estar instalados, lanzando errores de "Unknown model".
**Solución:** Se define la variable de entorno `OLLAMA_API_KEY="ollama-local"`. OpenClaw requiere cualquier valor en esta variable para activar el driver de Ollama como proveedor de modelos.

#### 3. Persistencia del Proceso
**Problema:** Al ejecutar el gateway en primer plano, el proceso moría al cerrar la terminal o recibir señales de interrupción de sesiones inactivas.
**Solución:** Se despliega en segundo plano mediante `nohup` y se desvincula de la entrada estándar:
```bash
nohup conda run -n openclaw_hybrid env OLLAMA_API_KEY="ollama-local" openclaw gateway > /tmp/openclaw_gateway_run.log 2>&1 &
```

#### 4. Acceso Remoto Seguro (SSH Tunneling)
**Problema:** Por seguridad, el gateway escucha solo en `127.0.0.1:18789` (loopback). El servidor no tiene puertos abiertos al exterior.
**Solución:** Se utiliza un túnel SSH inverso (Port Forwarding) para mapear el puerto del servidor al equipo local del usuario.
**Comando:** `ssh -L 18789:127.0.0.1:18789 i22ferlj@a6000ada.uco.es`

---

### Detalles Técnicos del Gateway
- **Puerto:** 18789
- **Protocolo:** HTTP / WebSocket (ws)
- **Token de Auth:** `86b3b59f7adc6304e72777b35f16bf29d7569f6d03e20e22`
- **Logs de ejecución:** `/tmp/openclaw_gateway_run.log`

---

### Próximos Pasos
- Automatizar el arranque del gateway dentro del script `scripts/start_client.sh` para que se levante automáticamente al iniciar el nodo Edge.
- Configurar el `gateway.mode` en el archivo JSON para permitir conexiones de red locales (`0.0.0.0`) si se despliega en una Raspberry Pi doméstica.
