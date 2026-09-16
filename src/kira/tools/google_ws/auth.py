"""Google OAuth flow.

Credentials come from `~/.kira/google/credentials.json` (Google Cloud OAuth
client, application type = "Desktop app"). We store the refresh token in
the macOS Keychain via `keyring` under the service name `KIRA/google`.

The consent screen is opened in the user's default browser by the local
`InstalledAppFlow`. The redirect_uri is `http://127.0.0.1:<free port>/`
which the flow's own tiny HTTP server terminates.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kira.core.logger import get_logger


logger = get_logger("tools.google.auth")


KEYRING_SERVICE = "KIRA/google"
KEYRING_USER = "primary"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


def credentials_path() -> Path:
    return Path.home() / ".kira" / "google" / "credentials.json"


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception as e:
        raise RuntimeError(
            "keyring is required to store Google tokens "
            "(pip install keyring): " + str(e)
        ) from e


def _google_libs():
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        return Credentials, Request, InstalledAppFlow
    except Exception as e:
        raise RuntimeError(
            "google-auth libraries missing "
            "(pip install google-auth-oauthlib google-api-python-client): "
            + str(e)
        ) from e


def has_credentials_file() -> bool:
    return credentials_path().exists()


def load_stored_token() -> dict | None:
    try:
        keyring = _keyring()
    except RuntimeError:
        return None
    try:
        blob = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return json.loads(blob) if blob else None
    except Exception:
        return None


def save_stored_token(token_json: dict) -> None:
    keyring = _keyring()
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(token_json))


def forget_token() -> None:
    try:
        keyring = _keyring()
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass


def is_authenticated() -> bool:
    return load_stored_token() is not None


def get_credentials() -> Any | None:
    """Return a live google.oauth2.credentials.Credentials, refreshed if
    needed. Returns None if not yet authenticated."""
    stored = load_stored_token()
    if not stored:
        return None
    try:
        Credentials, Request, _ = _google_libs()
    except RuntimeError as e:
        logger.warning(str(e))
        return None
    creds = Credentials.from_authorized_user_info(stored, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                save_stored_token(json.loads(creds.to_json()))
            except Exception as e:
                logger.warning(f"token refresh failed: {e}")
                return None
        else:
            return None
    return creds


def start_flow_and_authenticate(port: int = 0) -> dict:
    """Blocking: open a browser for consent, then persist the token.

    This runs in a background thread from the FastAPI /api/auth/google
    endpoint. `port=0` picks a free port.
    """
    if not has_credentials_file():
        raise RuntimeError(
            f"No credentials.json at {credentials_path()}. Download an "
            "OAuth Desktop client from Google Cloud Console and place it there."
        )
    _, _, InstalledAppFlow = _google_libs()
    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path()), SCOPES
    )
    creds = flow.run_local_server(port=port, open_browser=True)
    token = json.loads(creds.to_json())
    save_stored_token(token)
    return {"authenticated": True, "email": _who_am_i(creds)}


def _who_am_i(creds) -> str:
    try:
        from googleapiclient.discovery import build  # type: ignore
        oauth = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = oauth.userinfo().get().execute()
        return info.get("email", "")
    except Exception:
        return ""
