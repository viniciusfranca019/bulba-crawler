"""SqliteUrlRepository — tracks URL lifecycle in the `urls` table."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.models import UrlStatus
from domain.ports import UrlRepository
from infra.db.connection import SqliteDatabase


class SqliteUrlRepository(UrlRepository):
    """Implements UrlRepository using the shared SqliteDatabase connection."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def add_pending(self, url: str) -> bool:
        """Insert *url* as pending. Returns False if URL was already known."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.conn.execute(
            """
            INSERT OR IGNORE INTO urls (url, status, created_at, updated_at)
            VALUES (:url, :status, :now, :now)
            """,
            {"url": url, "status": UrlStatus.PENDING, "now": now},
        )
        await self._db.conn.commit()
        return cursor.rowcount > 0

    async def mark_done(self, url: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.conn.execute(
            """
            UPDATE urls SET status = :status, updated_at = :now
            WHERE url = :url
            """,
            {"status": UrlStatus.DONE, "now": now, "url": url},
        )
        await self._db.conn.commit()

    async def mark_failed(self, url: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.conn.execute(
            """
            UPDATE urls SET status = :status, reason = :reason, updated_at = :now
            WHERE url = :url
            """,
            {"status": UrlStatus.FAILED, "reason": reason, "now": now, "url": url},
        )
        await self._db.conn.commit()

    async def reset_failed(self) -> list[str]:
        """Reset all FAILED rows back to PENDING and clear their reason.

        Returns the list of URLs that were reset so callers can re-enqueue them.
        """
        now = datetime.now(timezone.utc).isoformat()
        # Fetch the URLs before updating so we can return them.
        async with self._db.conn.execute(
            "SELECT url FROM urls WHERE status = :failed",
            {"failed": UrlStatus.FAILED},
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return []

        await self._db.conn.execute(
            """
            UPDATE urls SET status = :pending, reason = NULL, updated_at = :now
            WHERE status = :failed
            """,
            {"pending": UrlStatus.PENDING, "failed": UrlStatus.FAILED, "now": now},
        )
        await self._db.conn.commit()
        return [row["url"] for row in rows]

    async def close(self) -> None:
        """Lifecycle managed by SqliteDatabase — nothing to do here."""
