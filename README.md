# Bulba Crawler

A concurrent web crawler that extracts Pokemon data from Bulbapedia, built with Python 3.13 and asyncio.

## Running the Project

The project uses [uv](https://docs.astral.sh/uv/) as its package manager.

### Install dependencies

```bash
uv sync --all-groups
```

### Crawl Pokemon pages

```bash
uv run python main.py crawl
```

CLI options:

| Flag           | Default    | Description                          |
|----------------|------------|--------------------------------------|
| `--db`         | `crawl.db` | Path to the SQLite database file     |
| `--rate`       | `2.0`      | Maximum requests per second          |
| `--assets-dir` | `assets`   | Directory to save Pokemon images     |

### Export data to JSON

```bash
uv run python main.py export --output pokemon.json
```

### Makefile shortcuts

```bash
make crawl          # run the crawler
make dump           # export to pokemon.json
make lint           # lint with ruff
make format         # format with ruff
make clean          # remove crawl.db and assets/
make install-all    # install all dependency groups
```

## Why These Libraries

| Library | Role | Why |
|---------|------|-----|
| **httpx\[http2\]** | HTTP client | Async-native client with HTTP/2 support. HTTP/2 multiplexing allows multiple requests over a single TCP connection, reducing connection overhead. Unlike `aiohttp`, httpx provides a requests-compatible API and built-in redirect following. |
| **aiosqlite** | Database | Thin async wrapper around Python's built-in `sqlite3` module. It runs SQLite operations in a background thread so the event loop is never blocked by disk I/O, without requiring an external database server. |
| **aiofiles** | File I/O | Provides async file read/write operations. Downloading Pokemon images involves writing bytes to disk, and `aiofiles` prevents those writes from blocking the event loop. |
| **aiolimiter** | Rate limiting | Implements a leaky-bucket rate limiter for asyncio. All workers share a single limiter instance, ensuring the crawler collectively respects a configurable request-per-second ceiling and avoids overwhelming Bulbapedia. |
| **uvloop** | Event loop | Drop-in replacement for the default asyncio event loop, built on top of libuv. It provides significantly higher I/O throughput, which benefits a crawler that spends most of its time waiting on network and disk. |
| **tenacity** | Retry logic | Flexible retry library with exponential backoff, configurable stop conditions, and exception filtering. The crawler uses it to retry only transient HTTP errors (429, 5xx, network failures) while letting permanent 4xx errors fail immediately. |
| **selectolax** | HTML parsing | A fast HTML parser backed by the Modest C library. It is significantly faster than BeautifulSoup for CSS-selector-based extraction, which matters when parsing multiple pages concurrently. |
| **pydantic** | Data validation | Validates and serializes the scraped Pokemon data into typed models (`PokemonData`, `CrawlUrl`). Ensures that malformed data is caught early instead of silently corrupting the database. |
| **structlog** | Logging | Structured logging library that produces key-value log lines. Each log event carries context like `worker=2, url=...`, making it straightforward to trace which worker processed which URL during concurrent execution. |
| **typer** | CLI | Builds the command-line interface (`crawl` and `export` commands) with type-annotated function signatures. Provides automatic `--help` generation and argument validation with minimal boilerplate. |

## Why the Producer/Worker Pattern

The crawler uses a **producer/consumer pattern** built on `asyncio.Queue` and `asyncio.create_task` to process multiple Pokemon URLs concurrently.

### How it works

1. A **producer** enqueues seed URLs into an `asyncio.Queue`, skipping any URL that was already crawled in a previous run (deduplication via the database).
2. Five **worker** tasks are spawned with `asyncio.create_task`. Each worker loops indefinitely, pulling one URL at a time from the queue, fetching it, parsing it, and persisting the result.
3. `await queue.join()` acts as a synchronization barrier -- it blocks until every enqueued item has been processed. After that, workers are cancelled and collected cleanly.

```
Producer                          Queue                         Workers (x5)
   |                                |                               |
   |-- enqueue URL 1 ------------->|                               |
   |-- enqueue URL 2 ------------->|                               |
   |-- enqueue URL 3 ------------->|          worker 0: get() ---->|
   |-- enqueue URL 4 ------------->|          worker 1: get() ---->|
   |-- enqueue URL 5 ------------->|          worker 2: get() ---->|
   |                                |          worker 3: get() ---->|
   |                                |          worker 4: get() ---->|
   |                                |                               |
   |<-- queue.join() waits -------->|<-- task_done() per item ------|
```

### Why this pattern instead of alternatives

- **vs. `asyncio.gather` over all URLs**: `gather` launches all coroutines at once. With a queue, we control the degree of parallelism (5 workers) independently from the number of URLs. If the seed list grows to hundreds of pages, the worker count stays fixed and the queue provides natural back-pressure.
- **vs. `asyncio.Semaphore`**: A semaphore limits concurrency but doesn't provide a work queue. The queue pattern gives us a clear separation between producing work (enqueuing URLs) and consuming it (workers), which makes it easy to add features like deduplication, retry of failed URLs, and graceful shutdown.
- **vs. threads / multiprocessing**: The workload is I/O-bound (HTTP requests, disk writes, SQLite queries). Asyncio handles this on a single thread with cooperative multitasking, avoiding the overhead and complexity of thread synchronization or inter-process communication.

The shared rate limiter ensures all workers collectively respect the request rate, regardless of how many are active.

## Why Hexagonal Architecture (Ports and Adapters)

The project follows the **Hexagonal Architecture** pattern, separating the codebase into three layers:

```
domain/              application/              infra/
  models.py            crawler.py                crawler/
  ports.py                                         http_fetcher.py
                                                   html_parser.py
                                                   image_downloader.py
                                                   rate_limiter.py
                                                 db/
                                                   connection.py
                                                   sqlite_storage.py
                                                   sqlite_url_repo.py
```

- **domain/** contains pure data models (`PokemonData`, `CrawlUrl`) and abstract port interfaces (`Fetcher`, `Parser`, `Storage`, `UrlRepository`, `RateLimiter`, `ImageDownloader`). It has zero I/O dependencies.
- **application/** contains `CrawlerService`, which orchestrates the crawl loop using only the port abstractions. It has no knowledge of httpx, aiosqlite, or any concrete adapter.
- **infra/** contains concrete implementations of each port, wired together in `main.py` (the composition root).

### Why this matters for a crawler

1. **Testability** -- Each port can be replaced with an in-memory fake. You can test the entire crawl orchestration logic without making real HTTP requests or touching the filesystem.
2. **Swappability** -- Changing the storage from SQLite to PostgreSQL, or the HTTP client from httpx to aiohttp, requires writing a new adapter that implements the existing port interface. The application layer and domain layer remain untouched.
3. **Dependency direction** -- Dependencies point inward: `infra` depends on `domain`, `application` depends on `domain`, but `domain` depends on nothing. This prevents infrastructure concerns from leaking into business logic.
4. **Readability** -- The `CrawlerService` reads as a high-level description of what the crawler does (fetch, parse, save, mark done), without being cluttered by HTTP headers, SQL queries, or file-system paths.
