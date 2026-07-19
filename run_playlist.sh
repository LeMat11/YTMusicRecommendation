#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

# If you ever use a virtualenv, you could do:
# source .venv/bin/activate

PYTHON_BIN="${PYTHON_BIN:-python3}"
exec "$PYTHON_BIN" main.py
