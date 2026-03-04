"""CrawlerService — orchestrates the producer/worker crawl loop.

This module depends only on domain ports and the standard library.
It has no knowledge of httpx, aiosqlite, or any other concrete adapter.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from domain.models import CrawlUrl, PokemonData
from domain.ports import (
    Fetcher,
    ImageDownloader,
    Parser,
    RateLimiter,
    Storage,
    UrlRepository,
)

log = structlog.get_logger(__name__)

_WORKERS = 5


class CrawlerService:
    """Runs a concurrent crawl over a fixed list of seed URLs.

    The producer enqueues every seed that has not been visited before.
    Each worker dequeues one URL at a time, fetches it, parses it,
    persists the result, and marks the URL as done or failed.

    asyncio.Queue provides back-pressure: workers block on get() when
    the queue is empty and the producer blocks on put() when the queue
    is full (maxsize=0 means unbounded, which is fine for a fixed list).
    """

    def __init__(
        self,
        fetcher: Fetcher,
        parser: Parser,
        storage: Storage,
        url_repo: UrlRepository,
        rate_limiter: RateLimiter,
        image_downloader: ImageDownloader | None = None,
        assets_dir: Path | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._parser = parser
        self._storage = storage
        self._url_repo = url_repo
        self._rate_limiter = rate_limiter
        self._image_downloader = image_downloader
        self._assets_dir = assets_dir
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def run(self, seed_urls: list[str]) -> None:
        """Entry point — seed the queue then drain it with workers."""
        enqueued = await self._produce(seed_urls)
        if enqueued == 0:
            log.info("crawler.no_new_urls", total=len(seed_urls))
            return

        log.info("crawler.start", enqueued=enqueued, workers=_WORKERS)
        tasks = [
            asyncio.create_task(self._worker(worker_id=i)) for i in range(_WORKERS)
        ]

        await self._queue.join()  # block until every item is processed

        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("crawler.done")

    # ------------------------------------------------------------------
    # Producer
    # ------------------------------------------------------------------

    async def _produce(self, seed_urls: list[str]) -> int:
        """Insert new URLs into the DB and enqueue them. Returns count enqueued."""
        # Re-enqueue any URLs that failed in a previous run.
        reset_urls = await self._url_repo.reset_failed()
        for url in reset_urls:
            await self._queue.put(url)
        if reset_urls:
            log.info("crawler.reset_failed", count=len(reset_urls))

        count = len(reset_urls)
        for url in seed_urls:
            is_new = await self._url_repo.add_pending(url)
            if is_new:
                await self._queue.put(url)
                count += 1
            else:
                log.debug("crawler.skip_known", url=url)
        return count

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _worker(self, worker_id: int) -> None:
        """Consume URLs from the queue indefinitely until cancelled."""
        while True:
            url = await self._queue.get()
            await self._process(url, worker_id)
            self._queue.task_done()

    async def _process(self, url: str, worker_id: int) -> None:
        log.info("worker.fetch", worker=worker_id, url=url)
        try:
            await self._rate_limiter.acquire()
            html = await self._fetcher.fetch(CrawlUrl(url=url))
            data = self._parser.parse(html)

            if data is not None:
                data = await self._download_image(data, worker_id)
                await self._storage.save(data)
                log.info("worker.saved", worker=worker_id, pokemon=data.name)
            else:
                log.debug("worker.no_data", worker=worker_id, url=url)

            await self._url_repo.mark_done(url)

        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            log.warning("worker.failed", worker=worker_id, url=url, reason=reason)
            await self._url_repo.mark_failed(url, reason)

    async def _download_image(self, data: PokemonData, worker_id: int) -> PokemonData:
        """Download the Pokémon image and return a new PokemonData with the
        local relative path stored in image_path.

        If no image_downloader or assets_dir is configured, or if the parsed
        data carries no image URL, returns data unchanged.
        """
        if (
            self._image_downloader is None
            or self._assets_dir is None
            or data.image_path is None
        ):
            return data

        image_url = data.image_path
        # Derive a clean filename from the URL's last path segment.
        filename = Path(image_url.split("?")[0]).name
        dest = self._assets_dir / filename
        local_path = str(dest)

        try:
            await self._image_downloader.download(image_url, dest)
            log.info("worker.image_saved", worker=worker_id, path=local_path)
        except Exception as exc:
            log.warning(
                "worker.image_failed",
                worker=worker_id,
                url=image_url,
                reason=f"{type(exc).__name__}: {exc}",
            )
            # Keep image_path as None so the record is still saved without it.
            return data.model_copy(update={"image_path": None})

        return data.model_copy(update={"image_path": local_path})
