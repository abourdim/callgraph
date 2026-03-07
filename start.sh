#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Callgraph Studio — start.sh
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-7411}"

# ── Colors ────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[0;33m'
B='\033[0;34m' C='\033[0;36m' W='\033[1;37m'
D='\033[2m'    N='\033[0m'

# ── Check functions ───────────────────────────────────────────
has()     { command -v "$1" &>/dev/null; }
py_has()  { python3 -c "import $1" 2>/dev/null; }
py_ver()  { python3 -c "import $1; print(getattr($1,'__version__','ok'))" 2>/dev/null || echo "?"; }

check_all() {
    PY_OK=false; FLASK_OK=false; TS_OK=false; TSC_OK=false; TS_WORKS=false
    CTAGS_OK=false; PORT_FREE=false

    has python3             && PY_OK=true
    py_has flask            && FLASK_OK=true
    py_has tree_sitter      && TS_OK=true
    py_has tree_sitter_c    && TSC_OK=true
    has ctags               && CTAGS_OK=true

    if $TS_OK && $TSC_OK; then
        python3 -c "
import tree_sitter_c as tsc
from tree_sitter import Language, Parser
Parser(Language(tsc.language())).parse(b'int f(void){}')
" 2>/dev/null && TS_WORKS=true
    fi

    if ! lsof -ti ":${PORT}" &>/dev/null 2>&1; then
        PORT_FREE=true
    fi
}

ok()   { echo -e "  ${G}✓${N}  $*"; }
warn() { echo -e "  ${Y}⚠${N}  $*"; }
err()  { echo -e "  ${R}✗${N}  $*"; }
info() { echo -e "  ${D}    $*${N}"; }

# ── Header ────────────────────────────────────────────────────
header() {
    clear
    echo -e "${C}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║       ✦  Callgraph Studio  v1.3          ║"
    echo "  ║       C · Interactive Call Graph         ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${N}"
}

# ── Status screen ─────────────────────────────────────────────
show_status() {
    check_all
    echo -e "  ${W}System Status${N}"
    echo "  ──────────────────────────────────────────"

    # Python
    if $PY_OK; then
        ok "python3       $(python3 --version 2>&1 | cut -d' ' -f2)"
    else
        err "python3       not found  →  install from python.org"
    fi

    # Flask
    if $FLASK_OK; then
        ok "flask         $(py_ver flask)"
    else
        err "flask         not installed"
        info "pip install flask"
    fi

    # tree-sitter
    if $TS_OK; then
        ok "tree-sitter   $(py_ver tree_sitter)"
    else
        err "tree-sitter   not installed"
        info "pip install tree-sitter"
    fi

    # tree-sitter-c
    if $TSC_OK; then
        ok "tree-sitter-c $(py_ver tree_sitter_c)"
    else
        err "tree-sitter-c not installed"
        info "pip install tree-sitter-c"
    fi

    # Runtime test
    if $TS_WORKS; then
        ok "parser test   tree-sitter parses C correctly"
    elif $TS_OK && $TSC_OK; then
        warn "parser test   installed but runtime check failed"
        info "Try: pip install --upgrade tree-sitter tree-sitter-c"
    fi

    # ctags (optional)
    if $CTAGS_OK; then
        ok "ctags         $(ctags --version 2>&1 | head -1 | cut -c1-40)"
    else
        warn "ctags         not found  (optional)"
        info "apt install universal-ctags"
    fi

    # Port
    echo ""
    if $PORT_FREE; then
        ok "port ${PORT}       free"
    else
        warn "port ${PORT}       in use"
        info "PID: $(lsof -ti :${PORT} 2>/dev/null | head -1)"
    fi

    echo ""
    # Ready?
    if $PY_OK && $FLASK_OK && $TS_WORKS; then
        echo -e "  ${G}● Ready to launch${N}"
    else
        echo -e "  ${R}● Not ready — resolve errors above${N}"
    fi
    echo "  ──────────────────────────────────────────"
}

# ── Install menu ──────────────────────────────────────────────
install_menu() {
    header
    echo -e "  ${W}Install Dependencies${N}"
    echo "  ──────────────────────────────────────────"
    echo ""
    echo "  Copy and run the commands for your system:"
    echo ""
    echo -e "  ${W}Ubuntu / Debian${N}"
    echo -e "  ${D}  sudo apt update"
    echo -e "  ${D}  sudo apt install python3 python3-pip universal-ctags"
    echo -e "  ${D}  pip install flask tree-sitter tree-sitter-c${N}"
    echo ""
    echo -e "  ${W}Fedora / RHEL${N}"
    echo -e "  ${D}  sudo dnf install python3 python3-pip ctags"
    echo -e "  ${D}  pip install flask tree-sitter tree-sitter-c${N}"
    echo ""
    echo -e "  ${W}Arch Linux${N}"
    echo -e "  ${D}  sudo pacman -S python python-pip ctags"
    echo -e "  ${D}  pip install flask tree-sitter tree-sitter-c${N}"
    echo ""
    echo -e "  ${W}macOS (Homebrew)${N}"
    echo -e "  ${D}  brew install python universal-ctags"
    echo -e "  ${D}  pip install flask tree-sitter tree-sitter-c${N}"
    echo ""
    echo -e "  ${W}virtualenv (any OS)${N}"
    echo -e "  ${D}  python3 -m venv .venv && source .venv/bin/activate"
    echo -e "  ${D}  pip install flask tree-sitter tree-sitter-c${N}"
    echo ""
    echo "  ──────────────────────────────────────────"
    echo "  Press Enter to return to menu"
    read -r
}

# ── Port menu ─────────────────────────────────────────────────
port_menu() {
    header
    echo -e "  ${W}Port Configuration${N}"
    echo "  ──────────────────────────────────────────"
    echo ""
    echo -e "  Current port: ${W}${PORT}${N}"
    echo ""

    local pid
    pid=$(lsof -ti ":${PORT}" 2>/dev/null | head -1 || true)
    if [[ -n "$pid" ]]; then
        echo -e "  ${Y}Port ${PORT} is in use by PID ${pid}${N}"
        echo ""
        echo "  [1] Kill process on port ${PORT}"
        echo "  [2] Use a different port"
        echo "  [3] Back"
        echo ""
        read -rp "  Choice: " ans
        case "$ans" in
            1)
                kill -9 "$pid" 2>/dev/null && echo -e "  ${G}Killed PID ${pid}${N}" || echo -e "  ${R}Failed (try sudo)${N}"
                sleep 0.5
                ;;
            2)
                read -rp "  New port: " newport
                [[ "$newport" =~ ^[0-9]+$ ]] && PORT="$newport" && echo -e "  ${G}Port set to ${PORT}${N}"
                ;;
        esac
    else
        echo -e "  ${G}Port ${PORT} is free${N}"
        echo ""
        echo "  [1] Use a different port"
        echo "  [2] Back"
        echo ""
        read -rp "  Choice: " ans
        case "$ans" in
            1)
                read -rp "  New port: " newport
                [[ "$newport" =~ ^[0-9]+$ ]] && PORT="$newport" && echo -e "  ${G}Port set to ${PORT}${N}"
                ;;
        esac
    fi
}

# ── Launch ────────────────────────────────────────────────────
do_launch() {
    check_all
    if ! $PY_OK; then
        echo -e "  ${R}✗ python3 not found — cannot launch${N}"; sleep 2; return
    fi
    if ! $FLASK_OK; then
        echo -e "  ${R}✗ flask not installed — cannot launch${N}"; sleep 2; return
    fi
    if ! $TS_WORKS; then
        echo -e "  ${Y}⚠  tree-sitter not working — indexing will fail${N}"
        echo -e "  ${D}  Launch anyway? (y/N) ${N}"
        read -rp "  " ans
        [[ "${ans,,}" != "y" ]] && return
    fi
    echo ""
    echo -e "  ${G}Launching...${N}"
    echo -e "  ${W}➜  http://localhost:${PORT}${N}"
    echo ""
    cd "$SCRIPT_DIR"
    exec python3 "$SCRIPT_DIR/server.py"
}

# ── Diagnostics ───────────────────────────────────────────────
diag_menu() {
    header
    echo -e "  ${W}Diagnostics${N}"
    echo "  ──────────────────────────────────────────"
    echo ""

    echo -e "  ${D}Python path:${N}"
    echo "    $(which python3 2>/dev/null || echo 'not found')"
    echo ""

    echo -e "  ${D}Pip packages (relevant):${N}"
    python3 -m pip list 2>/dev/null | grep -iE "flask|tree.sitter" | \
        while read -r line; do echo "    $line"; done
    echo ""

    echo -e "  ${D}tree-sitter parse test:${N}"
    python3 -c "
import tree_sitter_c as tsc
from tree_sitter import Language, Parser
p = Parser(Language(tsc.language()))
t = p.parse(b'volatile int x=0; void f(void){ x++; }')
fns = [n for n in t.root_node.children if n.type=='function_definition']
print(f'    parsed ok — {len(fns)} function(s) found')
" 2>&1 | while read -r line; do echo "    $line"; done
    echo ""

    echo -e "  ${D}server.py:${N}  $(wc -l < "$SCRIPT_DIR/server.py" 2>/dev/null || echo '?') lines"
    echo -e "  ${D}analyzer.py:${N} $(wc -l < "$SCRIPT_DIR/analyzer.py" 2>/dev/null || echo 'NOT FOUND — required')"
    echo -e "  ${D}index.html:${N}  $(wc -l < "$SCRIPT_DIR/index.html" 2>/dev/null || echo '?') lines"
    echo ""
    echo "  ──────────────────────────────────────────"
    echo "  Press Enter to return"
    read -r
}

# ── About ─────────────────────────────────────────────────────
about_menu() {
    header
    echo -e "  ${W}About Callgraph Studio${N}"
    echo "  ──────────────────────────────────────────"
    echo ""
    echo "  Version     1.3.0"
    echo "  License     MIT"
    echo ""
    echo -e "  ${W}Architecture${N}"
    echo "  ┌─────────────────────────────────────┐"
    echo "  │  index.html   — SVG renderer, all UI │"
    echo "  │  server.py    — Flask backend         │"
    echo "  │  analyzer.py  — tree-sitter engine    │"
    echo "  │  start.sh     — this launcher         │"
    echo "  └─────────────────────────────────────┘"
    echo ""
    echo -e "  ${W}Parser${N}       tree-sitter (replaces cflow)"
    echo -e "  ${W}Analysis${N}     call graph · globals · races"
    echo "               RTOS · peripherals"
    echo -e "  ${W}Export${N}       SVG · PNG"
    echo -e "  ${W}Persistence${N}  localStorage (24h session)"
    echo ""
    echo "  ──────────────────────────────────────────"
    echo "  Press Enter to return"
    read -r
}

# ── Main menu loop ────────────────────────────────────────────
while true; do
    header
    show_status
    echo ""
    echo -e "  ${W}Menu${N}"
    echo ""
    echo "  [1] Launch"
    echo "  [2] Install instructions"
    echo "  [3] Port settings"
    echo "  [4] Diagnostics"
    echo "  [5] About"
    echo "  [q] Quit"
    echo ""
    read -rp "  Choice: " choice

    case "$choice" in
        1) do_launch ;;
        2) install_menu ;;
        3) port_menu ;;
        4) diag_menu ;;
        5) about_menu ;;
        q|Q) echo ""; exit 0 ;;
        *) ;;
    esac
done
