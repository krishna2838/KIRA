"""Gmail helpers."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from kira.tools.google_ws.services import gmail_service, run_google


def _headers_to_dict(headers: list[dict]) -> dict[str, str]:
    return {h["name"]: h["value"] for h in headers or []}


def _extract_body(payload: dict) -> str:
    """Walk MIME parts to find the first text/plain (or html fallback)."""
    def _walk(part):
        if not part:
            return None
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime.startswith("text/plain"):
            return base64.urlsafe_b64decode(data.encode("ascii")).decode(
                "utf-8", errors="replace"
            )
        for sub in part.get("parts") or []:
            found = _walk(sub)
            if found:
                return found
        # last resort: html
        if data and mime.startswith("text/html"):
            return base64.urlsafe_b64decode(data.encode("ascii")).decode(
                "utf-8", errors="replace"
            )
        return None
    return _walk(payload) or ""


async def list_emails(query: str = "", max_results: int = 10) -> list[dict]:
    def _do():
        svc = gmail_service()
        resp = (
            svc.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        msgs = resp.get("messages", []) or []
        out = []
        for m in msgs:
            meta = (
                svc.users()
                .messages()
                .get(userId="me", id=m["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            h = _headers_to_dict(meta.get("payload", {}).get("headers", []))
            out.append({
                "id": m["id"],
                "thread_id": m.get("threadId"),
                "from": h.get("From", ""),
                "subject": h.get("Subject", ""),
                "date": h.get("Date", ""),
                "snippet": meta.get("snippet", ""),
                "unread": "UNREAD" in (meta.get("labelIds") or []),
            })
        return out
    return await run_google(_do)


async def read_email(message_id: str) -> dict:
    def _do():
        svc = gmail_service()
        m = (
            svc.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        h = _headers_to_dict(m.get("payload", {}).get("headers", []))
        body = _extract_body(m.get("payload"))
        return {
            "id": m["id"],
            "from": h.get("From", ""),
            "to": h.get("To", ""),
            "subject": h.get("Subject", ""),
            "date": h.get("Date", ""),
            "snippet": m.get("snippet", ""),
            "body": body[:20000],
            "unread": "UNREAD" in (m.get("labelIds") or []),
        }
    return await run_google(_do)


async def send_email(to: str, subject: str, body: str) -> dict:
    def _do():
        svc = gmail_service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"sent": True, "id": sent.get("id")}
    return await run_google(_do)


async def draft_email(to: str, subject: str, body: str) -> dict:
    def _do():
        svc = gmail_service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        draft = svc.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        return {"drafted": True, "id": draft.get("id")}
    return await run_google(_do)


async def get_unread_count() -> dict:
    def _do():
        svc = gmail_service()
        label = svc.users().labels().get(userId="me", id="INBOX").execute()
        return {"unread": int(label.get("messagesUnread", 0))}
    return await run_google(_do)


async def summarize_inbox(summarize_fn) -> dict:
    """`summarize_fn` is an async callable (text) -> str provided by the caller."""
    emails = await list_emails(query="is:unread newer_than:2d", max_results=8)
    if not emails:
        return {"summary": "No unread emails in the last 2 days.", "count": 0}
    text = "\n\n".join(
        f"From: {e['from']}\nSubject: {e['subject']}\nSnippet: {e['snippet']}"
        for e in emails
    )
    prompt = (
        "Summarize these unread emails in 3–5 short bullet points. "
        "Call out anything time-sensitive (deadlines, meetings, requests):\n\n"
        + text
    )
    summary = await summarize_fn(prompt)
    return {"summary": summary.strip(), "count": len(emails)}
