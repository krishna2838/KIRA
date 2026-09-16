"""Personal deadlines table CRUD."""
from __future__ import annotations

from datetime import datetime


class Deadlines:
    def __init__(self, db):
        self.db = db

    async def add(self, name: str, due: datetime, notes: str = "") -> dict:
        row = await self.db.fetchrow(
            """INSERT INTO deadlines (name, due, notes)
               VALUES ($1, $2, $3)
               RETURNING id, name, due, notes, completed, created_at""",
            name, due, notes,
        )
        return self._shape(row)

    async def upcoming(self, days: int = 14) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT id, name, due, notes, completed, created_at
               FROM deadlines
               WHERE completed = FALSE
                 AND due > NOW()
                 AND due < NOW() + ($1 || ' days')::interval
               ORDER BY due ASC""",
            str(days),
        )
        return [self._shape(r) for r in rows]

    async def complete(self, deadline_id: str) -> dict:
        await self.db.execute(
            "UPDATE deadlines SET completed = TRUE WHERE id = $1", deadline_id
        )
        return {"completed": True, "id": deadline_id}

    @staticmethod
    def _shape(row) -> dict:
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "due": row["due"].isoformat() if row["due"] else None,
            "notes": row["notes"],
            "completed": row["completed"],
        }
