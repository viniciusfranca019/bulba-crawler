"""Entrypoint — composition root, uvloop installation, and CLI definition."""

from __future__ import annotations

import asyncio

import structlog
import typer
import uvloop

from application.crawler import CrawlerService
from infra.crawler.html_parser import SelectolaxParser
from infra.crawler.http_fetcher import HttpxFetcher
from infra.crawler.rate_limiter import AiolimiterRateLimiter
from infra.db.connection import SqliteDatabase
from infra.db.sqlite_storage import SqliteStorage
from infra.db.sqlite_url_repo import SqliteUrlRepository

# Install uvloop as the default asyncio event loop policy before any loop
# is created. This replaces the default selector-based loop with libuv.
uvloop.install()

app = typer.Typer(add_completion=False)

# A small fixed list of Bulbapedia Pokémon pages to crawl.
_SEED_URLS: list[str] = [
    "https://bulbapedia.bulbagarden.net/wiki/Bulbasaur_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Charmander_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Squirtle_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Pikachu_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Mewtwo_(Pok%C3%A9mon)",
]


@app.command()
def crawl(
    db: str = typer.Option("crawl.db", help="Path to the SQLite database file."),
    rate: float = typer.Option(2.0, help="Maximum requests per second."),
) -> None:
    """Crawl Bulbapedia Pokémon pages and store results in SQLite."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    asyncio.run(_run(db_path=db, rate=rate))


async def _run(db_path: str, rate: float) -> None:
    database = SqliteDatabase(db_path)
    await database.open()

    fetcher = HttpxFetcher()
    parser = SelectolaxParser()
    storage = SqliteStorage(database)
    url_repo = SqliteUrlRepository(database)
    rate_limiter = AiolimiterRateLimiter(rate=rate)

    service = CrawlerService(
        fetcher=fetcher,
        parser=parser,
        storage=storage,
        url_repo=url_repo,
        rate_limiter=rate_limiter,
    )

    try:
        await service.run(seed_urls=_SEED_URLS)
    finally:
        await fetcher.close()
        await database.close()


if __name__ == "__main__":
    app()
