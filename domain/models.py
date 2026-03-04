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


class Ability(BaseModel):
    """A single Pokémon ability entry."""

    name: str
    is_hidden: bool

    model_config = {"frozen": True}


class Evolution(BaseModel):
    """Direct evolution neighbours relative to this Pokémon."""

    antecessor: str | None = None
    successor: str | None = None

    model_config = {"frozen": True}


class PokemonData(BaseModel):
    """Parsed Pokémon information extracted from a Bulbapedia page."""

    name: str
    pokedex_number: int | None = None
    category: str | None = None
    types: list[str]
    stats: dict[str, int]
    evolution: Evolution = Field(default_factory=Evolution)
    abilities: list[Ability] = Field(default_factory=list)

    model_config = {"frozen": True}
