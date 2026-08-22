from __future__ import annotations

import time
import logging
from threading import Lock
from typing import Any

import httpx

from errors import AppError
from cache.memory_cache import MemoryTTLCache


class JsonHttpClient:
    """Defensive JSON client: timeout, bounded retry, backoff, rate limit and cache."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 2,
        min_request_interval: float = 0.15,
        cache: MemoryTTLCache | None = None,
        transport: httpx.BaseTransport | None = None,
        user_agent: str = "steam-personal-mcp/0.1 (+https://github.com/)",
    ) -> None:
        # httpx can log full request URLs at INFO; Steam Web API keys are query
        # parameters, so keep those request logs disabled by default.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.min_request_interval = max(0.0, min_request_interval)
        self.cache = cache or MemoryTTLCache()
        self.user_agent = user_agent
        self._last_request = 0.0
        self._rate_lock = Lock()
        self._client = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": user_agent, "Accept": "application/json"})
        self.last_connectivity: str = "not_checked"

    def close(self) -> None:
        self._client.close()

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_ttl: float = 0,
        error_context: str = "Steam service",
    ) -> Any:
        if cache_key and cache_ttl > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        last_error: AppError | None = None
        for attempt in range(self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self._client.get(url, params=params)
                self.last_connectivity = "ok" if response.status_code < 400 else f"http_{response.status_code}"
            except httpx.TimeoutException as exc:
                last_error = AppError("NETWORK_ERROR", f"{error_context} timed out.", {"reason": type(exc).__name__})
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    continue
                raise last_error
            except httpx.HTTPError as exc:
                last_error = AppError("NETWORK_ERROR", f"Could not reach {error_context}.", {"reason": type(exc).__name__})
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    continue
                raise last_error

            if response.status_code == 429:
                last_error = AppError("RATE_LIMITED", f"{error_context} rate limited the request.")
                if attempt < self.max_retries:
                    retry_after = _retry_after(response)
                    time.sleep(retry_after if retry_after is not None else 0.5 * (2**attempt))
                    continue
                raise last_error
            if response.status_code in {500, 502, 503, 504}:
                last_error = AppError("NETWORK_ERROR", f"{error_context} returned a temporary server error.", {"status": response.status_code})
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    continue
                raise last_error
            if response.status_code in {401, 403}:
                raise AppError("HTTP_UNAUTHORIZED", f"{error_context} rejected the request.", {"status": response.status_code})
            if response.status_code >= 400:
                raise AppError("NETWORK_ERROR", f"{error_context} returned HTTP {response.status_code}.", {"status": response.status_code})
            try:
                data = response.json()
            except (ValueError, TypeError) as exc:
                raise AppError("NETWORK_ERROR", f"{error_context} returned malformed JSON.", {"reason": type(exc).__name__}) from exc
            if cache_key and cache_ttl > 0:
                self.cache.set(cache_key, data, cache_ttl)
            return data
        raise last_error or AppError("NETWORK_ERROR", f"Could not read {error_context}.")

    def _wait_for_rate_limit(self) -> None:
        with self._rate_lock:
            wait = self.min_request_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(4.0, 0.35 * (2**attempt)))


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return max(0.0, min(10.0, float(value))) if value else None
    except ValueError:
        return None
