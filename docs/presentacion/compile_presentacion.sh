#!/usr/bin/env bash
# ============================================================================
#  Compilación de la presentación Beamer — Luxe Core AI
#  Requiere: pdflatex (TeX Live 2023+)
#
#  1. Compila las figuras TikZ en figures/*.tex
#  2. Compila la presentación principal (2 pasadas)
# ============================================================================
set -euo pipefail

PRESENTACION_DIR="$(cd "$(dirname "$0")" && pwd)"
FIGURES_DIR="$PRESENTACION_DIR/figures"

echo "==> Luxe Core AI — Compilación de presentación"
echo "    Directorio: $PRESENTACION_DIR"

# -------------------------------------------------------
# Fase 0: Compilar figuras TikZ
# -------------------------------------------------------
if ls "$FIGURES_DIR"/*.tex &>/dev/null; then
    echo "    [0] Compilando figuras TikZ..."
    for f in "$FIGURES_DIR"/*.tex; do
        name="$(basename "$f" .tex)"
        echo "        $name"
        pdflatex -interaction=nonstopmode \
            -output-directory "$FIGURES_DIR" "$f" > /dev/null 2>&1
        if [ ! -f "$FIGURES_DIR/$name.pdf" ]; then
            echo "        ERROR en $name. Log:"
            tail -10 "$FIGURES_DIR/$name.log"
            exit 1
        fi
    done
    echo "    [0] Figuras compiladas."
else
    echo "    [0] Sin figuras que compilar."
fi

# -------------------------------------------------------
# Fase 1: Primera pasada pdflatex
# -------------------------------------------------------
echo "    [1/2] Primera pasada pdflatex (main.tex)..."
cd "$PRESENTACION_DIR"
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null 2>&1 || {
    echo "    ERROR en primera pasada. Mostrando log:"
    tail -40 main.log
    exit 1
}

# -------------------------------------------------------
# Fase 2: Segunda pasada pdflatex (resuelve referencias)
# -------------------------------------------------------
echo "    [2/2] Segunda pasada pdflatex..."
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null 2>&1 || {
    echo "    ERROR en segunda pasada. Mostrando log:"
    tail -40 main.log
    exit 1
}

echo "==> Presentación compilada: $PRESENTACION_DIR/main.pdf"
ls -lh "$PRESENTACION_DIR/main.pdf"
echo "    Páginas: $(pdfinfo main.pdf 2>/dev/null | grep Pages | awk '{print $2}' || echo '?')"
