"""Auto-redaction engine. Runs BEFORE any memory write. No exceptions."""
from __future__ import annotations

import re


REDACTION_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "api_key": r"(?:sk|pk|api[_-]?key)[_-]?[A-Za-z0-9]{20,}",
    "password": r"(?:password|passwd|pwd)\s*[:=]\s*\S+",
    "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"\b(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "jwt_token": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "private_key": (
        r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"
        r"[\s\S]*?-----END (?:RSA |EC |DSA )?PRIVATE KEY-----"
    ),
    "bearer_token": r"Bearer\s+[A-Za-z0-9_-]{20,}",
}


def redact(text: str, enabled_patterns: list[str] | None = None) -> str:
    """Strip sensitive patterns from text before storing."""
    if enabled_patterns is None:
        enabled_patterns = list(REDACTION_PATTERNS.keys())

    result = text
    for pattern_name in enabled_patterns:
        pattern = REDACTION_PATTERNS.get(pattern_name)
        if not pattern:
            continue
        result = re.sub(
            pattern,
            f"[REDACTED:{pattern_name.upper()}]",
            result,
            flags=re.IGNORECASE,
        )
    return result
