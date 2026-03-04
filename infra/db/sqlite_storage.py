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
            INSERT INTO pokemon (name, pokedex_number, category, types, stats, evolution, abilities, image_path, saved_at)
            VALUES (:name, :pokedex_number, :category, :types, :stats, :evolution, :abilities, :image_path, :saved_at)
            ON CONFLICT(name) DO UPDATE SET
                pokedex_number = excluded.pokedex_number,
                category       = excluded.category,
                types          = excluded.types,
                stats          = excluded.stats,
                evolution      = excluded.evolution,
                abilities      = excluded.abilities,
                image_path     = excluded.image_path,
                saved_at       = excluded.saved_at
            """,
            {
                "name": data.name,
                "pokedex_number": data.pokedex_number,
                "category": data.category,
                "types": json.dumps(data.types),
                "stats": json.dumps(data.stats),
                "evolution": json.dumps(data.evolution.model_dump()),
                "abilities": json.dumps([a.model_dump() for a in data.abilities]),
                "image_path": data.image_path,
                "saved_at": now,
            },
        )
        await self._db.conn.commit()

    async def close(self) -> None:
        """Lifecycle managed by SqliteDatabase — nothing to do here."""
