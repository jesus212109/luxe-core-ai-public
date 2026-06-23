#!/usr/bin/env python3
"""Genera fig_9_2_cobertura.pdf — barras de cobertura del Tier 0."""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Colores corporativos EPSC
EPSCDark = '#280091'
DarkGray = '#505050'
EPSCMedium = '#4C5CC5'

# Configuración global de fuente
plt.rcParams.update({
    'font.family': 'Linux Libertine O',
    'font.size': 10,
    'axes.unicode_minus': False,
})

# Datos
categorias = [
    'Iluminación\n(35 patrones)',
    'Ventilador\n(50 patrones)',
    'Escenas\n(40 patrones)',
    'Consultas\n(15 patrones)',
    'Conversacionales',
]
cobertura = [100, 100, 100, 100, 0]
x = np.arange(len(categorias))

# --- Figura ---
fig, ax = plt.subplots(figsize=(6.8, 4.5))

barras = ax.bar(
    x, cobertura, width=0.55,
    color=EPSCDark,
    edgecolor='white',
    linewidth=0.3,
    zorder=3,
)

# Etiquetas de porcentaje sobre las barras
etiquetas = ax.bar_label(
    barras,
    labels=['100 %', '100 %', '100 %', '100 %', ''],
    fontsize=9,
    color=EPSCDark,
    fontweight='bold',
    padding=4,
)

# Anotación para Conversacionales
ax.text(
    4, 5,
    'Derivados\nal Tier 2',
    ha='center',
    va='bottom',
    fontsize=8,
    color=DarkGray,
    style='italic',
    linespacing=1.3,
)

# Límites del eje Y
ax.set_ylim(0, 120)

# Ejes
ax.set_ylabel('Cobertura (%)', fontsize=10, color=DarkGray)
ax.set_xticks(x)
ax.set_xticklabels(categorias, fontsize=8, color=DarkGray)
ax.tick_params(axis='x', length=0)
ax.tick_params(axis='y', labelsize=9, colors=DarkGray)
ax.set_yticks([0, 20, 40, 60, 80, 100])

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

# Línea de texto informativa adicional sobre la barra de Conversacionales
# usando una flecha o línea punteada que indique la derivación

# Título
ax.set_title(
    'Cobertura del sistema de zero-inference (Tier 0)',
    fontsize=11.5,
    fontweight='bold',
    color=EPSCDark,
    pad=14,
)

# Nota al pie
fig.text(
    0.5, 0.01,
    'Sobre corpus de 500 comandos reales recogidos durante una semana de uso.',
    ha='center',
    fontsize=7.5,
    color=DarkGray,
    style='italic',
)

# Ajuste final
fig.tight_layout(rect=[0, 0.04, 1, 0.97])

# Guardar
output_path = os.path.join(OUTPUT_DIR, 'gen_fig_9_2_cobertura.pdf')
fig.savefig(output_path, bbox_inches='tight', dpi=150)
plt.close(fig)

size_kb = os.path.getsize(output_path) / 1024
print(f'✅ gen_fig_9_2_cobertura.pdf generado ({size_kb:.0f} KB)')
