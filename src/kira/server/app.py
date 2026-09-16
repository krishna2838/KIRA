"""FastAPI application factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from kira.core.config import get_config
from kira.core.logger import get_logger


logger = get_logger("server.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from kira.memory.db import get_db
    from kira.brain.ollama_client import OllamaClient
    from kira.brain.gemini_client import GeminiClient
    from kira.brain.router import ModelRouter

    config = get_config()

    # Core dependency: PostgreSQL. If it's unreachable we still start in a
    # DEGRADED mode (db=None) so /health can report it and the process
    # stays up instead of crash-looping.
    db = None
    try:
        db = await get_db()
    except Exception as e:
        logger.warning(f"Database unavailable — starting DEGRADED (no memory/chat persistence): {e}")

    # Run migrations (best-effort; import is guarded because `scripts` isn't
    # part of the installed package).
    if db is not None:
        try:
            import importlib.util
            from pathlib import Path
            mig_path = Path(__file__).resolve().parents[3] / "scripts" / "migrate.py"
            spec = importlib.util.spec_from_file_location("_kira_migrate", mig_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                await mod.run_migrations(db)
        except Exception as e:
            logger.warning(f"Migration warning: {e}")

    ollama = OllamaClient()

    api_key = (config.models.cloud.api_key or "").strip()
    if api_key:
        gemini = GeminiClient(api_key=api_key, model=config.models.cloud.model)
        logger.info("Cloud tier enabled (Gemini configured)")
    else:
        gemini = None
        logger.info("Cloud tier disabled — no GEMINI_API_KEY set; running Ollama-only")

    router = ModelRouter(config, ollama, gemini)

    # Keep the fast model warm; page smart in on first SMART routing.
    from kira.brain.preloader import ModelPreloader
    preloader = ModelPreloader(
        ollama,
        fast_model=config.models.fast.model,
        smart_model=config.models.smart.model,
    )
    try:
        await preloader.start()
    except Exception as e:
        logger.debug(f"preloader start failed: {e}")
    app.state.preloader = preloader

    # Tools subsystem — built-in MCP servers + external MCPs from config.
    from kira.memory.embeddings import EmbeddingEngine
    from kira.tools.bootstrap import build_tools_stack

    embeddings = EmbeddingEngine(ollama, config.models.embeddings.model)
    try:
        tool_registry, tool_router, tool_executor, tool_extras = await build_tools_stack(
            config, embeddings, db, model_router=router
        )
    except Exception as e:
        logger.warning(f"Tools subsystem failed to boot: {e}")
        tool_registry = tool_router = tool_executor = None
        tool_extras = {}

    app.state.db = db
    app.state.ollama = ollama
    app.state.gemini = gemini
    app.state.router = router
    app.state.config = config
    app.state.embeddings = embeddings
    app.state.tool_registry = tool_registry
    app.state.tool_router = tool_router
    app.state.tool_executor = tool_executor
    app.state.document_store = tool_extras.get("document_store")
    app.state.document_indexer = tool_extras.get("document_indexer")
    app.state.notifications_store = tool_extras.get("notifications_store")
    app.state.scheduler = tool_extras.get("scheduler")
    app.state.proactive_engine = tool_extras.get("proactive_engine")
    _proactive_from_monitor = tool_extras.get("proactive_from_monitor")
    app.state.deadlines = tool_extras.get("deadlines")
    monitor = tool_extras.get("monitor")
    app.state.monitor = monitor
    if monitor is not None:
        try:
            monitor.start()
        except Exception as e:
            logger.warning(f"monitor start failed: {e}")

    # macOS Notification Center observer — best-effort, streams into the store.
    nc_observer = None
    nc_drain_task = None
    if app.state.notifications_store is not None:
        try:
            from kira.tools.notifications.nc_observer import NCObserver, drain_into_store
            loop = asyncio.get_event_loop()
            nc_observer = NCObserver(loop)
            nc_observer.start()
            if nc_observer.available():
                stop_evt = asyncio.Event()
                nc_drain_task = asyncio.create_task(
                    drain_into_store(nc_observer, app.state.notifications_store, stop_event=stop_evt),
                    name="kira-nc-drain",
                )
                app.state.nc_stop_event = stop_evt
        except Exception as e:
            logger.debug(f"NC observer not started: {e}")
    app.state.nc_observer = nc_observer
    app.state.nc_drain_task = nc_drain_task

    # Documents: auto-index on startup + file watcher.
    doc_watcher = None
    doc_watch_task = None
    doc_index_task = None
    if app.state.document_indexer is not None:
        try:
            from kira.tools.documents.watcher import DocumentWatcher, drain_into_indexer
            loop = asyncio.get_event_loop()
            watched = [str(p) for p in config.documents.watched_directories]
            if watched:
                dw = DocumentWatcher(loop)
                if dw.start(watched):
                    stop_evt = asyncio.Event()
                    doc_watch_task = asyncio.create_task(
                        drain_into_indexer(dw, app.state.document_indexer, stop_event=stop_evt),
                        name="kira-doc-watch",
                    )
                    app.state.doc_watch_stop = stop_evt
                    doc_watcher = dw
                if config.documents.auto_index_on_startup:
                    async def _initial_index():
                        for root in watched:
                            try:
                                await app.state.document_indexer.index_directory(root)
                            except Exception as e:
                                logger.debug(f"initial index of {root} failed: {e}")
                    doc_index_task = asyncio.create_task(_initial_index(), name="kira-doc-init")
        except Exception as e:
            logger.warning(f"Document watcher/indexer failed: {e}")
    app.state.doc_watcher = doc_watcher
    app.state.doc_watch_task = doc_watch_task
    app.state.doc_index_task = doc_index_task

    # Voice pipeline
    voice_pipeline = None
    try:
        from kira.voice.bootstrap import build_pipeline
        from kira.server.voice_reply import make_voice_reply

        voice_reply = make_voice_reply(app)
        voice_pipeline = build_pipeline(config, ollama, voice_reply)
    except Exception as e:
        logger.warning(f"Voice pipeline unavailable: {e}")
    app.state.voice_pipeline = voice_pipeline

    # Startup summary — which subsystems came up, which are degraded.
    def _ok(v) -> str:
        return "up" if v else "DEGRADED"
    summary = {
        "database": _ok(db is not None),
        "ollama": "up",  # client always constructs; reachability shown in /health
        "cloud": _ok(gemini is not None),
        "tools": _ok(tool_registry is not None),
        "documents": _ok(app.state.document_indexer is not None),
        "voice": _ok(voice_pipeline is not None),
        "scheduler": _ok(app.state.scheduler is not None),
        "monitor": _ok(monitor is not None),
    }
    logger.info(
        "KIRA server started — subsystems: "
        + ", ".join(f"{k}={v}" for k, v in summary.items())
    )
    app.state.startup_summary = summary

    try:
        yield
    finally:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception:
                pass
        if monitor is not None:
            try:
                await monitor.stop()
            except Exception:
                pass
        if nc_observer is not None:
            try:
                nc_observer.stop()
            except Exception:
                pass
        if nc_drain_task is not None:
            nc_drain_task.cancel()
            try:
                await nc_drain_task
            except (Exception, asyncio.CancelledError):
                pass
        if voice_pipeline is not None:
            try:
                await voice_pipeline.stop()
            except Exception:
                pass
        if doc_watcher is not None:
            try:
                doc_watcher.stop()
            except Exception:
                pass
        for task in (doc_watch_task, doc_index_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (Exception, asyncio.CancelledError):
                    pass
        preloader = getattr(app.state, "preloader", None)
        if preloader is not None:
            try:
                await preloader.stop()
            except Exception:
                pass
        if tool_registry is not None:
            try:
                await tool_registry.close()
            except Exception:
                pass
        await ollama.close()
        if gemini is not None:
            await gemini.close()
        await db.disconnect()
        logger.info("KIRA server stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="KIRA",
        description="Personal AI Assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Allow any device on the local home network + Tauri webview.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|"
            r"10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?|tauri://localhost)$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from kira.server.routes import (
        chat,
        memory as memory_route,
        health,
        config as config_route,
        tools as tools_route,
        voice as voice_route,
        research as research_route,
        auth as auth_route,
        today as today_route,
        notifications as notifications_route,
        documents as documents_route,
        scheduler as scheduler_route,
        proactive as proactive_route,
        audit as audit_route,
        factcheck as factcheck_route,
        chat_stream as chat_stream_route,
        conversations as conversations_route,
    )
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(memory_route.router, prefix="/api")
    app.include_router(config_route.router, prefix="/api")
    app.include_router(tools_route.router, prefix="/api")
    app.include_router(voice_route.router, prefix="/api")
    app.include_router(research_route.router, prefix="/api")
    app.include_router(auth_route.router, prefix="/api")
    app.include_router(today_route.router, prefix="/api")
    app.include_router(notifications_route.router, prefix="/api")
    app.include_router(documents_route.router, prefix="/api")
    app.include_router(scheduler_route.router, prefix="/api")
    app.include_router(proactive_route.router, prefix="/api")
    app.include_router(audit_route.router, prefix="/api")
    app.include_router(factcheck_route.router, prefix="/api")
    app.include_router(chat_stream_route.router, prefix="/api")
    app.include_router(conversations_route.router, prefix="/api")

    # Serve React SPA build if present. This lets phones on the LAN load the UI
    # from the same origin as the API.
    # src/kira/server/app.py → parents[3] = repo root
    client_dist = Path(__file__).resolve().parents[3] / "packages" / "client" / "dist"
    if client_dist.exists():
        assets_dir = client_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            file_path = client_dist / path
            if path and file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(client_dist / "index.html")

    return app
