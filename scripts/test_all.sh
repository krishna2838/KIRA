#!/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate
# Guarantee the src-layout package is importable regardless of editable-install
# quirks (macOS provenance can stop the auto .pth from being honored).
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

echo "=== 1. Imports ==="
python -c "from kira.core.config import get_config; print('✓ core')"
python -c "from kira.brain.router import ModelRouter; print('✓ brain')"
python -c "from kira.memory.db import get_db; print('✓ memory')"
python -c "from kira.server.app import create_app; print('✓ server')"
python -c "import kira.tools, kira.voice; print('✓ tools + voice')"

echo "=== 2. Ollama ==="
curl -s http://localhost:11434/api/tags | python -m json.tool | grep -o '"name": "[^"]*"' | head -5

echo "=== 3. Docker ==="
docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null

echo "=== 4. Health ==="
curl -s http://localhost:8750/health | python -m json.tool

echo "=== 5. Chat ==="
echo "Sending test message (may take 60s on first run)..."
curl -s -X POST http://localhost:8750/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Say hello in one sentence"}' \
  --max-time 300 | python -c "
import sys,json
d=json.load(sys.stdin)
print('✓ Chat works!')
print('Reply:', d['message']['content'][:200])
print('Model:', d['message']['metadata'].get('model_tier','unknown'))
print('Latency:', d.get('latency_ms','?'), 'ms')
"

echo "=== All tests done ==="
