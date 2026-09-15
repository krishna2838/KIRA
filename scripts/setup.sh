#!/bin/bash
set -e

echo "Setting up KIRA..."

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Install from https://ollama.com/download"
    exit 1
fi

# Pull models (names come from the spec — swap if the tags aren't present locally)
echo "Pulling fast model (gemma4:e2b)..."
ollama pull gemma4:e2b || echo "  (skipped; adjust config/default.yaml if needed)"

echo "Pulling smart model (gemma3:8b)..."
ollama pull gemma3:8b || echo "  (skipped)"

echo "Pulling embedding model..."
ollama pull nomic-embed-text

# Start infrastructure
echo "Starting PostgreSQL + Redis..."
docker compose up -d

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
sleep 5

# Install Python packages (editable)
echo "Installing Python packages..."
pip install -e packages/core
pip install -e packages/brain
pip install -e packages/memory
pip install -e packages/tools
pip install -e packages/voice
pip install -e packages/server

# Run migrations
echo "Running database migrations..."
python scripts/migrate.py

# Install Playwright's Chromium (for browser automation)
echo "Installing Playwright Chromium…"
python -m playwright install chromium || echo "  (skip if already installed)"

# Prompt for macOS Accessibility permission — required for the a11y tree
# and reliable AppleScript control of other apps.
if [ "$(uname)" = "Darwin" ]; then
  echo ""
  echo "==================================================================="
  echo "  macOS Accessibility permission is REQUIRED for KIRA to read the"
  echo "  UI tree and drive other apps."
  echo "  Open: System Settings → Privacy & Security → Accessibility"
  echo "  and add your Terminal / Tauri app / Python interpreter."
  echo "==================================================================="
  read -r -p "Open System Settings there now? [y/N] " openit
  if [[ "$openit" =~ ^[Yy]$ ]]; then
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  fi
fi

# Install frontend
echo "Installing frontend..."
cd packages/client && npm install && cd ../..

# Create .env from example. GEMINI_API_KEY is OPTIONAL — KIRA runs
# fully on Ollama without it. Fill it in later if you want cloud/vision.
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env (GEMINI_API_KEY is optional; leave blank to run local-only)"
fi

# Install Rust (for Tauri)
if ! command -v rustc &> /dev/null; then
    echo "Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Install Tauri CLI
if ! cargo tauri --version &> /dev/null; then
    echo "Installing Tauri CLI..."
    cargo install tauri-cli --version "^2.0"
fi

echo ""
echo "KIRA setup complete."
echo "  Web:        bash scripts/dev.sh"
echo "  Desktop:    cargo tauri dev"
echo "  Build .dmg: cargo tauri build"
