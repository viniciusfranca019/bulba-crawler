"""SqliteStorage — persists PokemonData to the `pokemon` table."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domain.models import PokemonData
from domain.ports import Storage
from infra.db.connection import SqliteDatabase


class SqliteStorage(Storage):
    """Implements Storage using the shared SqliteDatabase connection."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def save(self, data: PokemonData) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.conn.execute(
            """
            INSERT INTO pokemon (name, types, stats, saved_at)
            VALUES (:name, :types, :stats, :saved_at)
            ON CONFLICT(name) DO UPDATE SET
                types    = excluded.types,
                stats    = excluded.stats,
                saved_at = excluded.saved_at
            """,
            {
                "name": data.name,
                "types": json.dumps(data.types),
                "stats": json.dumps(data.stats),
                "saved_at": now,
            },
        )
        await self._db.conn.commit()

    async def close(self) -> None:
        """Lifecycle managed by SqliteDatabase — nothing to do here."""
