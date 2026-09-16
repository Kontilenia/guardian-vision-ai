#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="$(basename "$PWD")"
VENV_DIR="$HOME/.venvs/$PROJECT_NAME"
REQUIREMENTS="src/requirements.txt"
UPGRADE_PIP="${UPGRADE_PIP:-1}"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR..."
  python -m venv "$VENV_DIR"
else
  echo "Virtual environment already exists in $VENV_DIR, skipping creation."
fi

# Non-fatal: a self-update failure (e.g. offline/blocked PyPI) must not break setup.
if [ "$UPGRADE_PIP" = "1" ]; then
  echo "Upgrading pip..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip || echo "WARNING: pip upgrade failed (continuing with bundled pip)."
else
  echo "Skipping pip upgrade (UPGRADE_PIP=$UPGRADE_PIP)."
fi

if [ -f "$REQUIREMENTS" ]; then
  echo "Installing dependencies from $REQUIREMENTS..."
  "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS"
else
  echo "No $REQUIREMENTS found, skipping dependency install."
fi

echo "Setup complete."
