#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the Terrabot repo-aware infra assistant.
# Creates a Python virtualenv with the Azure Functions backend + terrabot CLI,
# and installs Azure Functions Core Tools so the Functions host can run locally.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# 1. System package needed to create Python virtualenvs on the base image.
if ! python3 -m venv --help >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv "python3.$(python3 -c 'import sys; print(sys.version_info.minor)')-venv" || \
    sudo apt-get install -y -qq python3-venv
fi

# 2. Python virtualenv with runtime + dev dependencies and the editable CLI package.
# Recreate the venv if it is missing or points at a stale/incompatible interpreter.
if ! .venv/bin/python --version >/dev/null 2>&1; then
  rm -rf .venv
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .        # exposes the `terrabot` console script
pip install pytest      # test runner used by the repo test suite

# 3. Azure Functions Core Tools v4 (standalone binary, avoids authenticated npm feed).
FUNC_VERSION="4.14.0"
FUNC_DIR="$HOME/.local/func"
if [ "$("$FUNC_DIR/func" --version 2>/dev/null)" != "$FUNC_VERSION" ]; then
  tmp="$(mktemp -d)"
  curl -sSL -o "$tmp/func.zip" \
    "https://github.com/Azure/azure-functions-core-tools/releases/download/${FUNC_VERSION}/Azure.Functions.Cli.linux-x64.${FUNC_VERSION}.zip"
  rm -rf "$FUNC_DIR"
  mkdir -p "$FUNC_DIR"
  unzip -oq "$tmp/func.zip" -d "$FUNC_DIR"
  chmod +x "$FUNC_DIR/func" "$FUNC_DIR/gozip" 2>/dev/null || true
  rm -rf "$tmp"
fi
mkdir -p "$HOME/.local/bin"
ln -sf "$FUNC_DIR/func" "$HOME/.local/bin/func"

echo "Terrabot environment ready. Activate with: source .venv/bin/activate"
