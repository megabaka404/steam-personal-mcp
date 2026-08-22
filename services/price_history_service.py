from __future__ import annotations

from typing import Any

from errors import AppError


class PriceHistoryService:
    def __init__(self, store_service, history_store) -> None:
        self.store = store_service
        self.history = history_store

    def wishlist_history(self, *, appid: int | None = None, limit: int = 100) -> dict[str, Any]:
        _validate_appid(appid)
        self._observe_wishlist()
        summaries = self.history.summary(appid=appid, limit=max(1, min(1000, limit)))
        if appid is not None:
            summary = next((item for item in summaries if item["appid"] == appid), None)
            if summary is None:
                return {
                    "available": True,
                    "source": "MCP-observed price history",
                    "appid": appid,
                    "count": 0,
                    "records": [],
                    "message": "No price observation has been recorded for this AppID yet.",
                }
            return {"available": True, "source": "MCP-observed price history", **summary}
        return {"available": True, "source": "MCP-observed price history", "count": len(summaries), "items": summaries}

    def wishlist_price_drops(self) -> dict[str, Any]:
        wishlist = self._observe_wishlist()
        if not wishlist.get("available"):
            return wishlist
        wishlist_ids = {int(item.get("appid", 0)) for item in wishlist.get("items", []) if item.get("appid")}
        summaries = self.history.summary(limit=5000)
        tracked = [item for item in summaries if item["appid"] in wishlist_ids]
        drops = [item for item in tracked if item.get("cheaper_than_previous_observation")]
        return {
            "available": True,
            "source": "MCP-observed price history",
            "tracked_count": len(tracked),
            "count": len(drops),
            "items": drops,
            "note": "Historical lows and drops are based only on observations made by this MCP instance.",
        }

    def _observe_wishlist(self) -> dict[str, Any]:
        return self.store.wishlist(limit=200)


def _validate_appid(appid: int | None) -> None:
    if appid is not None:
        try:
            if int(appid) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise AppError("INVALID_ARGUMENT", "appid must be a positive integer.")
