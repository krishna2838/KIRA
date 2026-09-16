"""Google Drive helpers."""
from __future__ import annotations

from typing import Any

from kira.tools.google_ws.services import drive_service, run_google


async def search_files(query: str, max_results: int = 20) -> list[dict]:
    def _do():
        svc = drive_service()
        # Drive uses a `q=` DSL; wrap the free-text into a name-contains OR
        # fullText-contains disjunction.
        q = f"(name contains '{query}' or fullText contains '{query}') and trashed = false"
        resp = svc.files().list(
            q=q,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        ).execute()
        return resp.get("files", [])
    return await run_google(_do)


async def list_recent(limit: int = 20) -> list[dict]:
    def _do():
        svc = drive_service()
        resp = svc.files().list(
            orderBy="modifiedTime desc",
            pageSize=limit,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        ).execute()
        return resp.get("files", [])
    return await run_google(_do)


async def read_file(file_id: str) -> dict:
    def _do():
        svc = drive_service()
        meta = svc.files().get(
            fileId=file_id,
            fields="id, name, mimeType, modifiedTime, webViewLink",
        ).execute()
        mime = meta.get("mimeType", "")
        content = ""
        try:
            if mime == "application/vnd.google-apps.document":
                content = svc.files().export(
                    fileId=file_id, mimeType="text/plain"
                ).execute().decode("utf-8", errors="replace")
            elif mime == "application/vnd.google-apps.spreadsheet":
                content = svc.files().export(
                    fileId=file_id, mimeType="text/csv"
                ).execute().decode("utf-8", errors="replace")
            elif mime.startswith("text/"):
                content = svc.files().get_media(fileId=file_id).execute().decode(
                    "utf-8", errors="replace"
                )
        except Exception as e:
            content = f"[could not extract: {e}]"
        return {**meta, "content": content[:20000]}
    return await run_google(_do)
