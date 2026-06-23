#!/usr/bin/env python3
"""Genera fig_9_1_latencia.pdf — barras agrupadas de latencia antes/después."""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Colores corporativos EPSC
EPSCDark = '#280091'
EPSCMedium = '#4C5CC5'
DarkGray = '#505050'

# Configuración global de fuente
plt.rcParams.update({
    'font.family': 'Linux Libertine O',
    'font.size': 10,
    'axes.unicode_minus': False,
})

# Datos
categorias = np.array([
    'velocidad 3',
    'cómo está\nla casa',
    'enciende\nla luz',
    'temperatura',
    'buenos días',
])
x = np.arange(len(categorias))
width = 0.30

antes = np.array([2.0, 2.0, 3.0, 18.0, 12.0])
despues = np.array([1.5, 0.001, 0.3, 0.001, 15.0])

# --- Figura ---
fig, ax = plt.subplots(figsize=(6.8, 4.8))

barras_antes = ax.bar(
    x - width / 2, antes, width,
    label='Antes',
    color=EPSCDark,
    edgecolor='white',
    linewidth=0.3,
    zorder=3,
)
barras_despues = ax.bar(
    x + width / 2, despues, width,
    label='Después',
    color=EPSCMedium,
    edgecolor='white',
    linewidth=0.3,
    zorder=3,
)

# Etiquetas de valor sobre las barras (excepto valores < 0.01 que son ilegibles)
for bar, val in zip(barras_antes, antes):
    if val >= 0.01:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.08,
                f'{val:.0f}' if val >= 1 else f'{val:.1f}'.replace('.', ','),
                ha='center', va='bottom', fontsize=7, color=EPSCDark, fontweight='bold')
for bar, val in zip(barras_despues, despues):
    if val >= 0.01:
        label = f'{val:.0f}' if val >= 1 else f'{val:.1f}'.replace('.', ',')
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.5,
                label, ha='center', va='bottom', fontsize=7, color=EPSCMedium, fontweight='bold')
    else:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 3,
                '< 10 ms', ha='center', va='bottom', fontsize=6.5, color=EPSCMedium,
                fontweight='bold', style='italic')

# Escala logarítmica
ax.set_yscale('log')
ax.set_ylim(0.0002, 30)

# Ejes
ax.set_ylabel('Latencia (s)', fontsize=10, color=DarkGray)
ax.set_xticks(x)
ax.set_xticklabels(categorias, fontsize=8.5, color=DarkGray)
ax.tick_params(axis='x', length=0)
ax.tick_params(axis='y', labelsize=8.5, colors=DarkGray)

# Ticks del eje Y con coma decimal española
ax.set_yticks([0.001, 0.01, 0.1, 1, 10])
ax.set_yticklabels(['0,001', '0,01', '0,1', '1', '10'])

# Grid limpio
ax.grid(axis='y', alpha=0.25, linestyle='--', linewidth=0.5, color='#888888')
ax.set_axisbelow(True)

# Quitar bordes superior y derecho
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#CCCCCC')
ax.spines['left'].set_linewidth(0.8)
ax.spines['bottom'].set_color('#CCCCCC')
ax.spines['bottom'].set_linewidth(0.8)

# Leyenda
legend = ax.legend(
    fontsize=9,
    loc='upper left',
    framealpha=0.9,
    edgecolor='#DDDDDD',
    fancybox=False,
)
legend.get_frame().set_linewidth(0.5)

# Título
ax.set_title(
    'Comparación de latencia antes y después de la implementación',
    fontsize=11.5,
    fontweight='bold',
    color=EPSCDark,
    pad=14,
)

# Nota al pie
fig.text(
    0.5, 0.01,
    'Los valores son sobre hardware real (Ryzen 5, 16 GB RAM).',
    ha='center',
    fontsize=7.5,
    color=DarkGray,
    style='italic',
)

# Ajuste final
fig.tight_layout(rect=[0, 0.04, 1, 0.97])

# Guardar
output_path = os.path.join(OUTPUT_DIR, 'gen_fig_9_1_latencia.pdf')
fig.savefig(output_path, bbox_inches='tight', dpi=150)
plt.close(fig)

size_kb = os.path.getsize(output_path) / 1024
print(f'✅ gen_fig_9_1_latencia.pdf generado ({size_kb:.0f} KB)')
