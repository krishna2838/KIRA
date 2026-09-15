# KIRA

A local-first, MCP-native, memory-centric personal AI operating system.

**Target:** MacBook Air M4, 16GB RAM, macOS Tahoe 26.6.2

## Phase 0 + Phase 1 scope

- Foundation: config, logging, types, redaction, permissions
- Brain: model router (Ollama fast/smart + Gemini cloud), intent classifier, prompts
- Memory: knowledge graph, long-term memory store, conversations, working context (pgvector)
- Server: FastAPI gateway with chat, memory, health endpoints
- Client: React + Vite + Tailwind chat UI with memory viewer
- Desktop: Tauri v2 wrapper for native macOS app + system tray
- Network: bind to LAN so phone/other devices on the same WiFi can talk to KIRA

## Quick start

```bash
bash scripts/setup.sh
bash scripts/dev.sh
```

Then either open http://localhost:5173 in a browser, run `cargo tauri dev` for the desktop app, or open `http://<mac-lan-ip>:8750` from your phone on the same WiFi.

See `CLAUDE.md` for the full build spec.

## Notes

- Requires Python 3.11+ (uses `str | None` PEP 604 syntax). If you're on 3.9/3.10, `brew install python@3.12`.
- `src-tauri/icons/` ships with placeholder cyan squares. Before `cargo tauri build`, regenerate real icons with `cargo tauri icon path/to/logo.png`.
- The Ollama model tags in `config/default.yaml` (`gemma4:e2b`, `gemma3:8b`) come from the spec — swap them for whichever tags you have pulled locally.
- The server binds to `0.0.0.0:8750` so devices on your LAN can reach it. On public WiFi, set `KIRA_SERVER_NETWORK_MODE=public` (or edit the config) and switch the host back to `127.0.0.1`.

## Layout

```
kira/
├── CLAUDE.md              spec
├── config/default.yaml    layered config (env + ~/.kira/config.yaml override)
├── docker-compose.yml     PostgreSQL (+pgvector) + Redis
├── src-tauri/             native macOS desktop wrapper (Tauri v2)
├── scripts/               setup.sh, dev.sh, migrate.py
├── packages/
│   ├── core                types, config, redaction, permissions, logger
│   ├── brain               router, Ollama/Gemini clients, intent, prompts
│   ├── memory              db, embeddings, graph, store, conversations, context
│   ├── server              FastAPI app + /api/chat, /api/memory, /health
│   └── client              React + Vite + Tailwind + Zustand
├── evals/                 YAML cases + runner
└── tests/                 pytest suites (redaction, permissions, router, memory, config)
```

