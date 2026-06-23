#!/usr/bin/env python3
"""Genera fig_9_3_modelos.pdf — modelos evaluados para el Tier 2."""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Colores corporativos EPSC
EPSCDark = '#280091'
EPSCMedium = '#4C5CC5'
EPSCLight = '#8899DD'
DarkGray = '#505050'

# Configuración global de fuente
plt.rcParams.update({
    'font.family': 'Linux Libertine O',
    'font.size': 10,
    'axes.unicode_minus': False,
})

# Datos — modelos evaluados para Tier 2
modelos = [
    'Qwen3.5 9B\n(descartado)',
    'Qwen3.5 4B\n(descartado)',
    'Mistral 7B\n(seleccionado)',
    'Qwen2.5 7B\n(línea base)',
]
tiempos = [310, 135, 60, 27]  # segundos (valores experimentales reales)
colores = ['#CC4444', '#DD8844', EPSCDark, EPSCMedium]

y = np.arange(len(modelos))

# --- Figura ---
fig, ax = plt.subplots(figsize=(7.2, 4.5))

barras = ax.barh(
    y, tiempos, height=0.55,
    color=colores,
    edgecolor='white',
    linewidth=0.3,
    zorder=3,
)

# Etiquetas de valor sobre cada barra
for bar, val in zip(barras, tiempos):
    label = f'{val} s'
    ax.text(
        bar.get_width() + 8, bar.get_y() + bar.get_height() / 2,
        label, ha='left', va='center', fontsize=9,
        color=DarkGray, fontweight='bold',
    )

# Anotaciones cualitativas
anotaciones = [
    ('thinking mode\ninviable CPU', 310),
    ('thinking mode\ninviable CPU', 135),
    ('sin thinking\nrespuesta directa', 60),
    ('sin thinking\nrespuesta directa', 27),
]
for texto, x_pos in anotaciones:
    ax.text(
        x_pos + 60, y[anotaciones.index((texto, x_pos))],
        texto, ha='left', va='center', fontsize=7.5,
        color=DarkGray, style='italic',
    )

# Ejes
ax.set_xlim(0, 430)
ax.set_yticks(y)
ax.set_yticklabels(modelos, fontsize=8.5, color=DarkGray)
ax.tick_params(axis='y', length=0)
ax.tick_params(axis='x', labelsize=8.5, colors=DarkGray)
ax.set_xlabel('Latencia media (segundos)', fontsize=9.5, color=DarkGray)

# Grid limpio
ax.grid(axis='x', alpha=0.25, linestyle='--', linewidth=0.5, color='#888888')
ax.set_axisbelow(True)

# Quitar bordes
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#CCCCCC')
ax.spines['left'].set_linewidth(0.8)
ax.spines['bottom'].set_color('#CCCCCC')
ax.spines['bottom'].set_linewidth(0.8)

# Título
ax.set_title(
    'Modelos evaluados para el Tier 2 (razonador)',
    fontsize=11.5,
    fontweight='bold',
    color=EPSCDark,
    pad=14,
)

# Nota al pie
fig.text(
    0.5, 0.01,
    'Hardware: Ryzen 5, 16 GB RAM, Ubuntu 24.04, Ollama 0.24. '
    'Qwen3.5 descartado por thinking mode forzado (>0.6 tok/s en CPU). '
    'Mistral 7B seleccionado por respuesta directa y calidad conversacional.',
    ha='center',
    fontsize=7.5,
    color=DarkGray,
    style='italic',
)

# Ajuste final
fig.tight_layout(rect=[0, 0.06, 1, 0.97])

# Guardar
output_path = os.path.join(OUTPUT_DIR, 'gen_fig_9_3_modelos.pdf')
fig.savefig(output_path, bbox_inches='tight', dpi=150)
plt.close(fig)

size_kb = os.path.getsize(output_path) / 1024
print(f'✅ gen_fig_9_3_modelos.pdf generado ({size_kb:.0f} KB)')
