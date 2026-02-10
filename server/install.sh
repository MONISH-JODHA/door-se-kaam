#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  Door Se Kaam — Installation Script
# ═══════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         🖥️  Door Se Kaam  📱               ║"
echo "║    Remote Desktop Controller — Installer     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Check Python version ────────────────────────────────
echo "▸ Checking Python version..."
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            echo "  ✔ Found $cmd ($version)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ✘ Python 3.10+ is required but not found."
    echo "    Install with: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# ── Check system dependencies ───────────────────────────
echo ""
echo "▸ Checking system dependencies..."

MISSING_DEPS=()

# Check for pip
if ! "$PYTHON" -m pip --version &> /dev/null; then
    MISSING_DEPS+=("python3-pip")
fi

# Check for venv
if ! "$PYTHON" -m venv --help &> /dev/null 2>&1; then
    MISSING_DEPS+=("python3-venv")
fi

# Optional: xdotool (fallback input on some systems)
if ! command -v xdotool &> /dev/null; then
    echo "  ⚠ xdotool not found (optional, for fallback input handling)"
    echo "    Install with: sudo apt install xdotool"
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "  ✘ Missing required packages: ${MISSING_DEPS[*]}"
    echo ""
    # Detect package manager
    if command -v apt &> /dev/null; then
        echo "  Run: sudo apt install ${MISSING_DEPS[*]}"
    elif command -v dnf &> /dev/null; then
        echo "  Run: sudo dnf install ${MISSING_DEPS[*]}"
    elif command -v pacman &> /dev/null; then
        echo "  Run: sudo pacman -S ${MISSING_DEPS[*]}"
    fi
    exit 1
fi

echo "  ✔ All required dependencies found"

# ── Create virtual environment ──────────────────────────
echo ""
echo "▸ Setting up Python virtual environment..."

if [ -d "$VENV_DIR" ]; then
    echo "  ℹ Virtual environment already exists at $VENV_DIR"
    read -p "  Recreate? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        "$PYTHON" -m venv "$VENV_DIR"
        echo "  ✔ Virtual environment recreated"
    fi
else
    "$PYTHON" -m venv "$VENV_DIR"
    echo "  ✔ Virtual environment created at $VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# ── Install Python packages ────────────────────────────
echo ""
echo "▸ Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  ✔ All packages installed"

# ── Set initial password ────────────────────────────────
echo ""
DATA_DIR="$SCRIPT_DIR/data"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/password.hash" ]; then
    echo "▸ Set an access password for remote connections:"
    read -s -p "  Enter password (min 4 chars): " PASSWORD
    echo
    read -s -p "  Confirm password: " PASSWORD2
    echo

    if [ "$PASSWORD" != "$PASSWORD2" ]; then
        echo "  ✘ Passwords don't match. You can set it later."
    elif [ ${#PASSWORD} -lt 4 ]; then
        echo "  ✘ Password too short. You can set it later via the web UI."
    else
        python -c "
from auth import auth_manager
result = auth_manager.set_password('$PASSWORD')
print('  ✔ Password configured!' if result else '  ✘ Failed to set password')
"
    fi
else
    echo "  ℹ Password already configured"
fi

# ── Summary ─────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Installation complete!"
echo ""
echo "  To start the server:"
echo "    cd $SCRIPT_DIR"
echo "    source .venv/bin/activate"
echo "    python main.py"
echo ""
echo "  Or use the quick-start command:"
echo "    $VENV_DIR/bin/python $SCRIPT_DIR/main.py"
echo ""
echo "  The server will display the URL to open"
echo "  on your phone's browser."
echo "═══════════════════════════════════════════════"
echo ""
