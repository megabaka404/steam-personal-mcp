from __future__ import annotations

from typing import Any

from errors import AppError
from models.store import StoreGame, normalize_store_type, parse_price, price_payload


class StoreService:
    def __init__(self, store, steam, library, resolver, settings, price_history=None) -> None:
        self.store = store
        self.steam = steam
        self.library = library
        self.resolver = resolver
        self.settings = settings
        self.price_history = price_history

    def search_store(self, query: str, count: int = 20) -> dict[str, Any]:
        if not (query or "").strip():
            raise AppError("INVALID_ARGUMENT", "query must not be empty.")
        items = self.store.search(query.strip(), max(1, min(50, count)))
        owned = self._owned_ids()
        wishlist = self._wishlist_ids_or_none()
        rows = [self._from_search(item, owned, wishlist).public_dict(compact=True) for item in items]
        return {"query": query, "count": len(rows), "games": rows}

    def get_game(self, *, game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        resolved = self.resolver.resolve(game=game, appid=appid)
        raw = self.store.details(resolved.appid)
        if raw is None:
            raise AppError("STORE_UNAVAILABLE", "Steam Store details are not available for this AppID.", {"appid": resolved.appid})
        item = self._from_details(raw, resolved.appid)
        item.owned_by_user = resolved.appid in self._owned_ids()
        wishlist = self._wishlist_ids_or_none()
        item.wishlisted_by_user = resolved.appid in wishlist if wishlist is not None else None
        return item.public_dict()

    def specials(self, *, count: int = 50, min_discount: int = 0, max_price: float | None = None, min_price: float | None = None, sort_by: str = "discount", exclude_owned: bool = False) -> list[dict[str, Any]]:
        if sort_by not in {"discount", "price", "reviews", "name"}:
            raise AppError("INVALID_ARGUMENT", "sort_by must be discount, price, reviews, or name.")
        if not 0 <= min_discount <= 100:
            raise AppError("INVALID_ARGUMENT", "min_discount must be between 0 and 100.")
        owned = self._owned_ids()
        wishlist = self._wishlist_ids_or_none()
        rows = []
        for raw in self.store.featured_items():
            item = self._from_search(raw, owned, wishlist)
            if not item.price or item.price.discount_percent < min_discount:
                continue
            price = item.price.public_dict().get("price")
            if max_price is not None and (price is None or price > max_price):
                continue
            if min_price is not None and (price is None or price < min_price):
                continue
            if exclude_owned and item.owned_by_user:
                continue
            rows.append(item.public_dict(compact=True))
        rows.sort(key=_sort_key(sort_by))
        return rows[: max(1, min(200, count))]

    def deep_discounts(self, min_discount: int = 70, count: int = 50, exclude_owned: bool = False) -> list[dict[str, Any]]:
        return self.specials(count=count, min_discount=min_discount, sort_by="discount", exclude_owned=exclude_owned)

    def search_sales(self, *, query: str | None = None, min_discount: int = 0, max_price: float | None = None, genres: list[str] | None = None, count: int = 30, exclude_owned: bool = False) -> list[dict[str, Any]]:
        if query:
            raw_items = self.store.search(query, min(50, max(1, count)))
            owned, wishlist = self._owned_ids(), self._wishlist_ids_or_none()
            rows = [self._from_search(raw, owned, wishlist) for raw in raw_items]
        else:
            rows = [self._from_search(raw, self._owned_ids(), self._wishlist_ids_or_none()) for raw in self.store.featured_items()]
        result = []
        for item in rows:
            if not item.price or item.price.discount_percent < min_discount:
                continue
            final_price = item.price.public_dict().get("price")
            if max_price is not None and (final_price is None or final_price > max_price):
                continue
            if exclude_owned and item.owned_by_user:
                continue
            if genres:
                detail = self.store.details(item.appid)
                if not _has_genres(detail, genres):
                    continue
                if detail:
                    item = self._from_details(detail, item.appid)
                    item.owned_by_user = item.appid in self._owned_ids()
            result.append(item.public_dict(compact=True))
        result.sort(key=lambda item: (-((item.get("price") or {}).get("discount_percent") or 0), (item.get("price") or {}).get("price") or 0, item.get("name", "").casefold()))
        return result[: max(1, min(200, count))]

    def compare(self, games: list[str | int]) -> list[dict[str, Any]]:
        if not games or len(games) > 10:
            raise AppError("INVALID_ARGUMENT", "games must contain between 1 and 10 items.")
        result = []
        for value in games:
            resolved = self.resolver.resolve(appid=value if isinstance(value, int) else None, game=value if isinstance(value, str) else None)
            raw = self.store.details(resolved.appid)
            if raw:
                item = self._from_details(raw, resolved.appid)
                item.owned_by_user = resolved.appid in self._owned_ids()
                wishlist = self._wishlist_ids_or_none()
                item.wishlisted_by_user = resolved.appid in wishlist if wishlist is not None else None
                result.append(item.public_dict(compact=True))
        return result

    def dlc(self, *, game: str | None = None, appid: int | None = None, only_discounted: bool = False) -> dict[str, Any]:
        resolved = self.resolver.resolve(game=game, appid=appid)
        base = self.store.details(resolved.appid)
        if not base:
            raise AppError("STORE_UNAVAILABLE", "Steam Store details are not available for this game.")
        rows = []
        for dlc_appid in base.get("dlc") or []:
            try:
                dlc_id = int(dlc_appid)
            except (TypeError, ValueError):
                continue
            detail = self.store.details(dlc_id)
            if not detail:
                continue
            item = self._from_details(detail, dlc_id)
            if only_discounted and (not item.price or item.price.discount_percent <= 0):
                continue
            rows.append(item.public_dict(compact=True))
        return {"appid": resolved.appid, "game_name": str(base.get("name") or resolved.name or f"App {resolved.appid}"), "count": len(rows), "dlc": rows}

    def wishlist(self, *, only_discounted: bool = False, limit: int = 100) -> dict[str, Any]:
        try:
            raw_items = self.steam.get_wishlist()
        except AppError as exc:
            return {"available": False, "supported": False, "reason": exc.message, "items": []}
        owned = self._owned_ids()
        wishlist_ids = {_appid(item) for item in raw_items}
        rows = []
        for raw in raw_items[: max(1, min(200, limit))]:
            appid = _appid(raw)
            if not appid:
                continue
            detail = self.store.details(appid)
            if not detail:
                continue
            item = self._from_details(detail, appid)
            item.owned_by_user = appid in owned
            item.wishlisted_by_user = True
            if only_discounted and (not item.price or item.price.discount_percent <= 0):
                continue
            row = item.public_dict(compact=True)
            row["priority"] = raw.get("priority")
            row["date_added"] = raw.get("date_added")
            if self.price_history is not None:
                self.price_history.observe(appid=appid, name=item.name, price=row.get("price"))
            rows.append(row)
        return {"available": True, "supported": True, "total": len(raw_items), "count": len(rows), "items": rows}

    def wishlist_sales(self, *, min_discount: int = 0, max_price: float | None = None, sort_by: str = "discount", limit: int = 100) -> dict[str, Any]:
        wishlist = self.wishlist(only_discounted=False, limit=limit)
        if not wishlist.get("available"):
            return wishlist
        rows = []
        for item in wishlist["items"]:
            price = item.get("price") or {}
            if price.get("discount_percent", 0) < min_discount or price.get("discount_percent", 0) <= 0:
                continue
            if max_price is not None and (price.get("price") is None or price["price"] > max_price):
                continue
            rows.append(item)
        rows.sort(key=_sort_key(sort_by))
        return {**wishlist, "items": rows, "count": len(rows)}

    def wishlist_best_deals(self, limit: int = 20) -> dict[str, Any]:
        sales = self.wishlist_sales(limit=100)
        if not sales.get("available"):
            return sales
        rows = []
        for item in sales["items"]:
            price = item.get("price") or {}
            discount = float(price.get("discount_percent") or 0)
            review = float(item.get("review_percentage") or 0)
            final_price = float(price.get("price") or 0)
            score = discount * 0.6 + review * 0.35 - min(final_price, 100) * 0.05
            rows.append({**item, "deal_score": round(score, 2), "deal_reasons": [f"{int(discount)}% discount", f"{int(review)}% positive reviews"] if review else [f"{int(discount)}% discount"]})
        rows.sort(key=lambda item: item["deal_score"], reverse=True)
        return {**sales, "items": rows[: max(1, min(100, limit))], "count": min(len(rows), max(1, min(100, limit)))}

    def _from_search(self, raw: dict[str, Any], owned: set[int], wishlist: set[int] | None) -> StoreGame:
        appid = int(raw.get("appid", raw.get("id", 0)) or 0)
        price_raw = price_payload(raw)
        review = self._review_summary(appid)
        item = StoreGame(
            appid=appid,
            name=str(raw.get("name") or f"App {appid}"),
            type=normalize_store_type(raw.get("type")),
            price=parse_price(price_raw),
            review_score=_int_or_none(raw.get("review_score")) if raw.get("review_score") is not None else (review or {}).get("review_score"),
            review_percentage=_int_or_none(raw.get("review_percentage")) if raw.get("review_percentage") is not None else (review or {}).get("review_percentage"),
            review_count=_int_or_none(raw.get("review_count")) if raw.get("review_count") is not None else (review or {}).get("review_count"),
            owned_by_user=appid in owned,
            wishlisted_by_user=(appid in wishlist if wishlist is not None else None),
        )
        return item

    def _from_details(self, raw: dict[str, Any], appid: int, *, include_reviews: bool = True) -> StoreGame:
        review = self._review_summary(appid) if include_reviews else None
        return StoreGame(
            appid=appid,
            name=str(raw.get("name") or f"App {appid}"),
            type=normalize_store_type(raw.get("type")),
            header_image=raw.get("header_image"),
            developers=raw.get("developers") or [],
            publishers=raw.get("publishers") or [],
            release_date=raw.get("release_date"),
            genres=raw.get("genres") or [],
            categories=raw.get("categories") or [],
            short_description=raw.get("short_description"),
            price=parse_price(raw.get("price_overview")),
            dlc=[int(value) for value in (raw.get("dlc") or []) if str(value).isdigit()],
            supported_languages=raw.get("supported_languages"),
            platforms=raw.get("platforms") or {},
            metacritic=raw.get("metacritic"),
            recommendations=raw.get("recommendations"),
            review_score=(review or {}).get("review_score"),
            review_percentage=(review or {}).get("review_percentage"),
            review_count=(review or {}).get("review_count"),
        )

    def _review_summary(self, appid: int) -> dict[str, Any] | None:
        method = getattr(self.store, "review_summary", None)
        if method is None:
            return None
        try:
            value = method(appid)
            return value if isinstance(value, dict) else None
        except Exception:
            # Review data is enrichment only; never break Store data.
            return None

    def _owned_ids(self) -> set[int]:
        try:
            return {game.appid for game in self.library.owned_games()}
        except AppError:
            return set()

    def _wishlist_ids_or_none(self) -> set[int] | None:
        try:
            return {_appid(item) for item in self.steam.get_wishlist() if _appid(item)}
        except AppError:
            return None


def _appid(item: dict[str, Any]) -> int:
    try:
        return int(item.get("appid", item.get("id", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _sort_key(sort_by: str):
    if sort_by == "price":
        return lambda item: ((item.get("price") or {}).get("price") is None, (item.get("price") or {}).get("price") or 0)
    if sort_by == "reviews":
        return lambda item: -(item.get("review_percentage") or 0)
    if sort_by == "name":
        return lambda item: item.get("name", "").casefold()
    return lambda item: -((item.get("price") or {}).get("discount_percent") or 0)


def _has_genres(detail: dict[str, Any] | None, genres: list[str]) -> bool:
    if not detail:
        return False
    names = {str(item.get("description", "")).casefold() for item in (detail.get("genres") or [])}
    return any(any(str(genre).casefold() in name or name in str(genre).casefold() for name in names) for genre in genres)
