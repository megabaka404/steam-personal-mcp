from __future__ import annotations

from typing import Any

from cache.memory_cache import MemoryTTLCache
from clients.http_client import JsonHttpClient
from config import Settings


class StoreClient:
    """Public Steam Store JSON/API client; no HTML scraping or account cookies."""

    store_base = "https://store.steampowered.com"

    def __init__(self, settings: Settings, cache: MemoryTTLCache, http: JsonHttpClient | None = None) -> None:
        self.settings = settings
        self.cache = cache
        self.http = http or JsonHttpClient(
            timeout=settings.http_timeout,
            max_retries=settings.max_retries,
            min_request_interval=settings.min_request_interval,
            cache=cache,
        )

    def search(self, query: str, count: int = 20) -> list[dict[str, Any]]:
        data = self.http.get_json(
            f"{self.store_base}/api/storesearch/",
            params={"term": query, "cc": self.settings.store_country, "l": self.settings.store_language, "start": 0, "count": min(50, count), "infinite": 1},
            cache_key=f"store-search:{self.settings.store_country}:{query.casefold()}:{count}", cache_ttl=900,
            error_context="Steam Store search API",
        )
        return data.get("items") or [] if isinstance(data, dict) else []

    def details(self, appid: int) -> dict[str, Any] | None:
        data = self.http.get_json(
            f"{self.store_base}/api/appdetails",
            params={"appids": appid, "cc": self.settings.store_country, "l": self.settings.store_language},
            cache_key=f"store-details:{self.settings.store_country}:{appid}", cache_ttl=1800,
            error_context="Steam Store app details API",
        )
        if not isinstance(data, dict):
            return None
        item = data.get(str(appid)) or data.get(appid)
        if not isinstance(item, dict) or not item.get("success"):
            return None
        return item.get("data") if isinstance(item.get("data"), dict) else None

    def review_summary(self, appid: int) -> dict[str, Any] | None:
        """Read Steam's public aggregate review summary, never individual reviews."""
        data = self.http.get_json(
            f"{self.store_base}/appreviews/{appid}",
            params={"json": 1, "language": "all", "filter": "summary"},
            cache_key=f"store-reviews:{appid}", cache_ttl=1800,
            error_context="Steam Store review summary API",
        )
        summary = data.get("query_summary") if isinstance(data, dict) else None
        if not isinstance(summary, dict):
            return None
        total = _int_or_none(summary.get("total_reviews"))
        positive = _int_or_none(summary.get("total_positive"))
        percentage = None
        if total and total > 0 and positive is not None:
            percentage = round(positive * 100 / total)
        recent_percentage = None
        recent_count = None
        recent_source = None
        recent_reason = "Recent review summary was not available."
        try:
            recent_data = self.http.get_json(
                f"{self.store_base}/appreviews/{appid}",
                params={"json": 1, "language": "all", "filter": "recent", "num_per_page": 100},
                cache_key=f"store-reviews-recent:{appid}", cache_ttl=1800,
                error_context="Steam Store recent review summary API",
            )
            recent = recent_data.get("query_summary") if isinstance(recent_data, dict) else None
            if isinstance(recent, dict):
                candidate_count = _int_or_none(recent.get("total_reviews"))
                recent_positive = _int_or_none(recent.get("total_positive"))
                # Steam has returned lifetime-looking query_summary data for
                # filter=recent in the wild. Do not label it recent unless the
                # aggregate is observably distinct from the overall summary.
                if candidate_count and recent_positive is not None and candidate_count != total:
                    recent_count = candidate_count
                    recent_percentage = round(recent_positive * 100 / recent_count)
                    recent_source = "Steam appreviews filter=recent query_summary"
                    recent_reason = None
                else:
                    recent_reason = "Steam appreviews filter=recent returned no independently verifiable recent aggregate."
        except Exception:
            # Recent review enrichment is optional and must not break Store details.
            recent_reason = "Steam appreviews recent review request failed."
        return {
            "review_score": _int_or_none(summary.get("review_score")),
            "review_percentage": percentage,
            "review_count": total,
            "recent_review_score": None,
            "recent_review_percentage": recent_percentage,
            "recent_review_count": recent_count,
            "recent_review_available": recent_count is not None and recent_percentage is not None,
            "recent_review_source": recent_source,
            "recent_review_reason": recent_reason,
            "review_score_desc": summary.get("review_score_desc"),
        }

    def featured(self) -> dict[str, Any]:
        return self.http.get_json(
            f"{self.store_base}/api/featuredcategories/",
            params={"cc": self.settings.store_country, "l": self.settings.store_language},
            cache_key=f"store-featured:{self.settings.store_country}:{self.settings.store_language}", cache_ttl=600,
            error_context="Steam Store featured API",
        )

    def featured_items(self) -> list[dict[str, Any]]:
        data = self.featured()
        items: list[dict[str, Any]] = []
        for key in ("specials", "0", "1", "2", "3", "4", "5", "6", "large_capsules", "featured_win", "featured_mac", "featured_linux"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, dict):
                value = value.get("items", [])
            if isinstance(value, list):
                items.extend(value)
        seen: set[int] = set()
        unique = []
        for item in items:
            try:
                appid = int(item.get("id", item.get("appid")))
            except (TypeError, ValueError):
                continue
            if appid not in seen:
                seen.add(appid)
                unique.append({**item, "appid": appid})
        return unique


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
