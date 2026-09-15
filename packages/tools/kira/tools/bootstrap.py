"""Wire up the tools subsystem for the server's lifespan."""
from __future__ import annotations

from kira.logger import get_logger
from kira.permissions import PermissionEngine, ToolPermission
from kira.types import RiskLevel

from kira.tools.executor import ToolExecutor
from kira.tools.mcp_client import MCPClient
from kira.tools.registry import ToolRegistry
from kira.tools.tool_router import ToolRouter
from kira.tools.types import ToolTransport


logger = get_logger("tools.bootstrap")


_BUILTIN_MODULES = {
    "filesystem": "kira.tools.servers.filesystem_server",
    "terminal": "kira.tools.servers.terminal_server",
    "web": "kira.tools.servers.web_search_server",
    "research": "kira.tools.servers.research_server",
    "browser": "kira.tools.servers.browser_server",
    "computer": "kira.tools.servers.computer_server",
    "google": "kira.tools.servers.google_server",
    "notifications": "kira.tools.servers.notifications_server",
    "life": "kira.tools.servers.life_os_server",
    "code": "kira.tools.servers.coding_server",
    "documents": "kira.tools.servers.documents_server",
}


def _load_builtin(name: str):
    import importlib
    module_path = _BUILTIN_MODULES.get(name)
    if not module_path:
        raise KeyError(f"Unknown built-in server: {name}")
    module = importlib.import_module(module_path)
    return module.SERVER


def _build_permission_engine(config) -> PermissionEngine:
    overrides: dict[str, ToolPermission] = {}
    for tool_name, spec in (config.permissions.tool_overrides or {}).items():
        risk_override = None
        if spec.risk_override is not None:
            try:
                risk_override = RiskLevel(spec.risk_override)
            except ValueError:
                risk_override = None
        overrides[tool_name] = ToolPermission(
            mode=spec.mode,
            rate_limit_per_min=spec.rate_limit_per_min,
            risk_override=risk_override,
        )
    return PermissionEngine(
        auto_approve_level=config.permissions.auto_approve_level,
        tool_overrides=overrides,
    )


async def _connect_redis(config):
    try:
        import redis.asyncio as redis_async  # type: ignore
        client = redis_async.Redis(
            host=config.database.redis.host,
            port=config.database.redis.port,
            decode_responses=True,
        )
        # Ping to verify — fail soft if Redis is down.
        await client.ping()
        return client
    except Exception as e:
        logger.info(f"Redis unavailable — tool embedding cache disabled ({e})")
        return None


async def build_tools_stack(config, embeddings, db, model_router=None):
    """Return (registry, router, executor, extras).

    extras is a dict of shared runtime handles the server may want:
      { 'notifications_store', 'deadlines', 'monitor' }

    model_router is optional; when provided, the research + notifications +
    life-OS servers get LLM summarizers, and the monitor gets meeting/email
    check hooks.
    """
    redis_client = await _connect_redis(config)

    # Configure the research server before it gets registered.
    if model_router is not None and "research" in (config.tools.enabled_builtins or []):
        try:
            from kira.tools.servers import research_server
            from kira.types import ModelTier

            fast_model = config.models.fast.model
            smart_model = config.models.smart.model

            async def _planner_generate(prompt: str) -> str:
                return await model_router.ollama.generate(
                    model=fast_model, prompt=prompt, options={"temperature": 0.2}
                )

            async def _synth_generate(prompt: str) -> str:
                return await model_router.generate(
                    ModelTier.SMART,
                    [{"role": "user", "content": prompt}],
                )

            research_server.configure(
                planner_generate=_planner_generate,
                synth_generate=_synth_generate,
                redis_client=redis_client,
            )
            logger.info(
                f"Research pipeline configured "
                f"(planner={fast_model}, synth={smart_model})"
            )
        except Exception as e:
            logger.warning(f"Research pipeline configure failed: {e}")

    # Wire the vision callable for `computer.analyze_screenshot`.
    if model_router is not None and "computer" in (config.tools.enabled_builtins or []):
        try:
            from kira.tools.computer.screen import configure_vision

            if getattr(model_router, "cloud_available", False):
                gemini = model_router.gemini

                async def _vision(image_bytes: bytes, question: str) -> str:
                    import base64
                    b64 = base64.b64encode(image_bytes).decode("ascii")
                    # Ask Gemini via a data URL preamble; the client concatenates
                    # them into a `contents` payload for us.
                    prompt = (
                        f"[Screenshot attached below as base64 PNG]\n"
                        f"{question}\n\n"
                        f"IMAGE_BASE64:\n{b64[:2000]}…(truncated)"
                    )
                    return await gemini.chat(
                        [{"role": "user", "content": prompt}]
                    )

                configure_vision(_vision)
                logger.info("Vision binding: Gemini")
            else:
                configure_vision(None)
                logger.info("Vision binding: unavailable (no cloud tier)")
        except Exception as e:
            logger.debug(f"vision binding failed: {e}")

    registry = ToolRegistry(embeddings=embeddings, redis_client=redis_client)

    for name in config.tools.enabled_builtins:
        try:
            server = _load_builtin(name)
            registry.register_internal(server)
            logger.info(f"Registered built-in server: {name} ({len(server.tools)} tools)")
        except Exception as e:
            logger.warning(f"Failed to load built-in {name}: {e}")

    for spec in config.tools.external:
        try:
            transport = ToolTransport(spec.transport)
        except ValueError:
            logger.warning(f"Unknown transport for {spec.name}: {spec.transport}")
            continue
        client = MCPClient(
            server_name=spec.name,
            transport=transport,
            command=spec.command,
            args=spec.args,
            env=spec.env,
            url=spec.url,
        )
        await registry.register_external(client)

    try:
        await registry.build_embeddings()
    except Exception as e:
        logger.warning(f"Embedding pass failed: {e}")

    permissions = _build_permission_engine(config)
    router = ToolRouter(registry, embeddings, top_k=config.tools.relevance_top_k)
    executor = ToolExecutor(registry, permissions, db=db)

    # ---- Personal-OS wiring (Phase 6) ----
    extras: dict = {}
    try:
        from kira.tools.life.deadlines import Deadlines
        from kira.tools.monitor import Monitor
        from kira.tools.notifications.store import NotificationStore
        from kira.tools.servers import google_server as gsrv
        from kira.tools.servers import life_os_server as lsrv
        from kira.tools.servers import notifications_server as nsrv

        notifications_store = NotificationStore(db=db, embeddings=embeddings)
        deadlines = Deadlines(db=db)
        extras["notifications_store"] = notifications_store
        extras["deadlines"] = deadlines

        summarize_fn = None
        if model_router is not None:
            from kira.types import ModelTier

            async def _summarize(prompt: str) -> str:
                return await model_router.generate(
                    ModelTier.SMART,
                    [{"role": "user", "content": prompt}],
                )
            summarize_fn = _summarize

        # Configure servers now that runtime deps exist.
        gsrv.configure(summarize_fn)
        nsrv.configure(notifications_store, summarize_fn)
        lsrv.configure(notifications_store, deadlines, summarize_fn)

        # Coding server needs BOTH a fast generator (keywords) and a smart
        # one (diagnosis). Skip if the model_router isn't wired.
        if model_router is not None and "code" in (config.tools.enabled_builtins or []):
            try:
                from kira.tools.servers import coding_server as csrv
                from kira.types import ModelTier

                fast_model = config.models.fast.model

                async def _fast(prompt: str) -> str:
                    return await model_router.ollama.generate(
                        model=fast_model, prompt=prompt,
                        options={"temperature": 0.1},
                    )

                async def _smart(prompt: str) -> str:
                    return await model_router.generate(
                        ModelTier.SMART,
                        [{"role": "user", "content": prompt}],
                    )

                csrv.configure(_fast, _smart)
                logger.info("Coding server configured")
            except Exception as e:
                logger.warning(f"Coding server configure failed: {e}")

        # ---- Scheduler + Proactive engine (Phase 9) ----
        try:
            from kira.tools.proactive import ProactiveEngine, from_monitor_event
            from kira.tools.scheduler import TaskScheduler, seed_defaults
            from kira.tools.types import ToolCall

            async def _dispatch(tool_name: str, args: dict):
                if executor is None:
                    raise RuntimeError("executor not initialized")
                outcome = await executor.execute(ToolCall(tool=tool_name, arguments=args or {}))
                if outcome.status == "ok" and outcome.result is not None:
                    return outcome.result.content
                if outcome.status == "needs_confirmation":
                    raise RuntimeError(f"needs confirmation: {tool_name}")
                raise RuntimeError(outcome.message or outcome.status)

            engine = ProactiveEngine(
                min_score=getattr(config.monitor, "proactive_min_score", 0.6),
            )
            if summarize_fn is not None:
                engine.set_scorer(summarize_fn)

            scheduler = TaskScheduler(db=db, dispatch=_dispatch)
            await scheduler.start()
            await seed_defaults(scheduler)

            extras["proactive_engine"] = engine
            extras["scheduler"] = scheduler
            extras["proactive_from_monitor"] = from_monitor_event
            logger.info("Scheduler + proactive engine online")
        except Exception as e:
            logger.warning(f"Scheduler / proactive setup failed: {e}")
        if "documents" in (config.tools.enabled_builtins or []) and config.documents.enabled:
            try:
                from kira.tools.documents.indexer import DocumentIndexer
                from kira.tools.documents.store import DocumentStore
                from kira.tools.servers import documents_server as dsrv

                doc_store = DocumentStore(db=db, embeddings=embeddings)
                indexer = DocumentIndexer(
                    doc_store,
                    embeddings,
                    max_file_mb=config.documents.max_file_mb,
                    parallelism=config.documents.parallelism,
                    chunk_tokens=config.documents.chunk_tokens,
                    overlap_tokens=config.documents.overlap_tokens,
                )
                dsrv.configure(doc_store, indexer, summarize_fn)
                extras["document_store"] = doc_store
                extras["document_indexer"] = indexer
                logger.info(
                    f"Documents server configured "
                    f"(watched={config.documents.watched_directories}, "
                    f"auto_index_on_startup={config.documents.auto_index_on_startup})"
                )
            except Exception as e:
                logger.warning(f"Documents server configure failed: {e}")

        # Optional Telegram / Discord.
        try:
            from kira.tools.notifications import discord_adapter, telegram_adapter
            telegram_adapter.configure(
                bot_token=(config.integrations.telegram.bot_token or None),
                allowed_chat_ids=config.integrations.telegram.allowed_chat_ids,
            )
            discord_adapter.configure(
                bot_token=(config.integrations.discord.bot_token or None),
            )
        except Exception as e:
            logger.debug(f"messaging adapters configure failed: {e}")

        # Proactive monitor
        from kira.tools.google_ws import calendar as gcal, gmail as gmail_mod
        from kira.tools.google_ws.auth import is_authenticated

        async def _events():
            if not is_authenticated():
                return []
            return await gcal.get_today_events()

        async def _unread():
            if not is_authenticated():
                return {"unread": 0}
            return await gmail_mod.get_unread_count()

        monitor = Monitor(
            get_today_events=_events,
            get_unread_count=_unread,
            notifications_store=notifications_store,
            check_interval_sec=int(getattr(config.monitor, "check_interval_sec", 300)),
        )
        extras["monitor"] = monitor
    except Exception as e:
        logger.warning(f"Personal-OS wiring failed: {e}")

    return registry, router, executor, extras
