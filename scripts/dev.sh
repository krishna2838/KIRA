#!/bin/bash
# Start KIRA in development mode
set -e

cd "$(dirname "$0")/.."

# Activate the project virtualenv.
if [ ! -d .venv ]; then
    echo ".venv missing — run bash scripts/setup.sh first."
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Guarantee `kira` is importable for uvicorn regardless of editable-install
# .pth quirks on macOS.
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

# Ensure Docker services are running
docker compose up -d

# Get local IP for phone access
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

# Start backend (bind to all interfaces). The `kira` package lives under
# src/ and is installed editable — no need to `cd` anywhere.
echo "Starting KIRA server..."
uvicorn kira.server.app:create_app --factory --reload --host 0.0.0.0 --port 8750 &
BACKEND_PID=$!

# Start frontend dev server. Use `npx vite` directly rather than
# `npm run dev` so we bypass any missing/broken `dev` script and get
# Vite from the local node_modules regardless of PATH.
echo "Starting KIRA client..."
(cd packages/client && npx vite --host) &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║              KIRA is running                     ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Desktop dev:  http://localhost:5173             ║"
echo "║  API:          http://localhost:8750             ║"
printf "║  Phone/LAN:    http://%-27s║\n" "${LOCAL_IP}:8750"
echo "╚══════════════════════════════════════════════════╝"
echo ""

wait
