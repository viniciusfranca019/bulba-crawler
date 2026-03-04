"""HttpxImageDownloader — downloads a remote image and saves it to disk.

Uses the same httpx.AsyncClient pattern as HttpxFetcher and aiofiles for
non-blocking file I/O, consistent with the rest of the async infrastructure.
"""

from __future__ import annotations

from pathlib import Path

import aiofiles
import httpx

from domain.ports import ImageDownloader
from infra.crawler._retry import http_retry

_HEADERS = {
    "User-Agent": (
        "bulba-crawler/0.1 (educational project; github.com/anomalyco/bulba-crawler)"
    )
}


class HttpxImageDownloader(ImageDownloader):
    """Implements ImageDownloader using httpx for the HTTP request and aiofiles
    for writing the image bytes to disk.

    A single AsyncClient is reused across all downloads to take advantage of
    connection pooling. Call close() when the crawl session ends.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )

    @http_retry(max_attempts=2)
    async def download(self, url: str, dest: Path) -> None:
        """Fetch the image at *url* and write it to *dest*.

        Skips the download if *dest* already exists, making re-runs idempotent.
        Creates any missing parent directories before writing.
        """
        if dest.exists():
            return

        dest.parent.mkdir(parents=True, exist_ok=True)

        response = await self._client.get(url)
        response.raise_for_status()

        async with aiofiles.open(dest, "wb") as f:
            await f.write(response.content)

    async def close(self) -> None:
        """Release the underlying httpx client."""
        await self._client.aclose()
