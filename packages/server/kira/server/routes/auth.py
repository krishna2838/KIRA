"""Google OAuth flow endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(tags=["auth"])


@router.get("/auth/google/status")
async def google_status(_: Request):
    from kira.tools.google_ws.auth import (
        has_credentials_file,
        is_authenticated,
    )
    return {
        "authenticated": is_authenticated(),
        "credentials_file_present": has_credentials_file(),
    }


@router.post("/auth/google")
async def google_signin(_: Request):
    """Kick off the browser OAuth flow.

    Blocks until the user completes consent in their browser. The redirect
    lands on a local port picked by google-auth's InstalledAppFlow.
    """
    from kira.tools.google_ws.auth import (
        has_credentials_file,
        start_flow_and_authenticate,
    )
    if not has_credentials_file():
        raise HTTPException(
            status_code=400,
            detail=(
                "Place your OAuth Desktop client credentials.json at "
                "~/.kira/google/credentials.json first (Google Cloud "
                "Console → APIs & Services → Credentials)."
            ),
        )
    # InstalledAppFlow is synchronous; run in a worker thread so it doesn't
    # block the event loop while the user completes consent.
    try:
        result = await asyncio.to_thread(start_flow_and_authenticate, 0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@router.post("/auth/google/signout")
async def google_signout(_: Request):
    from kira.tools.google_ws.auth import forget_token
    forget_token()
    return {"signed_out": True}


# ---- GitHub (personal access token, no OAuth) --------------------------


from pydantic import BaseModel


class GithubTokenIn(BaseModel):
    token: str


@router.get("/auth/github/status")
async def github_status(_: Request):
    from kira.tools.coding.github_api import has_pat
    return {"authenticated": has_pat()}


@router.post("/auth/github")
async def github_signin(body: GithubTokenIn, _: Request):
    from kira.tools.coding.github_api import set_pat
    if not body.token.strip():
        raise HTTPException(status_code=400, detail="token is empty")
    set_pat(body.token)
    return {"authenticated": True}


@router.post("/auth/github/signout")
async def github_signout(_: Request):
    from kira.tools.coding.github_api import forget_pat
    forget_pat()
    return {"signed_out": True}
