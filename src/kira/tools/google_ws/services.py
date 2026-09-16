"""Cached Google API service builders + helpers."""
from __future__ import annotations

import asyncio
from typing import Any

from kira.tools.google_ws.auth import get_credentials


def _build(name: str, version: str):
    from googleapiclient.discovery import build  # type: ignore

    creds = get_credentials()
    if creds is None:
        raise RuntimeError(
            "Google account not connected. Visit /api/auth/google to sign in."
        )
    return build(name, version, credentials=creds, cache_discovery=False)


async def run_google(fn) -> Any:
    """Wrap the (synchronous) Google client in a thread executor."""
    return await asyncio.to_thread(fn)


def gmail_service():
    return _build("gmail", "v1")


def calendar_service():
    return _build("calendar", "v3")


def tasks_service():
    return _build("tasks", "v1")


def drive_service():
    return _build("drive", "v3")
