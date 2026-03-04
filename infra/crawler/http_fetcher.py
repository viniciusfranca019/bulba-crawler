"""HttpxFetcher — fetches raw HTML over HTTP/2 using httpx."""

from __future__ import annotations

import httpx

from domain.models import CrawlUrl
from domain.ports import Fetcher

_HEADERS = {
    "User-Agent": (
        "bulba-crawler/0.1 (educational project; github.com/anomalyco/bulba-crawler)"
    )
}


class HttpxFetcher(Fetcher):
    """Implements Fetcher using a persistent httpx.AsyncClient with HTTP/2."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )

    async def fetch(self, crawl_url: CrawlUrl) -> str:
        response = await self._client.get(crawl_url.url)
        response.raise_for_status()
        return response.text

    async def close(self) -> None:
        await self._client.aclose()
