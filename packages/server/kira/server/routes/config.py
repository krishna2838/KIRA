"""Config inspection endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config_route(req: Request):
    cfg = req.app.state.config
    # Never leak secrets (api keys, passwords)
    return {
        "kira": cfg.kira.model_dump(),
        "models": {
            "fast": cfg.models.fast.model,
            "smart": cfg.models.smart.model,
            "cloud": cfg.models.cloud.model,
            "vision": cfg.models.vision.model,
            "embeddings": cfg.models.embeddings.model,
        },
        "server": {
            "host": cfg.server.host,
            "port": cfg.server.port,
            "network_mode": cfg.server.network_mode,
        },
        "memory": cfg.memory.model_dump(),
        "permissions": cfg.permissions.model_dump(),
    }
