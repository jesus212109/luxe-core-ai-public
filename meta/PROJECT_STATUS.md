# Luxe Core AI — Estado del Proyecto (2026-05-30)

## Contexto Académico
- **Autor:** Jesús Fernández López (UCO, Ingeniería Informática)
- **Tutor:** Dr. Rafael Muñoz Salinas
- **TFG:** Ecosistema Avanzado de Edge AI para Domótica Local

## Infraestructura
- **Arquitectura:** 100% Local — Node.js 24 (OpenClaw npm) + Python 3.12 (drivers) + C++20 (ESP32 HVAC)
- **Servidor:** Torre Ryzen (Ubuntu 24.04 LTS, headless)
- **Gateway:** OpenClaw npm v2026.5.27, puerto 18789 (LAN 192.168.1.0/24)
- **Red:** Subred air-gapped `192.168.1.0/24` (router TP-Link sin WAN)
- **Ollama:** localhost:11434 (modelos: qwen3-coder, llama3.2, bge-m3)

## Módulos

| Módulo | Estado | Detalle |
|--------|--------|---------|
| Tuya Smart Plug | ✅ Completo | `server/integrations/tuya_devices.py` — `tinytuya` 3.5 |
| Xiaomi BLE sensor | ✅ Completo | `server/integrations/ble_sensors.py` — GATT `ebe0ccc1` vía ESP32 bridge serial (workaround limitación Realtek) |
| FanLamp F8808 | ✅ Completo | `scripts/fanlamp_control.py` — ESP32 bridge serial (antes bloqueado por Realtek BT). ESP32 ahora también lee sensor Xiaomi vía GATT |
| OpenClaw Orchestrator | ✅ Desplegado | Gateway Node.js, Telegram + web nativos, exec tools |
| ESP32 HVAC Bridge | ❌ Pendiente | `server/integrations/hvac_bridge.py` (stub). ESP32 ocupado con FanLamp + Xiaomi BLE (dual-purpose) |
| LaTeX Memoria | 🔶 Avanzado | Cap. 1–9 redactados, apéndices TODO, ADR-008 añadido |

## Próximos pasos (orden prioridad)
1. Desarrollar firmware ESP32 para HVAC LIN bus (esphome-fujitsu-halcyon, ESP32 ocupado con FanLamp+Xiaomi, requiere compartir roles o dispositivo adicional)
2. DNS persistente: /etc/systemd/resolved.conf.d/dns.conf
3. **(propuesto)** Recuperar historial completo de commits en repo público (~200 commits sanitizados, ver § Public Repo)

## Repositorio público

### Contexto
El repo privado (`luxe-core-ai`, origin GitHub privado) contiene ~200 commits con toda la evolución del proyecto: prototipos, refactors, bugs, experimentos. El repo público (`luxe-core-ai-public`) es un orphan commit sanitizado con un solo commit — el historial completo se perdió por la presencia de credenciales en commits tempranos (Tuya device IDs, WiFi passwords, bot tokens, MACs).

### Riesgo vs beneficio de recuperar la historia

| Beneficio | Riesgo |
|-----------|--------|
| Perfil GitHub más activo (200 commits visibles) | Filtración irreversible de credencial si un commit escapa al sanitizado |
| Muestra evolución real del proyecto (refactors, features, bugs) | Nadie mira realmente el contador de commits de un repo de TFG |
| Los commit messages documentan el proceso de desarrollo | El nombre/email real del autor aparece en commits tempranos |

**Conclusión tentativa:** el riesgo es gestionable con `git filter-repo`, pero el beneficio es marginal. Merece la pena intentarlo en una rama separada para evaluar el resultado sin comprometer el `main` público.

### Implementación propuesta (por hacer, no ejecutada)

```
# 1. Preservar el estado actual del público
git checkout public-main
git branch public-orphan-backup   # backup del orphan commit actual

# 2. Clonar el privado como mirror
git clone --mirror git@github.com:jesus212109/luxe-core-ai.git /tmp/private-mirror
cd /tmp/private-mirror

# 3. Sanitizar con git filter-repo
git filter-repo \
  --path-remove firmware/Enchufe/ \
  --path-remove .env \
  --path-remove .env.example \
  --invert-paths  # opcional si hay más paths que mantener

git filter-repo \
  --replace-text <(cat <<'EOF'
TUYA_DEVICE_ID==>TUYA_DEVICE_ID_PLACEHOLDER
TUYA_LOCAL_KEY==>TUYA_LOCAL_KEY_PLACEHOLDER
BOT_TOKEN==>BOT_TOKEN_PLACEHOLDER
WIFI_PASSWORD==>WIFI_PASSWORD_PLACEHOLDER
192\.168\.1\.100==>192.168.1.X
A1:B3:13:9A:A6:1A==>AA:BB:CC:DD:EE:FF
EOF
)

# 4. Reescribir autor para que solo aparezca el alias de GitHub
git filter-repo --name-callback 'return name.replace(b"Jesús Fernández López", b"jesus212109").replace(b"Jesús", b"jesus212109")'
git filter-repo --email-callback 'return b"jesus212109@users.noreply.github.com"'

# 5. Verificar commit a commit que no hay credenciales
git log --all --format="%H" | while read h; do
  git diff-tree -p $h | grep -cE "<patron-1>|<patron-2>|<patron-3>" && echo "LEAK en $h"
done

# 6. Si todo OK: resetear el público con la historia completa
git remote add public git@github.com:jesus212109/luxe-core-ai-public.git
git push -f public --all
```

### Notas
- **El orden importa:** si algún commit falla la verificación, se descarta la rama y se mantiene el orphan — no hay pérdida.
- **El resultado no es un fork** (no hay parent repo upstream), pero puede presentarse como "versión pública limpia a partir del repositorio de desarrollo privado".
- **La decisión final está sin tomar** — este documento registra el análisis para retomarlo si en el futuro el perfil de GitHub cobra más relevancia profesional.
