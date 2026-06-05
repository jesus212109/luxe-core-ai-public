#!/bin/bash
# Compilar todas las figuras independientes del TFG
# Uso: bash compile_figures.sh [figura]
#   Sin argumentos: compila todas
#   Con argumento: compila solo esa (ej: bash compile_figures.sh fig_8_3_router)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIGURES_DIR="$SCRIPT_DIR/figures"
IMG_DIR="$SCRIPT_DIR/img"

# Crear directorios si no existen
mkdir -p "$FIGURES_DIR" "$IMG_DIR"

cd "$FIGURES_DIR"

if [ $# -eq 1 ]; then
    FILES=("$1.tex")
else
    FILES=(fig_*.tex)
fi

for f in "${FILES[@]}"; do
    if [ ! -f "$f" ]; then
        echo "⚠️  No se encuentra: $f"
        continue
    fi
    BASE="${f%.tex}"
    echo "🔨 Compilando $BASE..."
    if pdflatex -interaction=nonstopmode "$f" > /dev/null 2>&1; then
        echo "   ✅ $BASE.pdf generado"
        # Extraer nombre corto: fig_8_1_arquitectura -> fig_8_1.pdf
        SHORTNAME=$(echo "$BASE" | sed -E 's/_(arquitectura|despliegue|router|confort|ble)$//')
        cp "${BASE}.pdf" "${IMG_DIR}/${SHORTNAME}.pdf"
        echo "   📋 Copiado a ${IMG_DIR}/${SHORTNAME}.pdf"
    else
        echo "   ❌ Error en $BASE — revisa $BASE.log"
    fi
done

# Limpiar temporales de todas las figuras
rm -f fig_*.aux fig_*.log fig_*.out 2>/dev/null

echo ""
echo "✅ Compilación completada."
