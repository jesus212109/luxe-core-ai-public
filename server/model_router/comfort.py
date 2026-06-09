"""
Comfort Advisor — Recomendaciones de confort térmico.

Basado en temperatura + humedad relativa → índice de calor + recomendaciones
adaptadas al clima del sur de España (Córdoba/Andalucía).

Uso:
  from model_router.comfort import ComfortAdvisor
  result = ComfortAdvisor.assess(27.6, 53)
  print(ComfortAdvisor.format_simple(27.6, 53))
"""


class ComfortAdvisor:
    """Calcula el nivel de confort térmico y genera recomendaciones.

    Zonas térmicas:
      🟢 FRESCO       < 23°C           → Apagar ventilador
      🟢 CONFORTABLE  23-26°C, HR OK   → Sin acción
      🟡 CÁLIDO       26-28°C          → Ventilador 1-2
      🟠 CALOR        28-31°C          → Ventilador 3
      🔴 MUY CALOR    31-34°C          → Ventilador 4-5 + considerar AC
      🟣 EXTREMO      > 34°C           → Ventilador 5 + AC urgente

    Humedad:
      🔸 SECO    < 35% HR  → Recomendar humidificador
      ✅ ÓPTIMO  35-70% HR → Sin acción
      💧 HÚMEDO  > 70% HR  → Ventilador ayuda (no AC, reseca más)
    """

    # (temp_max, label, emoji, fan_speed, ac_recommended)
    THERMAL_ZONES = [
        (23, "Fresco",       "🟢", 0, False),
        (26, "Confortable",  "🟢", 0, False),
        (28, "Cálido",       "🟡", 1, False),
        (31, "Caluroso",     "🟠", 3, False),
        (34, "Muy caluroso", "🔴", 4, True),
        (99, "Extremo",      "🟣", 5, True),
    ]

    # Tracking de velocidad manual del usuario
    _manual_speed_file = "/tmp/luxe_manual_fan_speed.json"

    HUMIDITY_DRY = 35       # % — por debajo: ambiente seco
    HUMIDITY_HUMID = 70     # % — por encima: ambiente húmedo

    @classmethod
    def assess(cls, temperature_c: float, humidity_pct: float) -> dict:
        """Evalúa las condiciones y devuelve recomendaciones completas."""
        # --- Zona térmica ---
        for i, (tmax, label, emoji, fan, ac) in enumerate(cls.THERMAL_ZONES):
            if temperature_c < tmax:
                zone_idx = i
                break
        else:
            zone_idx = len(cls.THERMAL_ZONES) - 1

        _, label, emoji, fan_speed, ac_rec = cls.THERMAL_ZONES[zone_idx]

        # --- Estado de humedad ---
        if humidity_pct < cls.HUMIDITY_DRY:
            hum_status = "seco"
            humidifier = True
            hum_emoji = "🔸"
            hum_label = "Seco"
        elif humidity_pct > cls.HUMIDITY_HUMID:
            hum_status = "húmedo"
            humidifier = False
            hum_emoji = "💧"
            hum_label = "Húmedo"
        else:
            hum_status = "óptimo"
            humidifier = False
            hum_emoji = "✅"
            hum_label = ""

        # --- Sensación térmica (heat index) ---
        hi = cls._heat_index(temperature_c, humidity_pct)

        # --- Resumen ---
        parts = [f"{emoji} {temperature_c:.1f}°C"]
        if hum_label:
            parts.append(f"{hum_emoji} {humidity_pct:.0f}%")
        else:
            parts.append(f"{humidity_pct:.0f}% HR")
        if abs(hi - temperature_c) >= 0.5:
            parts.append(f"🌡️ Sensación {hi:.1f}°C")
        summary = " | ".join(parts)

        # --- Recomendaciones ---
        actions = []

        if fan_speed == 0:
            actions.append("🌀 Ventilador: no necesario ahora")
        elif zone_idx <= 2:  # Fresco a Cálido
            actions.append(f"🌀 Ventilador al {fan_speed} sería suficiente")
        elif zone_idx == 3:  # Caluroso
            actions.append(f"🌀 Pon el ventilador al {fan_speed}")
        else:  # Muy caluroso o Extremo
            actions.append(f"🌀 Ventilador al {fan_speed} (máximo)")

        if humidifier:
            actions.append("💦 Humidificador recomendado — el ambiente está seco")

        if ac_rec:
            if zone_idx == 4:  # Muy caluroso
                actions.append("❄️ Plantéate encender el aire acondicionado")
            else:  # Extremo
                actions.append("❄️ Enciende el aire acondicionado cuanto antes")
            actions.append("💡 Tip: 10 min de ventilador antes del AC para enfriar antes la habitación")

        if not actions:
            actions.append("✅ Condiciones óptimas, ¡a disfrutar!")

        return {
            "temperature": temperature_c,
            "humidity": humidity_pct,
            "zone": zone_idx,
            "label": label,
            "emoji": emoji,
            "fan_speed": fan_speed,
            "ac_recommended": ac_rec,
            "humidity_status": hum_status,
            "humidifier_recommended": humidifier,
            "summary": summary,
            "actions": actions,
            "heat_index": hi,
        }

    # ------------------------------------------------------------------
    # Fórmula NOAA Heat Index (sensación térmica)
    # ------------------------------------------------------------------

    @staticmethod
    def _heat_index(temp_c: float, humidity_pct: float) -> float:
        """Índice de calor NOAA (Rothfusz). Solo aplica T > 27°C y HR > 40%.
        
        La fórmula original usa °F. Convertimos a °F para el cálculo
        y devolvemos el resultado en °C.
        """
        if temp_c < 27 or humidity_pct < 40:
            return temp_c
        
        # Convertir a Fahrenheit para la fórmula NOAA
        T = temp_c * 9 / 5 + 32
        R = humidity_pct
        
        HI_F = (-42.379 + 2.04901523 * T + 10.14333127 * R
                - 0.22475541 * T * R - 6.83783e-3 * T ** 2
                - 5.481717e-2 * R ** 2 + 1.22874e-3 * T ** 2 * R
                + 8.5282e-4 * T * R ** 2 - 1.99e-6 * T ** 2 * R ** 2)
        
        # Ajuste para HR < 13% y T 80-112°F
        if R < 13 and 80 <= T <= 112:
            HI_F -= ((13 - R) / 4) * ((17 - abs(T - 95)) / 17) ** 0.5
        
        # Convertir de vuelta a Celsius
        return round((HI_F - 32) * 5 / 9, 1)

    # ------------------------------------------------------------------
    # Formatos de salida
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Tracking de velocidad manual
    # ------------------------------------------------------------------

    @classmethod
    def record_manual_speed(cls, speed: int) -> None:
        """Registra que el usuario ha puesto manualmente el ventilador a X."""
        import json, time
        try:
            with open(cls._manual_speed_file, "w") as f:
                json.dump({"speed": speed, "timestamp": time.time()}, f)
        except Exception:
            pass

    @classmethod
    def get_previous_manual_speed(cls) -> tuple[int | None, float | None]:
        """Devuelve (velocidad, timestamp) del último ajuste manual del usuario.
        Solo si fue en los últimos 30 minutos.
        """
        import json, os, time
        try:
            if not os.path.exists(cls._manual_speed_file):
                return None, None
            with open(cls._manual_speed_file) as f:
                data = json.load(f)
            age = time.time() - data.get("timestamp", 0)
            if age > 1800:  # 30 min
                return None, None
            return data.get("speed"), data.get("timestamp")
        except Exception:
            return None, None

    # ------------------------------------------------------------------
    # Formatos de salida
    # ------------------------------------------------------------------

    @classmethod
    def format_simple(cls, temperature_c: float, humidity_pct: float,
                      timestamp: str = None) -> str:
        """Formato compacto para consultas rápidas de temperatura."""
        a = cls.assess(temperature_c, humidity_pct)
        msg = a["summary"]
        if timestamp:
            ts = timestamp[:16].replace("T", " ")
            msg += f"\n📡 {ts}"
        return msg

    @classmethod
    def format_full(cls, temperature_c: float, humidity_pct: float,
                    timestamp: str = None) -> str:
        """Formato completo con recomendaciones accionables."""
        a = cls.assess(temperature_c, humidity_pct)
        lines = [
            a["summary"],
            "",
            "📋 Recomendaciones:",
        ]
        for action in a["actions"]:
            lines.append(f"  {action}")
        if timestamp:
            ts = timestamp[:16].replace("T", " ")
            lines.append(f"\n📡 Datos de {ts}")
        return "\n".join(lines)
