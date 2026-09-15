"""Optional Discord integration.

We deliberately do NOT run a long-lived discord.py client from inside the
FastAPI process — that would monopolize an event loop. Instead the
integration exposes REST-style reads via the bot token; when a user does
want live pushes, they can run a separate `discord.py` process that posts
into KIRA's `/api/notifications/ingest` endpoint.
"""
from __future__ import annotations

from kira.logger import get_logger


logger = get_logger("tools.notifications.discord")


_bot_token: str | None = None


def configure(bot_token: str | None) -> None:
    global _bot_token
    _bot_token = bot_token or None


def is_configured() -> bool:
    return _bot_token is not None


async def read_channel(channel_id: str, limit: int = 25) -> dict:
    if not is_configured():
        return {"available": False, "reason": "discord bot not configured"}
    try:
        import httpx  # type: ignore
    except Exception as e:
        return {"available": False, "reason": str(e)}
    headers = {"Authorization": f"Bot {_bot_token}"}
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"available": False, "reason": str(e)}
    return {
        "available": True,
        "messages": [
            {
                "id": m["id"],
                "author": (m.get("author") or {}).get("username", ""),
                "text": m.get("content", ""),
                "timestamp": m.get("timestamp"),
            }
            for m in data
        ],
    }
