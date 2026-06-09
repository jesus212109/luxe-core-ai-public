# 007 — Despliegue de Red y Contingencia de Conectividad

## Contexto del Cambio

El despliegue del servidor Ubuntu Server 24.04 LTS en la red air-gapped del ecosistema Luxe Core AI enfrentó dos obstáculos de infraestructura durante la puesta en marcha inicial. El router TP-Link TL-MR6400 —cedido temporalmente, con ranura SIM rota— opera exclusivamente como switch local y punto de acceso WLAN en el segmento `192.168.1.0/24`, sin conectividad WAN. La instalación mínima de Ubuntu Server carece de las herramientas de red necesarias para configurar interfaces inalámbricas (`wpasupplicant`) y de editores de texto para modificar archivos de configuración. Ambos factores exigieron soluciones de ingeniería de redes ad-hoc, documentadas como decisiones de diseño de infraestructura.

## Decisión 1: Diagnóstico y Corrección del Puerto LAN/WAN Híbrido

### Problema

Al interconectar la torre servidor mediante cable Ethernet al router TP-Link, el portátil de desarrollo (conectado vía Wi-Fi al mismo router) devolvía un error de enrutamiento al intentar establecer una sesión SSH:

```
ssh jesus@192.168.1.50
ssh: connect to host 192.168.1.50 port 22: No route to host
```

El comando `arp -a` no mostraba entrada para `192.168.1.50`. El mapa de red del firmware del router indicaba `Wired Clients: 0`.

### Diagnóstico

El cable Ethernet del servidor se había conectado al puerto híbrido **LAN/WAN** del TL-MR6400. Este puerto, diseñado para operar indistintamente como puerto de red local o como interfaz de conexión a un módem externo, es gestionado por la lógica interna del router de la siguiente forma:

1. Al no detectar una tarjeta SIM activa en la ranura (ranura rota), el firmware del router desactiva la funcionalidad de puente de red (*bridge*) en el puerto LAN/WAN, priorizando la búsqueda de una línea WAN externa.
2. Esta desactivación aísla eléctricamente la interfaz física del servidor (`enp3s0`) del segmento inalámbrico (WLAN), impidiendo el intercambio de tramas a nivel de Capa 2 (Enlace de Datos, modelo OSI).

### Solución

Se migró el enlace físico del servidor desde el puerto LAN/WAN híbrido a un **puerto LAN dedicado** del router. Al tratarse de un puerto exclusivamente conmutado, el *switch* interno del TL-MR6400 restablece inmediatamente el intercambio de tramas Ethernet a nivel de Capa 2 entre todos los dispositivos conectados. El comando `arp -a` confirmó la presencia de `192.168.1.50` con la MAC del servidor, y la sesión SSH se estableció correctamente.

## Decisión 2: Pasarela de Red Local de Contingencia (NAT + iptables)

### Problema

La instalación mínima de Ubuntu Server 24.04 LTS carece de:

- Herramientas de edición de texto (ni `nano`, ni `vim-tiny` en la imagen mínima)
- El demonio `wpasupplicant` necesario para gestionar la antena Wi-Fi USB (`wlx803f5d225955`)
- Cualquier paquete del *stack* de desarrollo del proyecto (Python, Git, Node.js)

Sin conectividad a Internet en el segmento de red y sin capacidad de instalar paquetes *offline*, el servidor no podía configurarse para ejecutar el ecosistema.

### Solución: Portátil como Gateway NAT con Tethering USB

Se implementó una arquitectura de enrutamiento de contingencia utilizando el portátil de desarrollo como **pasarela de red de Capa 3** (capa de Red, modelo OSI):

1. **Acceso WAN:** el portátil obtuvo conectividad a Internet mediante anclaje USB (*tethering*) desde un smartphone Android (interfaz `enp0s20f0u2u2`), que actúa como módem celular 4G/5G.
2. **Acceso LAN:** el portátil mantuvo su conexión Wi-Fi al router TP-Link a través de la interfaz `wlp45s0` con IP `192.168.1.101/24`.
3. **Reenvío de paquetes:** se habilitó el *forwarding* de paquetes IP en el kernel del portátil.
4. **Enmascaramiento NAT:** se configuró una regla de enmascaramiento en la tabla `nat` de `iptables` para que todo el tráfico saliente del servidor apareciese como originado por el portátil.
5. **Apertura del firewall perimetral:** se reconfiguró la política de la cadena `FORWARD` de la tabla `filter` para permitir el tránsito de paquetes entre interfaces.

#### Configuración del Servidor (Netplan)

Archivo `/etc/netplan/01-network.yaml` en el servidor:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp3s0:
      addresses:
        - 192.168.1.50/24
      routes:
        - to: default
          via: 192.168.1.101
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
```

#### Configuración del Portátil (iptables + sysctl)

```bash
# Habilitar reenvío de paquetes entre interfaces
sudo sysctl -w net.ipv4.ip_forward=1

# Enmascarar tráfico saliente hacia la interfaz WAN celular
sudo iptables -t nat -A POSTROUTING \
  -o enp0s20f0u2u2 -j MASQUERADE

# CRÍTICO: la cadena FORWARD de la tabla filter
# tiene política DROP por defecto. Sin esta regla,
# los paquetes entre interfaces son descartados.
sudo iptables -P FORWARD ACCEPT
```

### Análisis de Seguridad: Inspección de Estado de Paquetes (Stateful Packet Inspection)

Además de la activación del *forwarding* en el kernel (`net.ipv4.ip_forward=1`) y la regla de enmascaramiento en la tabla `nat` (`POSTROUTING -j MASQUERADE`), el flujo inicial de paquetes fue interceptado por la política restrictiva por defecto de la cadena `FORWARD` de la tabla `filter` en el portátil de desarrollo.

La arquitectura de seguridad perimetral de la distribución bloquea por defecto el tránsito de paquetes entre interfaces distintas del mismo host (WLAN $\leftrightarrow$ USB-WAN Cellular). Este mecanismo de **inspección de estado de paquetes** (*Stateful Packet Inspection*, SPI) protege al sistema operativo del portátil contra tráfico no solicitado que pudiera cursarse entre segmentos de red. Sin embargo, en el escenario de contingencia —donde el portátil asume temporalmente el rol de enrutador intermedio— esta política de filtrado interrumpe completamente el puente de red, impidiendo que el servidor headless alcance los repositorios de paquetes de Ubuntu a través de la conexión celular.

La solución consistió en reconfigurar transitoriamente la política de filtrado de la cadena `FORWARD`, mutando la directiva por defecto de `DROP` a `ACCEPT` durante la ventana de actualización. Esta maniobra, aunque reduce temporalmente la postura de seguridad del portátil de desarrollo, está confinada exclusivamente al segmento de red aislado (`192.168.1.0/24`) y a la interfaz USB de *tethering* —que no expone servicios locales accesibles desde la red celular—, por lo que el riesgo de exposición externa es inexistente. Una vez completada la instalación del *stack* base del servidor y verificada la conectividad, la política de filtrado fue restablecida a su valor por defecto.

## Consecuencias

1. **La topología de red air-gapped queda completamente documentada y es reproducible.** Cualquier nuevo dispositivo en el segmento `192.168.1.0/24` puede incorporarse siguiendo el mismo procedimiento de asignación estática de IP y enrutamiento hacia el portátil como pasarela de contingencia.

2. **El servidor Ubuntu Server está completamente operativo** con el *stack* de desarrollo instalado (Python 3.11+, Node.js 22, Git, Cockpit, `bluez`), listo para recibir el despliegue de OpenClaw y Ollama.

3. **El patrón de Gateway de contingencia es reutilizable** para futuras situaciones en las que el servidor requiera acceso puntual a Internet (actualizaciones de seguridad, instalación de nuevos paquetes) sin comprometer la arquitectura air-gapped permanente.

4. **La documentación del análisis de seguridad (iptables filter table)** sirve como referencia académica para comprender la interacción entre las políticas de filtrado perimetral y el enrutamiento inter-interfaz en sistemas Linux, un concepto aplicable a cualquier despliegue de Edge AI que opere en entornos de red restringidos.
