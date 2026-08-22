from __future__ import annotations

import datetime as dt
import math
from typing import Any

from errors import AppError
from models.store import parse_price
from services.recommendation_features import profile_terms, unique


class P1Service:
    """Bounded personal analyses that combine library and public Store data."""

    def __init__(self, store_client, store_service, store_recommendations, library, steam, history, settings) -> None:
        self.store = store_client
        self.store_service = store_service
        self.store_recommendations = store_recommendations
        self.library = library
        self.steam = steam
        self.history = history
        self.settings = settings

    def new_releases_for_me(self, *, days: int = 30, count: int = 20, exclude_owned: bool = True) -> dict[str, Any]:
        if days < 0:
            raise AppError("INVALID_ARGUMENT", "days must be non-negative.")
        count = _bounded(count, 1, 50)
        owned = self.store_recommendations._owned_ids()
        wishlist = self.store_recommendations._wishlist_ids() or set()
        profile = self.store_recommendations._preference_profile(owned)
        terms = profile_terms(profile)
        raw_candidates = self.store_recommendations._candidate_pool(terms, wishlist, include_wishlist=True)
        now = dt.datetime.now(dt.timezone.utc)
        rows = []
        for appid, raw in raw_candidates.items():
            if exclude_owned and appid in owned:
                continue
            item, detail = self.store_recommendations._candidate(appid, raw, owned, wishlist, include_reviews=False)
            if not _is_game_item(item):
                continue
            release = _release_info(detail)
            release_dt = release["date"]
            if release["coming_soon"] or release_dt is None:
                continue
            age_days = (now - release_dt).total_seconds() / 86400
            if age_days < 0 or age_days > days:
                continue
            context = self.store_recommendations._candidate_context(item, detail, profile, wishlist, raw.get("_candidate_sources", []))
            discount = context["discount_percent"]
            recency_bonus = max(0, 10 - age_days / max(1, days) * 10)
            score = min(100, context["candidate_score"] + recency_bonus)
            reasons = list(context["candidate_reasons"])
            reasons.insert(0, f"Released {release['date_text']}")
            row = item.public_dict(compact=True)
            row.update(context)
            row.update({
                "release_date": release["date_text"],
                "release_date_iso": release["date"].date().isoformat(),
                "days_since_release": round(max(0, age_days), 1),
                "candidate_score": round(score, 2),
                "candidate_reasons": unique(reasons),
                "reasons": unique(reasons),
                "score": round(score, 2),
                "score_deprecated": True,
                "score_note": "Deprecated compatibility alias for candidate_score; not final recommendation confidence.",
            })
            rows.append(row)
        rows.sort(key=lambda row: (-row["candidate_score"], row["name"].casefold(), row["appid"]))
        return {
            "days": days,
            "count": min(count, len(rows)),
            "candidate_source": "Steam public Store search, featured specials, and wishlist; not a full catalog scan",
            "interpretation": "Candidates and evidence only. candidate_score ranks retrieval priority and is not a final fit, purchase recommendation, or confidence score.",
            "games": rows[:count],
        }

    def library_value_stats(self) -> dict[str, Any]:
        try:
            games = self.library.owned_games()
        except AppError as exc:
            return {"available": False, "reason": exc.message, "games_scanned": 0}
        total_original_minor = 0
        total_current_minor = 0
        total_playtime = sum(game.total_hours for game in games)
        priced: list[dict[str, Any]] = []
        free_games = 0
        missing_price: list[dict[str, Any]] = []
        currencies: set[str] = set()
        scan_limit = min(100, len(games))
        for game in sorted(games, key=lambda item: item.playtime_forever, reverse=True)[:scan_limit]:
            try:
                detail = self.store.details(game.appid)
            except AppError:
                detail = None
            price = parse_price(detail.get("price_overview")) if detail else None
            if price is None:
                if game.is_free:
                    free_games += 1
                else:
                    missing_price.append({"appid": game.appid, "name": game.name})
                continue
            data = price.public_dict()
            if data.get("currency"):
                currencies.add(str(data["currency"]))
            total_original_minor += int(data.get("original_price_minor") or data.get("price_minor") or 0)
            total_current_minor += int(data.get("price_minor") or 0)
            current = data.get("price")
            value_per_hour = round(game.total_hours / current, 3) if current and current > 0 else None
            priced.append({
                "appid": game.appid,
                "name": game.name,
                "playtime_hours": game.total_hours,
                "price": data,
                "hours_per_dollar": value_per_hour,
                "is_free": bool(game.is_free),
            })
        currency = next(iter(currencies)) if len(currencies) == 1 else None
        total_original = _minor_to_major(total_original_minor, currency)
        total_current = _minor_to_major(total_current_minor, currency)
        value_ranked = [item for item in priced if item["hours_per_dollar"] is not None]
        best = sorted(value_ranked, key=lambda item: (-item["hours_per_dollar"], item["name"].casefold()))[:10]
        worst = sorted(value_ranked, key=lambda item: (item["hours_per_dollar"], item["name"].casefold()))[:10]
        return {
            "available": True,
            "currency": currency,
            "currencies": sorted(currencies),
            "games_scanned": scan_limit,
            "priced_games": len(priced),
            "free_games": free_games,
            "missing_price_games": len(missing_price),
            "missing_price": missing_price[:50],
            "total_original_value": total_original,
            "total_current_value": total_current,
            "total_playtime_hours": round(total_playtime, 2),
            "hours_per_dollar": round(total_playtime / total_current, 3) if total_current and total_current > 0 else None,
            "best_value_games": best,
            "lowest_value_games": worst,
            "estimate_note": "Values use current public Store/MSRP prices, not the user's actual purchase prices, bundles, gifts, or regional payment history.",
        }

    def missing_dlc_for_owned_games(
        self,
        *,
        only_discounted: bool = False,
        min_discount: int = 0,
        count: int = 100,
        exclude_soundtracks: bool = False,
        exclude_cosmetics: bool = False,
    ) -> dict[str, Any]:
        if not 0 <= min_discount <= 100:
            raise AppError("INVALID_ARGUMENT", "min_discount must be between 0 and 100.")
        count = _bounded(count, 1, 200)
        try:
            games = self.library.owned_games()
        except AppError as exc:
            return {"available": False, "reason": exc.message, "count": 0, "dlc": []}
        owned = {game.appid for game in games}
        rows = []
        seen: set[int] = set()
        parents_scanned = 0
        scan_limit = min(30, len(games))
        for game in sorted(games, key=lambda item: item.playtime_forever, reverse=True)[:scan_limit]:
            try:
                base = self.store.details(game.appid)
            except AppError:
                base = None
            if not base or not base.get("dlc"):
                continue
            parents_scanned += 1
            for raw_dlc_id in base.get("dlc") or []:
                try:
                    dlc_id = int(raw_dlc_id)
                except (TypeError, ValueError):
                    continue
                if dlc_id in owned or dlc_id in seen:
                    continue
                try:
                    detail = self.store.details(dlc_id)
                except AppError:
                    detail = None
                if not detail:
                    continue
                item = self.store_service._from_details(detail, dlc_id, include_reviews=False)
                if not _is_game_dlc(item, detail):
                    continue
                if exclude_soundtracks and _contains_kind(item, detail, "soundtrack"):
                    continue
                if exclude_cosmetics and _contains_kind(item, detail, "cosmetic"):
                    continue
                discount = item.price.discount_percent if item.price else 0
                if only_discounted and discount <= 0:
                    continue
                if discount < min_discount:
                    continue
                seen.add(dlc_id)
                row = item.public_dict(compact=True)
                row.update({
                    "parent_appid": game.appid,
                    "parent_name": str(base.get("name") or game.name),
                    "discount_percent": discount,
                    "dlc_type": item.type,
                })
                rows.append(row)
        rows.sort(key=lambda row: (-row["discount_percent"], (row.get("price") or {}).get("price") or 0, row["name"].casefold()))
        return {
            "available": True,
            "games_scanned": scan_limit,
            "parents_with_dlc": parents_scanned,
            "count": min(count, len(rows)),
            "dlc": rows[:count],
            "scan_note": "To avoid Store request storms, owned games are scanned by playtime priority with a maximum of 30 parents per call.",
        }

    def wishlist_release_watch(self) -> dict[str, Any]:
        try:
            raw_wishlist = self.steam.get_wishlist()
        except AppError as exc:
            return {"available": False, "reason": exc.message, "count": 0, "items": []}
        rows = []
        for raw in raw_wishlist[:200]:
            appid = _appid(raw)
            if not appid:
                continue
            try:
                detail = self.store.details(appid)
            except AppError:
                detail = None
            if not detail:
                continue
            release = _release_info(detail)
            previous = self.history.observe_release(
                appid=appid,
                name=str(detail.get("name") or f"App {appid}"),
                release_date=release["date_text"],
                coming_soon=release["coming_soon"],
                status=release["status"],
            )
            transition = None
            if previous:
                if previous.get("coming_soon") and not release["coming_soon"]:
                    transition = "coming_soon_to_released"
                elif previous.get("release_date") != release["date_text"]:
                    transition = "release_date_changed"
            rows.append({
                "appid": appid,
                "name": detail.get("name") or f"App {appid}",
                "coming_soon": release["coming_soon"],
                "release_date": release["date_text"],
                "release_date_iso": release["date"].date().isoformat() if release["date"] else None,
                "status": release["status"],
                "transition": transition,
                "priority": raw.get("priority"),
                "date_added": raw.get("date_added"),
            })
        rows.sort(key=lambda row: (not row["coming_soon"], row["release_date_iso"] or "9999-99-99", row["name"].casefold()))
        return {
            "available": True,
            "total_wishlist": len(raw_wishlist),
            "count": len(rows),
            "items": rows,
            "source": "Steam wishlist plus public Store appdetails; release transitions are MCP-observed.",
        }


def _release_info(detail: dict[str, Any]) -> dict[str, Any]:
    raw = detail.get("release_date") or {}
    coming_soon = bool(raw.get("coming_soon")) if isinstance(raw, dict) else False
    date_text = str(raw.get("date") or "") if isinstance(raw, dict) else str(raw or "")
    parsed = _parse_date(date_text)
    return {"coming_soon": coming_soon, "date_text": date_text or None, "date": parsed, "status": "upcoming" if coming_soon else ("released" if parsed or date_text else "unknown")}


def _parse_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%d %b, %Y", "%d %B, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(value.strip(), pattern).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def _is_game_item(item) -> bool:
    name = (item.name or "").casefold()
    return (item.type or "unknown").casefold() in {"game", "app", "unknown"} and not name.endswith((" soundtrack", " ost"))


def _is_game_dlc(item, detail: dict[str, Any]) -> bool:
    return (item.type or detail.get("type") or "").casefold() in {"dlc", "game", "app", "unknown"}


def _contains_kind(item, detail: dict[str, Any], kind: str) -> bool:
    values = [item.name, detail.get("short_description")]
    values.extend((entry.get("description") if isinstance(entry, dict) else entry) for entry in (detail.get("genres") or []))
    values.extend((entry.get("description") if isinstance(entry, dict) else entry) for entry in (detail.get("categories") or []))
    return kind in " ".join(str(value or "").casefold() for value in values)


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


def _minor_to_major(minor: int, currency: str | None) -> float | None:
    from models.store import minor_to_major
    return minor_to_major(minor, currency)
