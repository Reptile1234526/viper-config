#!/usr/bin/env bash
set -e

echo "=== Viper Mini Config — installer ==="

# Ensure Python 3.10+ is available
if ! command -v python3 &>/dev/null; then
    echo "Python 3 not found. Install via: brew install python"
    exit 1
fi

PY=$(python3 -c "import sys; print(sys.version_info >= (3,10))")
if [ "$PY" != "True" ]; then
    echo "Python 3.10+ required. Current: $(python3 --version)"
    exit 1
fi

# Create and activate venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "Installation complete!"
echo ""
echo "IMPORTANT — Before running, grant Accessibility access:"
echo "  System Settings → Privacy & Security → Accessibility"
echo "  Add Terminal (or your Python binary) to the list."
echo ""
echo "Run with:  source .venv/bin/activate && python main.py"
