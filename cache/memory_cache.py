from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float


class MemoryTTLCache:
    """Small process-local TTL cache with transparent hit/miss counters."""

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > now:
                self._hits += 1
                return entry.value
            if entry is not None:
                self._entries.pop(key, None)
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl: float) -> Any:
        now = monotonic()
        with self._lock:
            self._entries[key] = CacheEntry(value, now + max(0.0, ttl), now)
        return value

    def get_or_set(self, key: str, ttl: float, factory):
        value = self.get(key)
        if value is not None:
            return value
        return self.set(key, factory(), ttl)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def snapshot(self) -> dict[str, Any]:
        now = monotonic()
        with self._lock:
            expired = [key for key, value in self._entries.items() if value.expires_at <= now]
            for key in expired:
                self._entries.pop(key, None)
            return {
                "entries": [
                    {
                        "key": key,
                        "ttl_seconds": round(max(0.0, value.expires_at - now), 1),
                    }
                    for key, value in sorted(self._entries.items())
                ],
                "entry_count": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
            }
