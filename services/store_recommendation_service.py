from __future__ import annotations

import math
from typing import Any

from errors import AppError
from services.recommendation_features import (
    best_profile_match,
    compare_features,
    extract_features,
    profile_evidence,
    profile_terms,
    unique,
)


class StoreRecommendationService:
    """Retrieve Store candidates and package evidence for an LLM to judge."""

    def __init__(self, store_client, store_service, library, steam, resolver) -> None:
        self.store = store_client
        self.store_service = store_service
        self.library = library
        self.steam = steam
        self.resolver = resolver

    def recommend_store_for_me(
        self,
        *,
        count: int = 15,
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
        terms = profile_terms(profile)
        raw_candidates = self._candidate_pool(terms, wishlist if include_wishlist and wishlist is not None else set(), include_wishlist=include_wishlist)
        rows = []
        for appid, raw in raw_candidates.items():
            if appid in owned:
                continue
            # Wishlist IDs can re-enter through featured specials or Store search.
            # Apply the exclusion after all candidate sources have been merged.
            if not include_wishlist and wishlist is not None and appid in wishlist:
                continue
            item, detail = self._candidate(appid, raw, owned, wishlist)
            if not _is_game_candidate(item):
                continue
            if exclude_early_access and _early_access_status(detail) is True:
                continue
            if not _within_price(item, max_price) or not _discount_at_least(item, min_discount):
                continue
            context = self._candidate_context(item, detail, profile, wishlist, raw.get("_candidate_sources", []))
            discount = context["discount_percent"]
            score = context["candidate_score"]
            row = item.public_dict(compact=True)
            row.update(context)
            row.update({"score": score, "score_deprecated": True, "score_note": "Deprecated compatibility alias for candidate_score; not final recommendation confidence."})
            rows.append(row)
        rows.sort(key=lambda row: (-row["candidate_score"], row["name"].casefold(), row["appid"]))
        candidate_source = "Steam public Store search and featured specials"
        if include_wishlist:
            candidate_source += ", and wishlist"
        wishlist_filter = {
            "include_wishlist": include_wishlist,
            "available": wishlist is not None,
            "applied": not include_wishlist and wishlist is not None,
        }
        if not include_wishlist and wishlist is None:
            wishlist_filter["note"] = "Wishlist data was unavailable; wishlist exclusion could not be verified."
        return {
            "count": min(count, len(rows)),
            "candidate_source": f"{candidate_source}; not a full catalog scan",
            "wishlist_filter": wishlist_filter,
            "interpretation": "Candidates and evidence only. candidate_score ranks retrieval priority and is not a final fit, purchase recommendation, or confidence score.",
            "games": rows[:count],
        }

    def _candidate_context(
        self,
        item,
        detail: dict[str, Any],
        profile: list[dict[str, Any]],
        wishlist: set[int] | None,
        candidate_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        price = item.price.public_dict() if item.price else {}
        discount = int(price.get("discount_percent") or 0)
        evidence = profile_evidence(detail, profile)
        similarity, _, _ = best_profile_match(detail, profile)
        candidate_score = _candidate_score(
            similarity,
            wishlisted=item.appid in (wishlist or set()),
            discount=discount,
            review_percentage=item.review_percentage,
        )
        tags = _public_tags(detail)
        modes = _mode_flags(detail)
        early_access = _early_access_status(detail)
        missing_data = _missing_data(item, detail, tags, modes, early_access)
        candidate_reasons: list[str] = []
        specific = evidence["matched_preferences"]
        broad_matches = sorted({value for match in evidence["all_matches"] for value in match["matched_features"]["genres"] + match["matched_features"]["categories"]})
        if specific:
            candidate_reasons.append(f"Concrete profile feature overlap: {', '.join(specific[:4])}")
        elif broad_matches:
            candidate_reasons.append("Broad genre/category overlap only; retained as weak retrieval evidence")
        elif profile:
            candidate_reasons.append("No concrete profile feature overlap; retained from the bounded Store candidate pool")
        else:
            candidate_reasons.append("No usable owned-game Store profile was available; retrieval relies on public Store signals")
        if item.appid in (wishlist or set()):
            candidate_reasons.append("Wishlist signal surfaced this candidate; wishlist status is not proof of preference fit")
        if discount > 0:
            candidate_reasons.append(f"Current {discount}% discount makes the item worth surfacing")
        if candidate_sources:
            candidate_reasons.append(f"Retrieved from {', '.join(candidate_sources[:2])}")
        potential_mismatches = _potential_mismatches(profile, evidence, modes, early_access, item)
        return {
            "current_price": price.get("price"),
            "original_price": price.get("original_price"),
            "discount_percent": discount,
            "tags": tags,
            "categories": item.categories or None,
            "singleplayer": modes["singleplayer"],
            "multiplayer": modes["multiplayer"],
            "co_op": modes["co_op"],
            "controller_support": modes["controller_support"],
            "keyboard_mouse_support": modes["keyboard_mouse_support"],
            "owned": bool(item.owned_by_user),
            "wishlisted": item.wishlisted_by_user,
            "early_access": early_access,
            "release_date": detail.get("release_date") or None,
            "high_playtime_intersections": evidence["high_playtime_intersections"],
            "recent_play_intersections": evidence["recent_intersections"],
            "matched_preferences": evidence["matched_preferences"],
            "potential_mismatches": potential_mismatches,
            "missing_data": missing_data,
            "candidate_reasons": unique(candidate_reasons),
            "reasons": unique(candidate_reasons),
            "evidence": {
                "library_games_considered": evidence["profile_games_considered"],
                "high_playtime_games": evidence["high_playtime_intersections"],
                "recently_played_games": evidence["recent_intersections"],
                "wishlist": {"wishlisted": item.wishlisted_by_user, "source": "Steam wishlist" if wishlist is not None else None},
                "candidate_sources": candidate_sources or [],
                "metadata_source": "Steam public Store appdetails/search; missing fields are not inferred",
            },
            "candidate_score": candidate_score,
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
        source_features = extract_features(source_raw)
        terms = sorted(source_features["genres"] | source_features["categories"] | source_features["tags"] | source_features["specific"])
        raw_candidates = self._candidate_pool(terms[:4], wishlist, include_wishlist=True)
        rows = []
        for candidate_appid, raw in raw_candidates.items():
            if candidate_appid == resolved.appid or (exclude_owned and candidate_appid in owned):
                continue
            item, detail = self._candidate(candidate_appid, raw, owned, wishlist)
            if not _is_game_candidate(item) or not _within_price(item, max_price):
                continue
            score, reasons = compare_features(source_features, extract_features(detail))
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
                _add_candidate(candidates, raw, "featured specials")
        except AppError:
            pass
        if include_wishlist:
            for appid in wishlist:
                candidates.setdefault(appid, {"appid": appid, "id": appid, "_candidate_sources": ["wishlist"]})
        for term in terms[:4]:
            if len(term) < 3:
                continue
            try:
                for raw in self.store.search(term, 15):
                    _add_candidate(candidates, raw, f"Store search: {term}")
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
            profile.append({"game": game, "features": extract_features(detail), "weight": 1 + math.log1p(game.total_hours) + game.recent_hours * 0.5})
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


def _candidate_score(similarity: float, *, wishlisted: bool, discount: int, review_percentage: int | None) -> float:
    """Rank retrieval priority only; never represents final user fit."""
    score = min(65.0, similarity * 0.65)
    if wishlisted:
        score += 15.0
    if discount > 0:
        score += min(10.0, discount * 0.10)
    if review_percentage is not None:
        score += min(5.0, review_percentage * 0.05)
    return round(min(100.0, score), 2)


def _public_tags(detail: dict[str, Any]) -> list[str] | None:
    tags = detail.get("tags")
    if isinstance(tags, dict):
        values = [str(value) for value in tags if str(value).strip()]
    elif isinstance(tags, list):
        values = []
        for item in tags:
            value = item.get("name") if isinstance(item, dict) else item
            if str(value or "").strip():
                values.append(str(value))
    else:
        return None
    return sorted(dict.fromkeys(value for value in values if value.strip()), key=str.casefold) or None


def _mode_flags(detail: dict[str, Any]) -> dict[str, Any]:
    values = [str(item.get("description") if isinstance(item, dict) else item).casefold() for item in (detail.get("categories") or [])]
    has_explicit_categories = bool(values)
    return {
        "singleplayer": True if any(value in {"single-player", "single player"} for value in values) else (False if has_explicit_categories and any("multi-player" in value or "multiplayer" in value for value in values) else None),
        "multiplayer": True if any("multi-player" in value or "multiplayer" in value or "online multiplayer" in value for value in values) else (False if has_explicit_categories and any(value in {"single-player", "single player"} for value in values) else None),
        "co_op": True if any("co-op" in value or "cooperative" in value for value in values) else None,
        "controller_support": "full" if any("full controller support" in value for value in values) else ("partial" if any("partial controller support" in value for value in values) else None),
        "keyboard_mouse_support": True if any("keyboard" in value and "mouse" in value for value in values) else None,
    }


def _early_access_status(detail: dict[str, Any]) -> bool | None:
    if detail.get("is_early_access") is True:
        return True
    if detail.get("is_early_access") is False:
        return False
    values = [item.get("description") if isinstance(item, dict) else item for item in (detail.get("categories") or [])]
    if any("early access" in str(value).casefold() for value in values):
        return True
    return None


def _missing_data(item, detail: dict[str, Any], tags: list[str] | None, modes: dict[str, Any], early_access: bool | None) -> list[str]:
    missing: list[str] = []
    if not item.price:
        missing.append("price")
    if item.review_percentage is None or item.review_count is None:
        missing.append("review summary")
    if not item.genres:
        missing.append("genres")
    if not item.categories:
        missing.append("categories")
    if tags is None:
        missing.append("tags not exposed by this Store response")
    if not detail.get("release_date"):
        missing.append("release date")
    if all(modes[key] is None for key in ("singleplayer", "multiplayer", "co_op")):
        missing.append("player mode metadata")
    if modes["controller_support"] is None:
        missing.append("controller support metadata")
    if modes["keyboard_mouse_support"] is None:
        missing.append("keyboard/mouse metadata")
    if early_access is None:
        missing.append("explicit Early Access flag")
    return missing


def _potential_mismatches(profile: list[dict[str, Any]], evidence: dict[str, Any], modes: dict[str, Any], early_access: bool | None, item) -> list[str]:
    mismatches: list[str] = []
    if profile and not evidence["matched_preferences"]:
        if evidence["all_matches"]:
            mismatches.append("Only broad genre/category overlap was found; no concrete tag or feature overlap.")
        else:
            mismatches.append("No concrete overlap with the available high-playtime or recent-game metadata was found.")
    if early_access is True:
        mismatches.append("The item is marked Early Access; stability and feature completeness may differ from released games.")
    if modes["singleplayer"] is True and "co-op" in evidence["user_modes"]:
        mismatches.append("The item is marked single-player while the observed user profile includes co-op activity.")
    if modes["multiplayer"] is False and "multiplayer" in evidence["user_modes"]:
        mismatches.append("The item is not marked multiplayer while the observed user profile includes multiplayer activity.")
    if not mismatches and not item.price:
        mismatches.append("Price is unavailable, so budget fit cannot be assessed.")
    return unique(mismatches)


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


def _add_candidate(target: dict[int, dict[str, Any]], raw: dict[str, Any], source: str) -> None:
    appid = _appid(raw)
    if appid > 0:
        if appid not in target:
            target[appid] = {**raw, "_candidate_sources": [source]}
        else:
            sources = target[appid].setdefault("_candidate_sources", [])
            if source not in sources:
                sources.append(source)


def _appid(raw: dict[str, Any]) -> int:
    try:
        return int(raw.get("appid", raw.get("id", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _bounded(value: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return minimum


def _validate_discount(value: int) -> None:
    if not 0 <= value <= 100:
        raise AppError("INVALID_ARGUMENT", "min_discount must be between 0 and 100.")
