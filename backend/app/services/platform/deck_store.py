import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from app.models.schemas import SlideData


class DeckStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    async def initialize(self) -> None:
        import os
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS decks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    deck_type TEXT NOT NULL,
                    theme TEXT NOT NULL DEFAULT 'minimalist',
                    aspect_ratio TEXT NOT NULL DEFAULT '16:9',
                    slides TEXT NOT NULL DEFAULT '[]',
                    thumbnail_b64 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.commit()

    async def create(
        self,
        name: str,
        deck_type: str,
        theme: str,
        aspect_ratio: str,
        slides: list[SlideData],
        thumbnail_b64: str | None = None,
    ) -> str:
        deck_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        slides_json = json.dumps([s.model_dump() for s in slides])
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO decks (id, name, deck_type, theme, aspect_ratio, slides, thumbnail_b64, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deck_id, name, deck_type, theme, aspect_ratio, slides_json, thumbnail_b64, now, now),
            )
            await db.commit()
        return deck_id

    async def get(self, deck_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_all(
        self,
        search: str = "",
        deck_type: str = "",
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT id, name, deck_type, slides, thumbnail_b64, created_at, updated_at FROM decks"
        params: list = []
        conditions: list[str] = []

        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")
        if deck_type:
            conditions.append("deck_type = ?")
            params.append(deck_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if sort == "oldest":
            query += " ORDER BY created_at ASC"
        elif sort == "name":
            query += " ORDER BY name ASC"
        else:
            query += " ORDER BY created_at DESC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        return [self._summary_from_row(r) for r in rows]

    async def update(
        self,
        deck_id: str,
        name: str | None = None,
        slides: list[SlideData] | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        updates: list[str] = ["updated_at = ?"]
        params: list = [now]

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if slides is not None:
            updates.append("slides = ?")
            params.append(json.dumps([s.model_dump() for s in slides]))

        params.append(deck_id)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"UPDATE decks SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()
        return cursor.rowcount > 0

    async def delete(self, deck_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            await db.commit()
        return cursor.rowcount > 0

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["slides"] = [SlideData(**s) for s in json.loads(d["slides"])]
        return d

    def _summary_from_row(self, row) -> dict:
        d = dict(row)
        slides = json.loads(d.pop("slides"))
        d["slide_count"] = len(slides)
        return d
