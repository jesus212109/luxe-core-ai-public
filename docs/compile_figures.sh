#!/bin/bash
# Compilar todas las figuras independientes del TFG
# Uso: bash compile_figures.sh [figura]
#   Sin argumentos: compila todas (TikZ + Python)
#   Con argumento: compila solo esa (ej: bash compile_figures.sh fig_8_3_router)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIGURES_DIR="$SCRIPT_DIR/figures"
IMG_DIR="$SCRIPT_DIR/img"

# Crear directorios si no existen
mkdir -p "$FIGURES_DIR" "$IMG_DIR"

cd "$FIGURES_DIR"

# --- Función: copiar PDF a img/ con nombre corto ---
copy_pdf() {
    local base="$1"
    local pdf="${base}.pdf"
    if [ -f "$pdf" ]; then
        local short
        short=$(echo "$base" | sed -E 's/^gen_//; s/_[^_]+$//')
        cp "$pdf" "${IMG_DIR}/${short}.pdf"
        echo "   📋 Copiado a ${IMG_DIR}/${short}.pdf"
    fi
}

# --- Generadores Python ---
run_python_gen() {
    local script="$1"
    local base="${script%.py}"
    echo "🐍 Ejecutando ${script}..."
    if python3 "$script" 2>&1; then
        copy_pdf "$base"
    else
        echo "   ❌ Error en ${script}"
    fi
}

# --- Compilación LaTeX ---
compile_latex() {
    local tex="$1"
    local base="${tex%.tex}"
    echo "🔨 Compilando ${base}..."
    if pdflatex -interaction=nonstopmode "$tex" > /dev/null 2>&1; then
        echo "   ✅ ${base}.pdf generado"
        copy_pdf "$base"
    else
        echo "   ❌ Error en ${base} — revisa ${base}.log"
    fi
}

# --- Selección de figuras ---
if [ $# -eq 1 ]; then
    # Modo: una figura específica
    name="$1"
    found=false

    # Intentar como generador Python
    py_script="gen_${name}.py"
    if [ -f "$py_script" ]; then
        run_python_gen "$py_script"
        found=true
    fi

    # Intentar como archivo LaTeX
    tex_file="${name}.tex"
    if [ -f "$tex_file" ]; then
        compile_latex "$tex_file"
        found=true
    fi

    if [ "$found" = false ]; then
        echo "⚠️  No se encuentra gen_${name}.py ni ${name}.tex"
        exit 1
    fi
else
    # Modo: todas las figuras

    # Generadores Python
    for script in gen_fig_*.py; do
        [ -f "$script" ] || continue
        run_python_gen "$script"
    done

    # Figuras LaTeX
    for tex in fig_*.tex; do
        [ -f "$tex" ] || continue
        compile_latex "$tex"
    done
fi

# Limpiar temporales LaTeX
rm -f fig_*.aux fig_*.log fig_*.out 2>/dev/null

echo ""
echo "✅ Compilación completada."
