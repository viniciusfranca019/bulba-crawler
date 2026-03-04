"""Shared retry configuration for HTTP infrastructure adapters.

Provides a single source of truth for:
- Which exceptions are transient and worth retrying.
- Which HTTP status codes are retryable (429, 5xx) vs permanent (other 4xx).
- Backoff parameters and attempt limits.
- A structured-log callback that fires on each retry attempt.

Usage
-----
Apply `http_retry(max_attempts=3)` as a decorator on any async method that
performs an HTTP request and may raise httpx exceptions::

    class MyFetcher:
        @http_retry(max_attempts=3)
        async def fetch(self, url: str) -> str:
            ...
"""

from __future__ import annotations

import httpx
import structlog
import tenacity

log = structlog.get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* is a transient HTTP error worth retrying.

    Retryable conditions:
    - Any httpx network-layer error (timeout, connection reset, etc.).
    - HTTP 429 Too Many Requests.
    - HTTP 5xx Server Error (the server may recover).

    Non-retryable conditions:
    - HTTP 4xx (except 429): permanent client errors such as 404 Not Found
      or 403 Forbidden will not be fixed by retrying.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    # TimeoutException, ConnectError, RemoteProtocolError, etc.
    return isinstance(exc, httpx.TransportError)


def _log_retry(retry_state: tenacity.RetryCallState) -> None:
    """Structured-log callback invoked before each retry sleep."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "http.retry",
        attempt=retry_state.attempt_number,
        wait_s=round(retry_state.next_action.sleep, 2)
        if retry_state.next_action
        else 0,
        reason=f"{type(exc).__name__}: {exc}" if exc else "unknown",
    )


def http_retry(*, max_attempts: int = 3) -> tenacity.AsyncRetrying:
    """Return a tenacity retry decorator for async HTTP methods.

    Parameters
    ----------
    max_attempts:
        Total number of attempts (1 = no retries, 3 = up to 2 retries).

    Backoff
    -------
    Exponential starting at 1 s, multiplier 2, capped at 30 s.
    Attempts:  1 (immediate) → wait 1 s → attempt 2 → wait 2 s → attempt 3.
    """
    return tenacity.retry(
        retry=tenacity.retry_if_exception(_is_retryable),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=30),
        stop=tenacity.stop_after_attempt(max_attempts),
        before_sleep=_log_retry,
        reraise=True,
    )
