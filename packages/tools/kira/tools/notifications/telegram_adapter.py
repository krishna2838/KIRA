"""Optional Telegram integration.

Uses `python-telegram-bot` when installed. The bootstrap wires a bot token
via `configure(bot_token, allowed_chat_ids)`. If nothing is configured, the
tools return `{"available": False}` and the LLM is expected to say so.
"""
from __future__ import annotations

from kira.logger import get_logger


logger = get_logger("tools.notifications.telegram")


_bot_token: str | None = None
_allowed: set[int] = set()


def configure(bot_token: str | None, allowed_chat_ids: list[int] | None = None) -> None:
    global _bot_token, _allowed
    _bot_token = bot_token or None
    _allowed = set(allowed_chat_ids or [])


def is_configured() -> bool:
    return _bot_token is not None


async def read_recent(chat_id: int, limit: int = 20) -> dict:
    if not is_configured():
        return {"available": False, "reason": "telegram bot not configured"}
    if _allowed and chat_id not in _allowed:
        return {"available": False, "reason": f"chat {chat_id} not authorized"}
    try:
        from telegram import Bot  # type: ignore
    except Exception as e:
        return {"available": False, "reason": f"python-telegram-bot missing: {e}"}
    try:
        bot = Bot(token=_bot_token)  # type: ignore[arg-type]
        updates = await bot.get_updates(timeout=5)
        rows = []
        for u in updates[-limit:]:
            if not u.message or u.message.chat_id != chat_id:
                continue
            rows.append({
                "id": u.update_id,
                "from": u.message.from_user.username if u.message.from_user else "",
                "text": u.message.text or "",
                "date": u.message.date.isoformat() if u.message.date else "",
            })
        return {"available": True, "messages": rows}
    except Exception as e:
        return {"available": False, "reason": str(e)}


async def send_message(chat_id: int, text: str) -> dict:
    if not is_configured():
        return {"sent": False, "reason": "telegram bot not configured"}
    if _allowed and chat_id not in _allowed:
        return {"sent": False, "reason": f"chat {chat_id} not authorized"}
    try:
        from telegram import Bot  # type: ignore

        bot = Bot(token=_bot_token)  # type: ignore[arg-type]
        msg = await bot.send_message(chat_id=chat_id, text=text)
        return {"sent": True, "message_id": msg.message_id}
    except Exception as e:
        return {"sent": False, "reason": str(e)}
