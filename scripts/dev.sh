#!/bin/bash
# Start KIRA in development mode
set -e

# Ensure Docker services are running
docker compose up -d

# Get local IP for phone access
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

# Start backend (bind to all interfaces)
echo "Starting KIRA server..."
(cd packages/server && uvicorn kira.server.app:create_app --factory --reload --host 0.0.0.0 --port 8750) &
BACKEND_PID=$!

# Start frontend dev server
echo "Starting KIRA client..."
(cd packages/client && npm run dev -- --host) &
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
