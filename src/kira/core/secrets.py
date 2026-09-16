"""Central secret manager.

All API keys, tokens, and passwords go through here. Backed by the macOS
Keychain via `keyring`; falls back to `~/.kira/secrets.json` when keyring
isn't available (never with a helpful log line — we never log the value).

Registered secret names are stored so callers can enumerate what's set
without leaking the values themselves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


SERVICE = "KIRA/secrets"
_FALLBACK_PATH = Path.home() / ".kira" / "secrets.json"


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def _fallback_read() -> dict:
    if not _FALLBACK_PATH.exists():
        return {}
    try:
        with _FALLBACK_PATH.open() as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _fallback_write(data: dict) -> None:
    _FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FALLBACK_PATH.open("w") as f:
        json.dump(data, f)
    try:
        os.chmod(_FALLBACK_PATH, 0o600)
    except OSError:
        pass


def get_secret(name: str) -> Optional[str]:
    kr = _keyring()
    if kr is not None:
        try:
            val = kr.get_password(SERVICE, name)
            if val is not None:
                return val
        except Exception:
            pass
    # Fallback for environments without Keychain (CI, Linux dev boxes).
    return _fallback_read().get(name)


def set_secret(name: str, value: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, name, value)
            return
        except Exception:
            pass
    data = _fallback_read()
    data[name] = value
    _fallback_write(data)


def delete_secret(name: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
    data = _fallback_read()
    if name in data:
        data.pop(name, None)
        _fallback_write(data)


def list_secret_names() -> list[str]:
    """Return known secret NAMES only — never values.

    Keyring doesn't have a portable "enumerate" API, so we track the set of
    names KIRA has *set* via this module in `~/.kira/secret_names.json`.
    """
    names_path = _FALLBACK_PATH.parent / "secret_names.json"
    try:
        with names_path.open() as f:
            return sorted(json.load(f) or [])
    except Exception:
        return sorted(_fallback_read().keys())


def _record_name(name: str) -> None:
    path = _FALLBACK_PATH.parent / "secret_names.json"
    try:
        current = []
        if path.exists():
            with path.open() as f:
                current = json.load(f) or []
        if name not in current:
            current.append(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w") as f:
                json.dump(current, f)
    except Exception:
        pass


# Wrap set/delete to keep the name index honest.
_set_orig = set_secret
_delete_orig = delete_secret


def set_secret(name: str, value: str) -> None:  # type: ignore[no-redef]
    _set_orig(name, value)
    _record_name(name)


def delete_secret(name: str) -> None:  # type: ignore[no-redef]
    _delete_orig(name)
    path = _FALLBACK_PATH.parent / "secret_names.json"
    try:
        if path.exists():
            with path.open() as f:
                current = json.load(f) or []
            if name in current:
                current.remove(name)
                with path.open("w") as f:
                    json.dump(current, f)
    except Exception:
        pass
