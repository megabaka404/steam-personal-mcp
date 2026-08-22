from __future__ import annotations

import time
from typing import Any

from errors import AppError
from models.account import unix_time_info
from services.recommendation_features import compare_features, extract_features, feature_overlaps


class GameIntelService:
    """Build one explainable game snapshot and reuse it for higher-level analysis."""

    def __init__(self, *, store_client, store_service, steam, library, resolver, achievements, price_history, game_history, local_steam) -> None:
        self.store_client = store_client
        self.store_service = store_service
        self.steam = steam
        self.library = library
        self.resolver = resolver
        self.achievements = achievements
        self.price_history = price_history
        self.game_history = game_history
        self.local_steam = local_steam

    def snapshot(self, *, game: str | None = None, appid: int | None = None, include_local: bool = True) -> dict[str, Any]:
        resolved = self.resolver.resolve(game=game, appid=appid)
        detail = self.store_client.details(resolved.appid)
        if not detail:
            raise AppError("STORE_UNAVAILABLE", "Steam Store details are not available for this AppID.", {"appid": resolved.appid})
        item = self.store_service._from_details(detail, resolved.appid)
        owned_record, ownership = self._ownership(resolved.appid)
        wishlist = self._wishlist(resolved.appid)
        achievements = self._achievements(resolved.appid)
        review = self._review(resolved.appid)
        price = item.price.public_dict() if item.price else None
        if self.price_history is not None and price:
            self.price_history.observe(appid=resolved.appid, name=item.name, price=price)
        price_history = self.price_history.summary(appid=resolved.appid, limit=500) if self.price_history else []
        deck = _deck_info(detail)
        workshop = _workshop_info(detail)
        local = self.local_steam.game_info(resolved.appid) if include_local and self.local_steam else {
            "available": False,
            "reason": "Local Steam service is not configured.",
        }
        dlc = self._dlc(detail, ownership.get("owned_appids") if ownership.get("available") else None)
        current_players = self._current_players(resolved.appid)
        build = _build_info(detail)
        history_payload = {
            "current_players": current_players,
            "overall_review_pct": review.get("overall_reviews", {}).get("positive_pct"),
            "recent_review_pct": review.get("recent_reviews", {}).get("positive_pct"),
            "review_count": review.get("overall_reviews", {}).get("review_count"),
            "recent_review_count": review.get("recent_reviews", {}).get("review_count"),
            "price": price,
            "deck_status": deck.get("status"),
            "build_identifier": build.get("identifier"),
        }
        observation = self.game_history.observe(
            appid=resolved.appid,
            name=item.name,
            snapshot=history_payload,
        ) if self.game_history else None
        observed_trend = _review_trend(self.game_history.records(resolved.appid) if self.game_history else [], now=int(time.time()), current=history_payload)
        result = {
            "available": True,
            "appid": resolved.appid,
            "name": item.name,
            "ownership": {
                key: value for key, value in ownership.items() if key != "owned_appids"
            },
            "playtime": {
                "total_minutes": owned_record.playtime_forever if owned_record else 0,
                "total_hours": owned_record.total_hours if owned_record else 0,
                "recent_two_week_minutes": owned_record.playtime_2weeks if owned_record else 0,
                "recent_two_week_hours": owned_record.recent_hours if owned_record else 0,
                "last_played": owned_record.public_dict().get("last_played") if owned_record else None,
                "available": ownership.get("available", True),
            },
            "achievements": achievements,
            "achievement_completion": achievements if achievements.get("available") else None,
            "wishlist": wishlist,
            "price": price,
            "original_price": price.get("original_price") if price else None,
            "discount": price.get("discount_percent", 0) if price else None,
            "observed_price_history": price_history[0] if price_history else {
                "available": False,
                "reason": "No price observation has been recorded by this MCP.",
                "source": "MCP-observed history",
            },
            "deck_compatibility": deck,
            "deck_details": deck.get("details"),
            "workshop_support": workshop,
            "current_players": current_players,
            "popularity_metrics": {
                "current_players": current_players,
                "review_count": review.get("overall_reviews", {}).get("review_count"),
                "recent_review_volume": review.get("recent_reviews", {}).get("review_count"),
                "source": review.get("source"),
            },
            "overall_reviews": review.get("overall_reviews"),
            "recent_reviews": review.get("recent_reviews"),
            "review_count": review.get("overall_reviews", {}).get("review_count"),
            "recent_review_count": review.get("recent_reviews", {}).get("review_count"),
            "review_trend": observed_trend,
            "release_date": detail.get("release_date"),
            "build_information": build,
            "installed": local.get("installed") if isinstance(local, dict) else None,
            "install_path": local.get("install_path") if isinstance(local, dict) else None,
            "disk_usage": {
                "size_on_disk": local.get("size_on_disk") if isinstance(local, dict) else None,
                "actual_directory_size": local.get("actual_directory_size") if isinstance(local, dict) else None,
                "shadercache_usage": local.get("shadercache_size") if isinstance(local, dict) else None,
                "compatdata_usage": local.get("compatdata_size") if isinstance(local, dict) else None,
                "compatdata_status": local.get("compatdata_status") if isinstance(local, dict) else "unavailable",
                "source": "local Steam files" if isinstance(local, dict) and local.get("available") else None,
            },
            "dlc": dlc,
            "observation": observation,
            "sources": {
                "store": "Steam public Store appdetails",
                "reviews": review.get("source"),
                "personal": "Steam Web API when profile/game details are public",
                "history": "MCP-observed history",
                "local": "local Steam files" if isinstance(local, dict) and local.get("available") else local.get("reason") if isinstance(local, dict) else None,
            },
            "missing_data": _missing_data(detail, review, deck, workshop, local),
        }
        return result

    def library_overlap(self, *, game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        resolved = self.resolver.resolve(game=game, appid=appid)
        detail = self.store_client.details(resolved.appid)
        if not detail:
            raise AppError("STORE_UNAVAILABLE", "Store metadata is unavailable for the target game.")
        target_features = extract_features(detail)
        try:
            owned_games = self.library.owned_games()
        except AppError as exc:
            return {
                "available": False,
                "reason": exc.message,
                "appid": resolved.appid,
                "game_name": detail.get("name") or resolved.name,
                "closest_owned_games": [],
            }
        rows = []
        for owned in owned_games:
            if owned.appid == resolved.appid:
                continue
            owned_detail = self.store_client.details(owned.appid)
            if not owned_detail:
                continue
            score, reasons = compare_features(extract_features(owned_detail), target_features)
            overlaps = feature_overlaps(extract_features(owned_detail), target_features)
            if score <= 0:
                continue
            rows.append({
                "appid": owned.appid,
                "name": owned.name,
                "playtime_hours": owned.total_hours,
                "recent_two_week_hours": owned.recent_hours,
                "similarity_score": round(score, 2),
                "similarity_reasons": reasons,
                "feature_overlaps": overlaps,
            })
        rows.sort(key=lambda item: (-item["similarity_score"], -item["playtime_hours"], item["name"].casefold(), item["appid"]))
        high = [row for row in rows if row["similarity_score"] >= 40]
        barely = [row for row in high if row["playtime_hours"] < 2]
        top_score = rows[0]["similarity_score"] if rows else 0
        level = "high" if top_score >= 60 or len(high) >= 4 else "medium" if top_score >= 30 or high else "low"
        analysis = []
        if high:
            analysis.append(f"User already owns {len(high)} games with substantial feature overlap.")
        if barely:
            analysis.append(f"{len(barely)} similar owned games have very low observed playtime.")
        if not rows:
            analysis.append("No owned game with usable Store feature overlap was found.")
        return {
            "available": True,
            "appid": resolved.appid,
            "game_name": detail.get("name") or resolved.name,
            "overlap_level": level,
            "closest_owned_games": rows[:10],
            "owned_similar_count": len(high),
            "barely_played_similar_count": len(barely),
            "analysis": analysis,
            "source": "Owned library playtime plus public Store genres, categories, tags, and feature aliases.",
            "interpretation": "Similarity is evidence of library overlap, not a final recommendation or purchase verdict.",
        }

    def update_impact(self, *, game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        current = self.snapshot(game=game, appid=appid, include_local=False)
        history = self.game_history.changes(current["appid"]) if self.game_history else {"available": False, "records": []}
        records = history.get("records", [])
        if len(records) < 2:
            return {
                "available": False,
                "reason": "At least two MCP observations are required before change analysis.",
                "appid": current["appid"],
                "game_name": current["name"],
                "current_snapshot": current,
                "source": "MCP-observed history",
            }
        changes = history.get("changes") or {}
        build_changed = "build_identifier" in changes
        effects = []
        for field in ("current_players", "overall_review_pct", "recent_review_pct", "review_count", "recent_review_count", "price_minor", "deck_status"):
            if field in changes:
                effects.append({
                    "metric": field,
                    "change": changes[field],
                    "relation_to_build_change": "observed_nearby" if build_changed else "no_build_change_observed",
                })
        return {
            "available": True,
            "appid": current["appid"],
            "game_name": current["name"],
            "build_change_observed": build_changed,
            "changes": effects,
            "observed_correlation": effects if build_changed else [],
            "confirmed_update_effect": False,
            "confirmed_update_effect_reason": "MCP observations cannot establish causality between a build/update and a later metric change.",
            "history": records,
            "source": "MCP-observed history",
        }

    def buy_advice(self, *, game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        snapshot = self.snapshot(game=game, appid=appid, include_local=False)
        positive: list[str] = []
        negative: list[str] = []
        uncertainties: list[str] = []
        if snapshot["ownership"].get("owned"):
            return {
                "available": True,
                "appid": snapshot["appid"],
                "game_name": snapshot["name"],
                "verdict": "skip",
                "confidence": "high",
                "positive_factors": [],
                "negative_factors": ["The game is already owned."],
                "uncertainties": [],
                "evidence": snapshot,
            }
        price = snapshot.get("price") or {}
        discount = int(price.get("discount_percent") or 0)
        history = snapshot.get("observed_price_history") or {}
        current_minor = price.get("price_minor")
        low_minor = history.get("historical_low_minor")
        if discount > 0:
            positive.append(f"Current discount is {discount}%.")
        else:
            negative.append("The game is not currently discounted.")
        if current_minor is not None and low_minor is not None:
            if current_minor <= low_minor:
                positive.append("Current price matches the lowest price observed by this MCP.")
            else:
                negative.append("Current price is above the lowest price observed by this MCP.")
        else:
            uncertainties.append("There is not enough MCP price history to compare the current price with an observed low.")
        trend = snapshot.get("review_trend") or {}
        if trend.get("trend") in {"rising", "sudden_recovery"}:
            positive.append("Recent review observations are improving.")
        elif trend.get("trend") in {"falling", "sudden_drop"}:
            negative.append("Recent review observations are deteriorating.")
        elif trend.get("status") == "insufficient_history":
            uncertainties.append("Review trend history is insufficient.")
        overlap = self.library_overlap(appid=snapshot["appid"])
        if overlap.get("owned_similar_count", 0):
            negative.append(f"The library already contains {overlap['owned_similar_count']} substantially similar games.")
        if any(row.get("playtime_hours", 0) >= 20 for row in overlap.get("closest_owned_games", [])):
            positive.append("At least one similar owned game has substantial observed playtime.")
        if snapshot.get("deck_compatibility", {}).get("status") == "unknown":
            uncertainties.append("Steam Deck compatibility is unknown.")
        if snapshot.get("wishlist", {}).get("wishlisted"):
            added = snapshot["wishlist"].get("added_at", {}).get("timestamp")
            if added:
                uncertainties.append(f"The wishlist age is {max(0, int((time.time() - added) / 86400))} days; intent is not inferred from age alone.")
        if not price:
            uncertainties.append("Price data is unavailable.")
        if negative and not positive:
            verdict = "wait"
        elif positive and not negative:
            verdict = "buy"
        else:
            verdict = "wait"
        evidence_count = len(positive) + len(negative)
        confidence = "high" if evidence_count >= 4 and not uncertainties else "medium" if evidence_count >= 2 else "low"
        return {
            "available": True,
            "appid": snapshot["appid"],
            "game_name": snapshot["name"],
            "verdict": verdict,
            "confidence": confidence,
            "positive_factors": positive,
            "negative_factors": negative,
            "uncertainties": uncertainties,
            "evidence": {
                "snapshot": snapshot,
                "library_overlap": overlap,
            },
            "interpretation": "This is an explainable evidence summary, not an opaque purchase score or an instruction to buy.",
        }

    def purchase_candidates(self, *, count: int = 10) -> dict[str, Any]:
        count = max(1, min(50, int(count)))
        try:
            wishlist = self.steam.get_wishlist()
        except AppError as exc:
            return {"available": False, "reason": exc.message, "items": []}
        rows = []
        for raw in wishlist[:count]:
            current_appid = _appid(raw)
            if not current_appid:
                continue
            try:
                rows.append(self.buy_advice(appid=current_appid))
            except AppError:
                continue
        rank = {"buy": 0, "wait": 1, "skip": 2}
        rows.sort(key=lambda item: (rank.get(item.get("verdict"), 9), item.get("confidence") != "high", item.get("game_name", "").casefold(), item.get("appid", 0)))
        return {
            "available": True,
            "count": len(rows),
            "items": rows[:count],
            "source": "Wishlist plus current public Store data and MCP-observed history.",
        }

    def _ownership(self, appid: int):
        try:
            record = self.library.game_in_library(appid=appid)
            games = self.library.owned_games()
            return record, {"available": True, "owned": record is not None, "owned_appids": {game.appid for game in games}}
        except AppError as exc:
            return None, {"available": False, "owned": None, "reason": exc.message, "owned_appids": set()}

    def _wishlist(self, appid: int) -> dict[str, Any]:
        try:
            rows = self.steam.get_wishlist()
        except AppError as exc:
            return {"available": False, "wishlisted": None, "reason": exc.message, "added_at": None}
        row = next((item for item in rows if _appid(item) == appid), None)
        return {
            "available": True,
            "wishlisted": row is not None,
            "added_at": unix_time_info(row.get("date_added")) if row and row.get("date_added") else None,
            "priority": row.get("priority") if row else None,
        }

    def _achievements(self, appid: int) -> dict[str, Any]:
        try:
            return self.achievements.summary(appid=appid)
        except Exception as exc:
            return {"available": False, "reason": f"Achievement data unavailable: {type(exc).__name__}"}

    def _review(self, appid: int) -> dict[str, Any]:
        try:
            raw = self.store_client.review_summary(appid) or {}
        except Exception:
            raw = {}
        source = "Steam public appreviews summary" if raw else "Steam public appreviews summary unavailable"
        recent_available = bool(raw.get("recent_review_available")) and raw.get("recent_review_count") is not None and raw.get("recent_review_percentage") is not None
        return {
            "overall_reviews": {
                "positive_pct": raw.get("review_percentage"),
                "review_count": raw.get("review_count"),
                "review_score": raw.get("review_score"),
            },
            "recent_reviews": {
                "available": recent_available,
                "positive_pct": raw.get("recent_review_percentage"),
                "review_count": raw.get("recent_review_count"),
                "review_score": raw.get("recent_review_score"),
                "source": raw.get("recent_review_source"),
                "reason": raw.get("recent_review_reason") if not recent_available else None,
            },
            "source": source,
            "recent_source": raw.get("recent_review_source"),
        }

    def _current_players(self, appid: int) -> int | None:
        method = getattr(self.steam, "current_players", None)
        if method is None:
            return None
        try:
            value = method(appid)
            return int(value) if value is not None else None
        except Exception:
            return None

    def _dlc(self, detail: dict[str, Any], owned_appids: set[int] | None) -> dict[str, Any]:
        ids = [_int(value) for value in (detail.get("dlc") or [])]
        ids = [value for value in ids if value]
        if owned_appids is None:
            return {"available": False, "owned_dlc": [], "missing_dlc": ids, "reason": "Owned game data is unavailable."}
        return {
            "available": True,
            "dlc": ids,
            "owned_dlc": [value for value in ids if value in owned_appids],
            "missing_dlc": [value for value in ids if value not in owned_appids],
        }


def _deck_info(detail: dict[str, Any]) -> dict[str, Any]:
    raw = detail.get("steam_deck_compatibility") or detail.get("deck_compatibility")
    if isinstance(raw, dict):
        status = str(raw.get("status") or raw.get("category") or "unknown").casefold()
        status = _normalize_status(status)
        return {"status": status, "verified": status == "verified", "playable": status == "playable", "unsupported": status == "unsupported", "details": raw.get("details") or raw, "source": "Steam Store appdetails compatibility metadata"}
    values = [str(item.get("description") if isinstance(item, dict) else item).casefold() for item in detail.get("categories") or []]
    for status in ("verified", "playable", "unsupported"):
        if any("steam deck" in value and status in value for value in values):
            return {"status": status, "verified": status == "verified", "playable": status == "playable", "unsupported": status == "unsupported", "details": None, "source": "Steam Store categories"}
    return {"status": "unknown", "verified": False, "playable": False, "unsupported": False, "details": None, "source": "Steam Deck compatibility was not present in the public Store response."}


def _workshop_info(detail: dict[str, Any]) -> dict[str, Any]:
    values = [str(item.get("description") if isinstance(item, dict) else item).casefold() for item in detail.get("categories") or []]
    supported = bool(detail.get("workshop_support")) if isinstance(detail.get("workshop_support"), bool) else any("workshop" in value for value in values)
    return {
        "workshop_supported": supported,
        "workshop_activity": detail.get("workshop_activity"),
        "popular_items": detail.get("popular_items"),
        "recent_updates": detail.get("workshop_recent_updates"),
        "source": "Steam Store appdetails categories" if supported else "Workshop support was not exposed by the public Store response.",
    }


def _build_info(detail: dict[str, Any]) -> dict[str, Any]:
    identifier = detail.get("buildid") or detail.get("build_id") or detail.get("last_change_number")
    return {
        "identifier": str(identifier) if identifier is not None else None,
        "buildid": detail.get("buildid") or detail.get("build_id"),
        "last_change_number": detail.get("last_change_number"),
        "source": "Steam Store appdetails when exposed" if identifier is not None else None,
    }


def _missing_data(detail: dict[str, Any], review: dict[str, Any], deck: dict[str, Any], workshop: dict[str, Any], local: dict[str, Any]) -> list[str]:
    missing = []
    if not detail.get("price_overview"):
        missing.append("price")
    if review.get("overall_reviews", {}).get("review_count") is None:
        missing.append("overall review summary")
    if review.get("recent_reviews", {}).get("review_count") is None:
        reason = review.get("recent_reviews", {}).get("reason")
        missing.append(f"recent review summary unavailable: {reason}" if reason else "recent review summary")
    if deck.get("status") == "unknown":
        missing.append("Steam Deck compatibility")
    if not workshop.get("workshop_supported"):
        missing.append("Workshop support flag")
    if not local.get("available"):
        missing.append("local Steam installation data")
    return missing


def _review_trend(records: list[dict[str, Any]], *, now: int, current: dict[str, Any]) -> dict[str, Any]:
    periods = {}
    for days in (7, 30, 90):
        cutoff = now - days * 86400
        relevant = [row for row in records if (row.get("observed_at") or {}).get("timestamp", 0) >= cutoff]
        if len(relevant) < 2:
            periods[f"{days}d"] = {"status": "insufficient_history", "observations": len(relevant), "reviews": None}
            continue
        first, last = relevant[0], relevant[-1]
        first_pct = first.get("recent_review_pct")
        last_pct = last.get("recent_review_pct")
        first_count = first.get("recent_review_count")
        last_count = last.get("recent_review_count")
        periods[f"{days}d"] = {
            "status": "available",
            "observations": len(relevant),
            "reviews": max(0, last_count - first_count) if first_count is not None and last_count is not None else None,
            "positive_pct_before": first_pct,
            "positive_pct_now": last_pct,
            "positive_pct_delta": last_pct - first_pct if first_pct is not None and last_pct is not None else None,
        }
    deltas = [value.get("positive_pct_delta") for value in periods.values() if value.get("status") == "available" and value.get("positive_pct_delta") is not None]
    delta = deltas[-1] if deltas else None
    if delta is None:
        label = "insufficient_history"
    elif delta >= 15:
        label = "sudden_recovery"
    elif delta >= 5:
        label = "rising"
    elif delta <= -15:
        label = "sudden_drop"
    elif delta <= -5:
        label = "falling"
    else:
        label = "stable"
    return {
        "status": "available" if deltas else "insufficient_history",
        "trend": label,
        "reviews_7d": periods["7d"].get("reviews"),
        "reviews_30d": periods["30d"].get("reviews"),
        "reviews_90d": periods["90d"].get("reviews"),
        "positive_pct_7d": periods["7d"].get("positive_pct_now"),
        "positive_pct_30d": periods["30d"].get("positive_pct_now"),
        "positive_pct_90d": periods["90d"].get("positive_pct_now"),
        "periods": periods,
        "source": "MCP-observed history",
    }


def _normalize_status(value: str) -> str:
    if "verified" in value:
        return "verified"
    if "playable" in value:
        return "playable"
    if "unsupported" in value:
        return "unsupported"
    return "unknown"


def _appid(raw: dict[str, Any]) -> int:
    return _int(raw.get("appid", raw.get("id", 0)))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
