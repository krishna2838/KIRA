#!/bin/bash
set -e

cd "$(dirname "$0")/.."
echo "Setting up KIRA..."

# Require python3.12 (the project targets 3.11+; we standardize on 3.12).
if ! command -v python3.12 &> /dev/null; then
    echo "python3.12 not found. Install it (e.g. 'brew install python@3.12')."
    exit 1
fi

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Install from https://ollama.com/download"
    exit 1
fi

# Pull models (names come from the spec — swap if the tags aren't present locally)
echo "Pulling fast model (gemma4:e2b)..."
ollama pull gemma4:e2b || echo "  (skipped; adjust config/default.yaml if needed)"

echo "Pulling smart model (qwen3:30b-a3b)..."
ollama pull qwen3:30b-a3b || echo "  (skipped)"

echo "Pulling embedding model..."
ollama pull nomic-embed-text

# Ensure .env exists so docker-compose + config pick up the same
# POSTGRES_PASSWORD (config/default.yaml reads it via ${POSTGRES_PASSWORD}).
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env (GEMINI_API_KEY is optional; leave blank to run local-only)"
fi

# Reset infrastructure fresh — the Postgres volume may have been
# created with a different password. Wipe it and let migrate.py rebuild.
echo "Resetting PostgreSQL + Redis (destructive)..."
docker compose down -v || true
docker compose up -d

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
sleep 5

# Create + activate the project virtualenv.
if [ ! -d .venv ]; then
    echo "Creating .venv..."
    python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip

# One editable install for the whole `kira` package.
echo "Installing kira (editable)..."
pip install -e .

# Robust importability: setuptools' auto-generated __editable__ .pth is not
# reliably honored on recent macOS (com.apple.provenance xattr), so write a
# plain kira.pth that site.py always processes.
SITE_PACKAGES="$(python -c 'import site; print(site.getsitepackages()[0])')"
rm -f "$SITE_PACKAGES"/__editable__.kira-*.pth
printf '%s\n' "$(pwd)/src" > "$SITE_PACKAGES/kira.pth"
python -c "import kira; print('kira importable at', kira.__file__)"

# Run migrations (migrate.py self-bootstraps src/ onto sys.path too).
echo "Running database migrations..."
PYTHONPATH="$(pwd)/src${PYTHONPATH:+:$PYTHONPATH}" python scripts/migrate.py

# Voice assets — wake word models (onnx) + a Piper TTS voice, so the voice
# pipeline is fully functional out of the box.
echo "Downloading wake-word models (openWakeWord, onnx)…"
python -c "from openwakeword.utils import download_models; download_models()" 2>/dev/null \
    || echo "  (skip — download later on first run)"

PIPER_DIR="$HOME/.kira/piper"
PIPER_ONNX="$PIPER_DIR/en_US-lessac-medium.onnx"
if [ ! -f "$PIPER_ONNX" ]; then
    echo "Downloading Piper voice (en_US-lessac-medium, ~63MB)…"
    mkdir -p "$PIPER_DIR"
    BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
    curl -sL "$BASE/en_US-lessac-medium.onnx"      -o "$PIPER_ONNX" --max-time 300 || echo "  (skip — configure config.voice.piper_voice_path later)"
    curl -sL "$BASE/en_US-lessac-medium.onnx.json" -o "$PIPER_ONNX.json" --max-time 60 || true
fi

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

# Install frontend deps and pre-build the Web UI into packages/client/dist,
# which the FastAPI server serves at http://<host>:8750.
echo "Installing + building frontend..."
( cd packages/client && npm install && npx vite build )

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

# Desktop shortcut for the menu-bar app — one double-click starts KIRA.
if [ "$(uname)" = "Darwin" ]; then
    DESKTOP="$HOME/Desktop/KIRA.command"
    if [ ! -e "$DESKTOP" ]; then
        ln -s "$(pwd)/scripts/KIRA.command" "$DESKTOP" || true
        echo "Placed a KIRA shortcut on your Desktop."
    fi
fi

echo ""
echo "KIRA setup complete."
echo "  Menu-bar app:  bash scripts/kira.sh    (or double-click ~/Desktop/KIRA.command)"
echo "  Web UI:        bash scripts/dev.sh     (optional — Chat lives at http://localhost:5173)"
echo "  Tauri desktop: cargo tauri dev         (optional — full-window app)"
