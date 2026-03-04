"""Port interfaces (ABCs) — define contracts for infrastructure adapters.

This module imports ONLY from `abc`, `pathlib`, and `domain.models`. No I/O allowed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from domain.models import CrawlUrl, PokemonData


class Fetcher(ABC):
    """Fetches raw HTML from a URL."""

    @abstractmethod
    async def fetch(self, crawl_url: CrawlUrl) -> str:
        """Return the HTML body for *crawl_url*."""

    @abstractmethod
    async def close(self) -> None:
        """Release underlying resources."""


class Parser(ABC):
    """Parses HTML into domain objects."""

    @abstractmethod
    def parse(self, html: str) -> PokemonData | None:
        """Extract Pokémon data from *html*. Return ``None`` if not a Pokémon page."""


class Storage(ABC):
    """Persists Pokémon data."""

    @abstractmethod
    async def save(self, data: PokemonData) -> None:
        """Persist *data* to the underlying store."""

    @abstractmethod
    async def close(self) -> None:
        """Flush and release underlying resources."""


class UrlRepository(ABC):
    """Tracks crawl URL lifecycle to avoid re-crawling."""

    @abstractmethod
    async def add_pending(self, url: str) -> bool:
        """Insert *url* as pending.

        Returns ``True`` if the URL was new and inserted,
        ``False`` if it was already known (any status).
        """

    @abstractmethod
    async def mark_done(self, url: str) -> None:
        """Mark *url* as successfully crawled."""

    @abstractmethod
    async def mark_failed(self, url: str, reason: str) -> None:
        """Mark *url* as failed with a human-readable *reason*."""

    @abstractmethod
    async def reset_failed(self) -> list[str]:
        """Reset all FAILED URLs back to PENDING so they are retried on re-run.

        Returns the list of URLs that were reset.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release underlying resources."""


class RateLimiter(ABC):
    """Controls the crawling request rate."""

    @abstractmethod
    async def acquire(self) -> None:
        """Block until a request token is available."""


class ImageDownloader(ABC):
    """Downloads and saves a remote image to a local path."""

    @abstractmethod
    async def download(self, url: str, dest: Path) -> None:
        """Fetch the image at *url* and write it to *dest*.

        Creates any missing parent directories. Skips the download if
        *dest* already exists (idempotent re-run behaviour).
        """
