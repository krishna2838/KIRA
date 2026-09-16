#!/bin/bash
# Launch the KIRA menu-bar app.
#
# Boots docker services if they're not running, activates .venv, then
# hands control to `python -m kira.app`. The menu-bar app itself starts
# the FastAPI server (subprocess) and the voice pipeline (in-process on a
# background asyncio loop).
set -e

cd "$(dirname "$0")/.."

# 1. Docker services.
if command -v docker &> /dev/null; then
    if ! docker compose ps --status running --services 2>/dev/null | grep -q postgres; then
        echo "Starting Docker services..."
        docker compose up -d
    fi
else
    echo "docker not found — KIRA needs Postgres + Redis."
    exit 1
fi

# 2. Virtualenv.
if [ ! -d .venv ]; then
    echo ".venv missing — run bash scripts/setup.sh first."
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Guarantee the src-layout `kira` package is importable for the app AND for
# the uvicorn subprocess it spawns (the child inherits this env).
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

# 3. Make sure the Web UI is built (the server serves packages/client/dist).
if [ ! -f packages/client/dist/index.html ]; then
    echo "Web UI not built — building now..."
    ( cd packages/client && npx vite build ) || echo "  (build failed; Web UI won't load — run scripts/setup.sh)"
fi

# 4. Banner with the URLs the user can open anywhere on the LAN.
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  KIRA is starting — menu bar + voice + web UI          ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Say 'Hey Jarvis' to talk to KIRA by voice.            ║"
echo "║                                                        ║"
printf "║  Web UI:  %-44s║\n" "http://localhost:8750"
printf "║  Phone:   %-44s║\n" "http://$LAN_IP:8750"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# 5. Run the menu-bar app. It spawns the server + voice loop.
exec python -m kira.app
