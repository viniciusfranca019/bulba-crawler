"""SqliteDatabase — owns the aiosqlite connection and initialises the schema.

Both SqliteStorage and SqliteUrlRepository receive an instance of this class
via dependency injection. There is a single connection to the database file,
which avoids duplicate file handles and ensures schema migrations run once.
"""

from __future__ import annotations

import aiosqlite


_DDL = """
CREATE TABLE IF NOT EXISTS urls (
    url        TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'pending',
    reason     TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pokemon (
    name           TEXT PRIMARY KEY,
    pokedex_number INTEGER,
    category       TEXT,
    types          TEXT NOT NULL,
    stats          TEXT NOT NULL,
    evolution      TEXT NOT NULL DEFAULT '{}',
    abilities      TEXT NOT NULL DEFAULT '[]',
    saved_at       TEXT NOT NULL
);
"""

# Columns added after the initial schema. Each entry is (column, definition).
# ALTER TABLE ignores the statement if the column already exists via the
# try/except in _migrate(); this keeps open() idempotent.
_MIGRATIONS: list[tuple[str, str]] = [
    ("pokedex_number", "INTEGER"),
    ("category", "TEXT"),
    ("evolution", "TEXT NOT NULL DEFAULT '{}'"),
    ("abilities", "TEXT NOT NULL DEFAULT '[]'"),
    ("image_path", "TEXT"),
    ("gender_ratio", "TEXT NOT NULL DEFAULT '{}'"),
]


class SqliteDatabase:
    """Owns a single aiosqlite connection for the entire crawl session."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteDatabase not initialised — call open() first.")
        return self._conn

    async def open(self) -> None:
        """Open the connection, apply the DDL, and run column migrations."""
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_DDL)
        await self._conn.commit()
        await self._migrate()

    async def _migrate(self) -> None:
        """Add new columns to existing databases that predate the current schema.

        SQLite does not support IF NOT EXISTS on ALTER TABLE, so we attempt
        each ALTER and silently swallow the OperationalError raised when the
        column already exists.
        """
        for column, definition in _MIGRATIONS:
            try:
                await self._conn.execute(  # type: ignore[union-attr]
                    f"ALTER TABLE pokemon ADD COLUMN {column} {definition}"
                )
                await self._conn.commit()  # type: ignore[union-attr]
            except aiosqlite.OperationalError:
                pass  # column already exists — nothing to do

    async def close(self) -> None:
        """Flush and close the connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
