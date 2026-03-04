"""Entrypoint — composition root, uvloop installation, and CLI definition."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import structlog
import typer
import uvloop

from application.crawler import CrawlerService
from infra.crawler.html_parser import SelectolaxParser
from infra.crawler.http_fetcher import HttpxFetcher
from infra.crawler.image_downloader import HttpxImageDownloader
from infra.crawler.rate_limiter import AiolimiterRateLimiter
from infra.db.connection import SqliteDatabase
from infra.db.sqlite_storage import SqliteStorage
from infra.db.sqlite_url_repo import SqliteUrlRepository

# Install uvloop as the default asyncio event loop policy before any loop
# is created. This replaces the default selector-based loop with libuv.
uvloop.install()

app = typer.Typer(add_completion=False, help="Bulbapedia Pokémon crawler.")

# A small fixed list of Bulbapedia Pokémon pages to crawl.
_SEED_URLS: list[str] = [
    "https://bulbapedia.bulbagarden.net/wiki/Bulbasaur_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Charmander_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Squirtle_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Pikachu_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Mewtwo_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Nidoran♂_(Pok%C3%A9mon)",
    "https://bulbapedia.bulbagarden.net/wiki/Nidoran♀_(Pok%C3%A9mon)",
]

_ASSETS_DIR = Path("assets")


@app.command()
def crawl(
    db: str = typer.Option("crawl.db", help="Path to the SQLite database file."),
    rate: float = typer.Option(2.0, help="Maximum requests per second."),
    assets_dir: str = typer.Option("assets", help="Directory to save Pokémon images."),
) -> None:
    """Crawl Bulbapedia Pokémon pages and store results in SQLite."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    asyncio.run(_run(db_path=db, rate=rate, assets_dir=Path(assets_dir)))


@app.command()
def export(
    db: str = typer.Option("crawl.db", help="Path to the SQLite database file."),
    output: str = typer.Option("-", help="Output file path. Use '-' for stdout."),
) -> None:
    """Export crawled Pokémon data from SQLite to JSON."""
    db_path = Path(db)
    if not db_path.exists():
        typer.echo(f"Database not found: {db}", err=True)
        raise typer.Exit(code=1)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT name, pokedex_number, category, types, stats, evolution, abilities, gender_ratio, image_path, saved_at FROM pokemon ORDER BY pokedex_number, name"
    ).fetchall()
    con.close()

    pokemon_list = [
        {
            "name": row["name"],
            "pokedex_number": row["pokedex_number"],
            "category": row["category"],
            "types": json.loads(row["types"]),
            "stats": json.loads(row["stats"]),
            "evolution": json.loads(row["evolution"]),
            "abilities": json.loads(row["abilities"]),
            "gender_ratio": json.loads(row["gender_ratio"]),
            "image_path": row["image_path"],
            "saved_at": row["saved_at"],
        }
        for row in rows
    ]

    result = json.dumps(pokemon_list, indent=2, ensure_ascii=False)

    if output == "-":
        sys.stdout.write(result + "\n")
    else:
        Path(output).write_text(result + "\n", encoding="utf-8")
        typer.echo(f"Exported {len(pokemon_list)} Pokémon to {output}")


async def _run(db_path: str, rate: float, assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)

    database = SqliteDatabase(db_path)
    await database.open()

    fetcher = HttpxFetcher()
    parser = SelectolaxParser()
    storage = SqliteStorage(database)
    url_repo = SqliteUrlRepository(database)
    rate_limiter = AiolimiterRateLimiter(rate=rate)
    image_downloader = HttpxImageDownloader()

    service = CrawlerService(
        fetcher=fetcher,
        parser=parser,
        storage=storage,
        url_repo=url_repo,
        rate_limiter=rate_limiter,
        image_downloader=image_downloader,
        assets_dir=assets_dir,
    )

    try:
        await service.run(seed_urls=_SEED_URLS)
    finally:
        await fetcher.close()
        await image_downloader.close()
        await database.close()


if __name__ == "__main__":
    app()
