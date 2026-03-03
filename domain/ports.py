"""Port interfaces (ABCs) — define contracts for infrastructure adapters.

This module imports ONLY from `abc` and `domain.models`. No I/O allowed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

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

    @abstractmethod
    def extract_links(self, html: str, base_url: str) -> list[str]:
        """Return absolute URLs of Pokémon pages found in *html*."""


class Storage(ABC):
    """Persists Pokémon data."""

    @abstractmethod
    async def save(self, data: PokemonData) -> None:
        """Append *data* to the underlying store."""

    @abstractmethod
    async def close(self) -> None:
        """Flush and release underlying resources."""


class RateLimiter(ABC):
    """Controls the crawling rate."""

    @abstractmethod
    async def acquire(self) -> None:
        """Block until a request token is available."""


class RobotsChecker(ABC):
    """Checks robots.txt compliance."""

    @abstractmethod
    async def setup(self, fetcher: Fetcher) -> None:
        """Fetch and parse robots.txt."""

    @abstractmethod
    def is_allowed(self, url: str) -> bool:
        """Return ``True`` if crawling *url* is permitted."""

