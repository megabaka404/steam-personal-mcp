from __future__ import annotations

import math
import re
from typing import Any

from errors import AppError


CORE_FEATURES = (
    "roguelike", "roguelite", "deckbuilder", "deckbuilding", "card battler",
    "turn-based", "soulslike", "metroidvania", "co-op", "cooperative",
    "survival", "simulation", "city builder", "4x", "tactical", "strategy",
    "rpg", "action", "adventure", "indie", "multiplayer", "single-player",
)


class StoreRecommendationService:
    """Deterministic Store recommendations backed by public Store metadata."""

    def __init__(self, store_client, store_service, library, steam, resolver) -> None:
        self.store = store_client
        self.store_service = store_service
        self.library = library
        self.steam = steam
        self.resolver = resolver

    def recommend_store_for_me(
        self,
        *,
        count: int = 10,
        max_price: float | None = None,
        min_discount: int = 0,
        include_wishlist: bool = True,
        exclude_early_access: bool = False,
    ) -> dict[str, Any]:
        count = _bounded(count, 1, 50)
        _validate_discount(min_discount)
        if max_price is not None and max_price < 0:
            raise AppError("INVALID_ARGUMENT", "max_price must be non-negative.")
        owned = self._owned_ids()
        wishlist = self._wishlist_ids()
        profile = self._preference_profile(owned)
        terms = _profile_terms(profile)
        raw_candidates = self._candidate_pool(terms, wishlist if include_wishlist else set(), include_wishlist=include_wishlist)
        rows = []
        dominant = _dominant_features(profile)
        for appid, raw in raw_candidates.items():
            if appid in owned:
                continue
            item, detail = self._candidate(appid, raw, owned, wishlist)
            if not _is_game_candidate(item):
                continue
            if exclude_early_access and _is_early_access(detail):
                continue
            if not _within_price(item, max_price) or not _discount_at_least(item, min_discount):
                continue
            similarity, similarity_reasons, anchor = _best_profile_match(detail, profile)
            price = item.price.public_dict() if item.price else {}
            score = similarity * 0.68
            reasons: list[str] = []
            if similarity > 0:
                reasons.extend(similarity_reasons[:2])
            if anchor and anchor["game"].total_hours >= 20:
                reasons.append(f"Similar to high-playtime {anchor['game'].name}")
            if anchor and anchor["game"].recent_hours > 0:
                reasons.append(f"Matches recent activity in {anchor['game'].name}")
            if dominant:
                reasons.append(f"Matches {', '.join(dominant[:3])} preference")
            if appid in wishlist:
                score += 12
                reasons.append("Already on your wishlist")
            discount = int(price.get("discount_percent") or 0)
            if discount > 0:
                score += min(12, discount * 0.12)
                reasons.append(f"Currently {discount}% off")
            if item.review_percentage is not None:
                score += min(6, item.review_percentage * 0.06)
            if not reasons:
                reasons.append("Limited public Store metadata; low-confidence match")
            row = item.public_dict(compact=True)
            row.update({"score": round(min(100, score), 2), "reasons": _unique(reasons), "discount_percent": discount})
            rows.append(row)
        rows.sort(key=lambda row: (-row["score"], row["name"].casefold(), row["appid"]))
        return {
            "count": min(count, len(rows)),
            "candidate_source": "Steam public Store search, featured specials, and wishlist; not a full catalog scan",
            "games": rows[:count],
        }

    def find_similar_games(
        self,
        *,
        game: str | None = None,
        appid: int | None = None,
        count: int = 20,
        exclude_owned: bool = True,
        max_price: float | None = None,
    ) -> dict[str, Any]:
        count = _bounded(count, 1, 50)
        if max_price is not None and max_price < 0:
            raise AppError("INVALID_ARGUMENT", "max_price must be non-negative.")
        resolved = self.resolver.resolve(game=game, appid=appid)
        source_raw = self.store.details(resolved.appid)
        if not source_raw:
            raise AppError("STORE_UNAVAILABLE", "Steam Store details are not available for the source game.", {"appid": resolved.appid})
        owned = self._owned_ids()
        wishlist = self._wishlist_ids()
        source_item = self.store_service._from_details(source_raw, resolved.appid)
        source_item.owned_by_user = resolved.appid in owned
        source_item.wishlisted_by_user = resolved.appid in wishlist if wishlist is not None else None
        source_features = _features(source_raw)
        terms = sorted(source_features["genres"] | source_features["categories"] | source_features["keywords"])
        raw_candidates = self._candidate_pool(terms[:4], wishlist, include_wishlist=True)
        rows = []
        for candidate_appid, raw in raw_candidates.items():
            if candidate_appid == resolved.appid or (exclude_owned and candidate_appid in owned):
                continue
            item, detail = self._candidate(candidate_appid, raw, owned, wishlist)
            if not _is_game_candidate(item) or not _within_price(item, max_price):
                continue
            score, reasons = _compare_features(source_features, _features(detail))
            if score <= 0:
                continue
            row = item.public_dict(compact=True)
            row.update({"similarity_score": round(score, 2), "similarity_reasons": reasons or ["Shared public Store metadata"]})
            rows.append(row)
        rows.sort(key=lambda row: (-row["similarity_score"], row["name"].casefold(), row["appid"]))
        return {
            "source_game": source_item.public_dict(),
            "count": min(count, len(rows)),
            "candidate_source": "Steam public Store metadata; no official Steam similarity endpoint",
            "games": rows[:count],
        }

    def _candidate_pool(self, terms: list[str], wishlist: set[int], *, include_wishlist: bool) -> dict[int, dict[str, Any]]:
        candidates: dict[int, dict[str, Any]] = {}
        try:
            for raw in self.store.featured_items():
                _add_candidate(candidates, raw)
        except AppError:
            pass
        if include_wishlist:
            for appid in wishlist:
                candidates.setdefault(appid, {"appid": appid, "id": appid})
        for term in terms[:4]:
            if len(term) < 3:
                continue
            try:
                for raw in self.store.search(term, 15):
                    _add_candidate(candidates, raw)
            except AppError:
                continue
        return dict(list(candidates.items())[:60])

    def _candidate(self, appid: int, raw: dict[str, Any], owned: set[int], wishlist: set[int] | None, *, include_reviews: bool = True):
        try:
            detail = self.store.details(appid)
        except AppError:
            detail = None
        if detail:
            item = self.store_service._from_details(detail, appid, include_reviews=include_reviews)
        else:
            detail = raw
            item = self.store_service._from_search(raw, owned, wishlist)
        item.owned_by_user = appid in owned
        item.wishlisted_by_user = appid in wishlist if wishlist is not None else None
        return item, detail

    def _preference_profile(self, owned: set[int]) -> list[dict[str, Any]]:
        try:
            library = self.library.owned_games()
        except AppError:
            return []
        games = [game for game in library if game.appid in owned and game.playtime_forever > 0]
        games.sort(key=lambda item: (item.playtime_forever + item.playtime_2weeks * 2, item.name.casefold()), reverse=True)
        profile = []
        for game in games[:12]:
            try:
                detail = self.store.details(game.appid)
            except AppError:
                continue
            if not detail:
                continue
            profile.append({"game": game, "features": _features(detail), "weight": 1 + math.log1p(game.total_hours) + game.recent_hours * 0.5})
        return profile

    def _owned_ids(self) -> set[int]:
        try:
            return {game.appid for game in self.library.owned_games()}
        except AppError:
            return set()

    def _wishlist_ids(self) -> set[int] | None:
        try:
            return {_appid(item) for item in self.steam.get_wishlist() if _appid(item)}
        except AppError:
            return None


def _best_profile_match(detail: dict[str, Any], profile: list[dict[str, Any]]):
    if not profile:
        return 0.0, [], None
    candidate = _features(detail)
    ranked = []
    for entry in profile:
        score, reasons = _compare_features(entry["features"], candidate)
        ranked.append((score, reasons, entry))
    ranked.sort(key=lambda value: (value[0], value[2]["weight"]), reverse=True)
    best = ranked[0]
    return best[0], best[1], best[2]


def _compare_features(source: dict[str, set[str]], candidate: dict[str, set[str]]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    genre_overlap = source["genres"] & candidate["genres"]
    if source["genres"] and genre_overlap:
        score += 38 * len(genre_overlap) / max(1, len(source["genres"]))
        reasons.extend(f"Shared {value.title()} genre" for value in sorted(genre_overlap)[:2])
    category_overlap = source["categories"] & candidate["categories"]
    if source["categories"] and category_overlap:
        score += 25 * len(category_overlap) / max(1, len(source["categories"]))
        reasons.extend(f"Shared {value.title()} category" for value in sorted(category_overlap)[:2])
    keyword_overlap = source["keywords"] & candidate["keywords"]
    if source["keywords"] and keyword_overlap:
        score += 25 * len(keyword_overlap) / max(1, len(source["keywords"]))
        reasons.extend(f"Shared {value.title()} feature" for value in sorted(keyword_overlap)[:2])
    if source["developers"] & candidate["developers"]:
        score += 6
        reasons.append("Same developer")
    if source["publishers"] & candidate["publishers"]:
        score += 6
        reasons.append("Same publisher")
    return min(100.0, score), _unique(reasons)


def _features(detail: dict[str, Any]) -> dict[str, set[str]]:
    genres = {_text(item.get("description") if isinstance(item, dict) else item) for item in (detail.get("genres") or [])}
    categories = {_text(item.get("description") if isinstance(item, dict) else item) for item in (detail.get("categories") or [])}
    tags = detail.get("tags") or {}
    if isinstance(tags, dict):
        categories.update(_text(key) for key in tags)
    elif isinstance(tags, list):
        categories.update(_text(item.get("name") if isinstance(item, dict) else item) for item in tags)
    text = " ".join([str(detail.get("name") or ""), str(detail.get("short_description") or ""), *genres, *categories])
    keywords = {term for term in CORE_FEATURES if term in text.casefold()}
    return {
        "genres": {item for item in genres if item},
        "categories": {item for item in categories if item},
        "keywords": keywords,
        "developers": {_text(item) for item in (detail.get("developers") or []) if _text(item)},
        "publishers": {_text(item) for item in (detail.get("publishers") or []) if _text(item)},
    }


def _profile_terms(profile: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, float] = {}
    for entry in profile:
        for group in ("genres", "categories", "keywords"):
            for value in entry["features"][group]:
                counts[value] = counts.get(value, 0) + entry["weight"]
    return [value for value, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]


def _dominant_features(profile: list[dict[str, Any]]) -> list[str]:
    return [value for value in _profile_terms(profile) if value in {"action", "adventure", "indie", "rpg", "strategy", "simulation", "roguelike", "roguelite", "deckbuilder", "deckbuilding"}]


def _is_early_access(detail: dict[str, Any]) -> bool:
    if detail.get("is_early_access") is True:
        return True
    values = []
    for item in detail.get("categories") or []:
        values.append(item.get("description") if isinstance(item, dict) else item)
    values.append(detail.get("type"))
    return any("early access" in str(value).casefold() for value in values)


def _is_game_candidate(item) -> bool:
    name = (item.name or "").casefold()
    if name.endswith((" soundtrack", " original soundtrack", " ost")):
        return False
    return (item.type or "unknown").casefold() in {"game", "app", "unknown"}


def _within_price(item, max_price: float | None) -> bool:
    if max_price is None:
        return True
    price = item.price.public_dict().get("price") if item.price else None
    return price is not None and price <= max_price


def _discount_at_least(item, minimum: int) -> bool:
    return bool(item.price and item.price.discount_percent >= minimum)


def _add_candidate(target: dict[int, dict[str, Any]], raw: dict[str, Any]) -> None:
    appid = _appid(raw)
    if appid > 0:
        target.setdefault(appid, raw)


def _appid(raw: dict[str, Any]) -> int:
    try:
        return int(raw.get("appid", raw.get("id", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _bounded(value: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return minimum


def _validate_discount(value: int) -> None:
    if not 0 <= value <= 100:
        raise AppError("INVALID_ARGUMENT", "min_discount must be between 0 and 100.")
