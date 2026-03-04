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
    name     TEXT PRIMARY KEY,
    types    TEXT NOT NULL,
    stats    TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
"""


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
        """Open the connection and apply the DDL."""
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_DDL)
        await self._conn.commit()

    async def close(self) -> None:
        """Flush and close the connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
