#!/bin/bash
# compile_docs.sh — Compilador multiplataforma de la memoria LaTeX
#
# Uso:
#   ./compile_docs.sh              # Verificar y compilar
#   ./compile_docs.sh --install    # Instalar dependencias que falten y compilar
#   ./compile_docs.sh --check-only # Solo verificar dependencias, no compilar

set -euo pipefail

cd "$(dirname "$0")"

# ─── Colores ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[*]${RESET} $*"; }
success() { echo -e "${GREEN}[✓]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
error()   { echo -e "${RED}[✗]${RESET} $*"; }

echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   Luxe Core AI — Compilador LaTeX    ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ─── Auto-detectar gestor de paquetes ──────────────────────────────────────────
PKG_MANAGER=""
INSTALL_CMD=""
PACKAGE_PREFIX=""

if command -v apt &>/dev/null; then
    PKG_MANAGER="apt"
    INSTALL_CMD="sudo apt install -y"
    PACKAGE_PREFIX="deb"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"
    PACKAGE_PREFIX="rpm"
elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
    INSTALL_CMD="sudo pacman -S --needed --noconfirm"
    PACKAGE_PREFIX="arch"
fi

# ─── Mapa de paquetes por distribución ─────────────────────────────────────────
# Formato: NOMBRE_STY:paquete_deb:paquete_rpm:paquete_arch
# Vacío = no necesario o nombre coincide
PACKAGE_MAP=(
    "libertine.sty:texlive-fonts-extra:texlive-libertine:texlive-fontsextra"
    "microtype.sty:texlive-latex-extra:texlive-microtype:texlive-latexextra"
    "biblatex.sty:texlive-latex-extra:texlive-biblatex:texlive-bibtexextra"
    "fancyhdr.sty:texlive-latex-extra:texlive-fancyhdr:texlive-latexextra"
    "titlesec.sty:texlive-latex-extra:texlive-titlesec:texlive-latexextra"
    "setspace.sty:texlive-latex-base:texlive-setspace:texlive-latexextra"
    "beramono.sty:texlive-bera:texlive-bera:texlive-bera"
)

# Binarios necesarios y su paquete
BINARY_MAP=(
    "pdflatex:texlive-latex-base:texlive-latex:texlive-core"
    "biber:biber:texlive-biber:biber"
)

pkg_for_os() {
    local entry="$1"
    local index
    case "$PACKAGE_PREFIX" in
        deb)  index=1 ;;
        rpm)  index=2 ;;
        arch) index=3 ;;
        *)    echo ""; return ;;
    esac
    echo "$entry" | cut -d':' -f"$((index+1))"
}

# ─── Verificar binarios ────────────────────────────────────────────────────────
MISSING_BINARIES=""
for entry in "${BINARY_MAP[@]}"; do
    bin=$(echo "$entry" | cut -d':' -f1)
    if ! command -v "$bin" &>/dev/null; then
        pkg=$(pkg_for_os "$entry")
        MISSING_BINARIES+=" $bin"
    fi
done

# ─── Verificar paquetes LaTeX ───────────────────────────────────────────────────
MISSING_PKGS=""
MISSING_STY=""
for entry in "${PACKAGE_MAP[@]}"; do
    sty=$(echo "$entry" | cut -d':' -f1)
    if ! kpsewhich "$sty" &>/dev/null 2>&1; then
        pkg=$(pkg_for_os "$entry")
        MISSING_PKGS+=" $pkg"
        MISSING_STY+=" $sty"
    fi
done

# ─── Modo --check-only: informar y salir ───────────────────────────────────────
if [ "${1:-}" = "--check-only" ]; then
    ALL_OK=true
    if [ -n "$MISSING_BINARIES" ]; then
        warn "Binarios faltantes:$MISSING_BINARIES"
        ALL_OK=false
    fi
    if [ -n "$MISSING_STY" ]; then
        warn "Paquetes LaTeX faltantes:$MISSING_STY"
        ALL_OK=false
    fi
    if [ -z "$PKG_MANAGER" ]; then
        warn "No se pudo detectar el gestor de paquetes."
        ALL_OK=false
    fi
    if $ALL_OK; then
        success "Entorno TeX Live completo."
        exit 0
    fi
    exit 1
fi

# ─── Resolver dependencias faltantes ───────────────────────────────────────────
NEEDS_INSTALL=false
INSTALL_LIST=""

if [ -n "$MISSING_BINARIES" ] || [ -n "$MISSING_PKGS" ]; then
    NEEDS_INSTALL=true
    INSTALL_LIST="$MISSING_PKGS"

    # Añadir paquetes de binarios faltantes si no son parte de un paquete LaTeX
    for entry in "${BINARY_MAP[@]}"; do
        bin=$(echo "$entry" | cut -d':' -f1)
        if ! command -v "$bin" &>/dev/null; then
            pkg=$(pkg_for_os "$entry")
            INSTALL_LIST+=" $pkg"
        fi
    done
fi

# ─── Intentar instalar si --install está presente ──────────────────────────────
if [ "${1:-}" = "--install" ]; then
    if $NEEDS_INSTALL; then
        if [ -z "$PKG_MANAGER" ]; then
            error "No se detectó gestor de paquetes (apt/dnf/pacman)."
            echo "  Instala TeX Live manualmente: https://tug.org/texlive/quickinstall.html"
            exit 1
        fi
        info "Instalando dependencias faltantes con $PKG_MANAGER..."
        # Normalizar lista (eliminar espacios duplicados)
        INSTALL_LIST=$(echo "$INSTALL_LIST" | tr -s ' ')
        # shellcheck disable=SC2086
        $INSTALL_CMD $INSTALL_LIST
        success "Dependencias instaladas correctamente."
    else
        info "No hay dependencias que instalar."
    fi

    # Re-verificar que pdflatex esté disponible después de instalar
    if ! command -v pdflatex &>/dev/null || ! command -v biber &>/dev/null; then
        error "Todavía faltan binarios tras la instalación."
        echo "  Puede que necesites instalar texlive-full o equivalente:"
        case "$PACKAGE_PREFIX" in
            deb)  echo "  sudo apt install texlive-full biber -y" ;;
            rpm)  echo "  sudo dnf install texlive-scheme-full -y" ;;
            arch) echo "  sudo pacman -S texlive-most biber --noconfirm" ;;
        esac
        exit 1
    fi
elif $NEEDS_INSTALL; then
    error "Entorno TeX Live incompleto."
    echo ""
    echo "  Binarios faltantes:$MISSING_BINARIES"
    echo "  Paquetes faltantes:$MISSING_STY"
    echo ""
    echo "  Para instalarlos automáticamente, ejecuta:"
    echo -e "  ${BOLD}  ./compile_docs.sh --install${RESET}"
    echo ""
    if [ -n "$PKG_MANAGER" ]; then
        echo "  O manualmente con tu gestor de paquetes:"
        echo -e "  ${BOLD}  $INSTALL_CMD $(echo $INSTALL_LIST | tr -s ' ')${RESET}"
        echo ""
    fi
    echo "  O instala TeX Live completo: https://tug.org/texlive/quickinstall.html"
    echo ""
    exit 1
fi

# ─── Compilar ───────────────────────────────────────────────────────────────────
info "Iniciando compilación de main.tex..."

# Paso 1
info "Paso 1/4 — Primera pasada (estructura e índice)..."
if ! pdflatex -interaction=nonstopmode -halt-on-error main.tex > compile.log 2>&1; then
    error "Error en la primera compilación."
    grep -E "^!" compile.log | head -10 || tail -20 compile.log
    echo "  Log completo: $(pwd)/compile.log"
    exit 1
fi

# Paso 2
info "Paso 2/4 — Procesando bibliografía (biber)..."
if ! biber main > biber.log 2>&1; then
    warn "Biber reportó problemas (puede ser normal si la bibliografía está vacía)."
    tail -5 biber.log
fi

# Paso 3
info "Paso 3/4 — Segunda pasada (referencias cruzadas)..."
pdflatex -interaction=nonstopmode -halt-on-error main.tex >> compile.log 2>&1 || true

# Paso 4
info "Paso 4/4 — Tercera pasada (resolución final)..."
pdflatex -interaction=nonstopmode -halt-on-error main.tex >> compile.log 2>&1 || true

# ─── Limpieza ────────────────────────────────────────────────────────────────────
info "Limpiando archivos temporales..."
rm -f *.aux *.log *.toc *.out *.bbl *.blg *.bcf *.run.xml \
      *.fdb_latexmk *.fls *.synctex.gz compile.log biber.log
rm -f sections/*.aux appendices/*.aux 2>/dev/null || true

echo ""
echo -e "${BOLD}${GREEN}  ╔══════════════════════════════════════╗"
echo -e "  ║   ✓  Compilación finalizada           ║"
echo -e "  ║   Documento: docs/main.pdf            ║"
echo -e "  ╚══════════════════════════════════════╝${RESET}"
echo ""
