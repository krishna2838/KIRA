"""Persistence + semantic search for captured notifications."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


class NotificationStore:
    """DB-backed store for notification events.

    The embedding pass is optional — if it fails we still store the row
    with a NULL embedding so plain text search / listing keeps working.
    """

    def __init__(self, db, embeddings=None):
        self.db = db
        self.embeddings = embeddings

    async def ingest(
        self,
        app_name: str,
        title: str,
        body: str,
        sender: str | None = None,
        importance: float = 0.5,
        timestamp: datetime | None = None,
    ) -> dict:
        emb = None
        text = f"{title}\n{body or ''}\nfrom {sender or ''}"
        if self.embeddings is not None:
            try:
                emb = await self.embeddings.embed(text)
            except Exception:
                emb = None
        row = await self.db.fetchrow(
            """INSERT INTO notifications
               (app_name, title, body, sender, timestamp, importance, embedding)
               VALUES ($1, $2, $3, $4, COALESCE($5, NOW()), $6, $7::vector)
               RETURNING id, timestamp""",
            app_name, title, body, sender, timestamp,
            float(importance), _vec(emb) if emb else None,
        )
        return {"id": str(row["id"]), "timestamp": row["timestamp"].isoformat()}

    async def recent(self, limit: int = 20, since_hours: int = 24) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT id, app_name, title, body, sender, timestamp, read, importance
               FROM notifications
               WHERE timestamp > NOW() - ($1 || ' hours')::interval
               ORDER BY timestamp DESC LIMIT $2""",
            str(since_hours), limit,
        )
        return [self._shape(r) for r in rows]

    async def unread_count(self) -> int:
        val = await self.db.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE read = FALSE"
        )
        return int(val or 0)

    async def mark_read(self, ids: list[str] | None = None) -> int:
        if ids is None:
            result = await self.db.execute(
                "UPDATE notifications SET read = TRUE WHERE read = FALSE"
            )
        else:
            result = await self.db.execute(
                "UPDATE notifications SET read = TRUE WHERE id = ANY($1::uuid[])",
                ids,
            )
        # asyncpg returns "UPDATE <n>"
        try:
            return int(str(result).split()[-1])
        except Exception:
            return 0

    async def search(
        self,
        query: str,
        limit: int = 15,
        app: str | None = None,
        sender: str | None = None,
    ) -> list[dict]:
        # Try semantic search first when embeddings are available.
        if self.embeddings is not None:
            try:
                emb = await self.embeddings.embed(query)
                sql = """
                    SELECT id, app_name, title, body, sender, timestamp, read, importance,
                           embedding <=> $1::vector AS distance
                    FROM notifications
                    WHERE embedding IS NOT NULL
                """
                args: list[Any] = [_vec(emb)]
                if app:
                    sql += f" AND app_name ILIKE ${len(args) + 1}"
                    args.append(app)
                if sender:
                    sql += f" AND sender ILIKE ${len(args) + 1}"
                    args.append(f"%{sender}%")
                sql += f" ORDER BY distance ASC LIMIT ${len(args) + 1}"
                args.append(limit)
                rows = await self.db.fetch(sql, *args)
                if rows:
                    return [self._shape(r) for r in rows]
            except Exception:
                pass

        # Lexical fallback.
        sql = """
            SELECT id, app_name, title, body, sender, timestamp, read, importance
            FROM notifications
            WHERE (title ILIKE $1 OR body ILIKE $1 OR sender ILIKE $1)
        """
        args = [f"%{query}%"]
        if app:
            sql += f" AND app_name ILIKE ${len(args) + 1}"
            args.append(app)
        if sender:
            sql += f" AND sender ILIKE ${len(args) + 1}"
            args.append(f"%{sender}%")
        sql += f" ORDER BY timestamp DESC LIMIT ${len(args) + 1}"
        args.append(limit)
        rows = await self.db.fetch(sql, *args)
        return [self._shape(r) for r in rows]

    async def latest_from(self, sender: str, limit: int = 5) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT id, app_name, title, body, sender, timestamp, read, importance
               FROM notifications
               WHERE sender ILIKE $1
               ORDER BY timestamp DESC LIMIT $2""",
            f"%{sender}%", limit,
        )
        return [self._shape(r) for r in rows]

    async def summarize_unread(self, summarize_fn) -> dict:
        rows = await self.recent(limit=25, since_hours=6)
        unread = [r for r in rows if not r["read"]]
        if not unread:
            return {"summary": "No unread notifications in the last 6 hours.", "count": 0}
        text = "\n".join(
            f"[{r['app_name']}] {r['sender'] or ''}: {r['title']} — {r['body'][:120]}"
            for r in unread
        )
        prompt = (
            "Summarize these notifications in ≤5 short bullets. "
            "Call out any that are urgent (mentions of deadline, meeting, "
            "'now', direct name mentions). If nothing is important, say so:\n\n"
            + text
        )
        summary = await summarize_fn(prompt)
        return {"summary": summary.strip(), "count": len(unread)}

    @staticmethod
    def _shape(row) -> dict:
        return {
            "id": str(row["id"]),
            "app_name": row["app_name"],
            "title": row["title"],
            "body": row["body"],
            "sender": row["sender"],
            "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            "read": row["read"],
            "importance": row["importance"],
        }
