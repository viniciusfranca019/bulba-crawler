"""Domain value objects — pure data, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class UrlStatus(str, Enum):
    """Lifecycle states for a crawl URL."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class CrawlUrl(BaseModel):
    """A URL scheduled for crawling."""

    url: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}


class PokemonData(BaseModel):
    """Parsed Pokémon information extracted from a Bulbapedia page."""

    name: str
    types: list[str]
    stats: dict[str, int]

    model_config = {"frozen": True}
