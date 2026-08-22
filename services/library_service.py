from __future__ import annotations

import statistics
import time
from difflib import SequenceMatcher
from typing import Any

from errors import AppError
from models.game import GameRecord, parse_game


class LibraryService:
    def __init__(self, steam, cache, settings) -> None:
        self.steam = steam
        self.cache = cache
        self.settings = settings
        self.resolver = None

    def owned_games(self, include_free_games: bool = True) -> list[GameRecord]:
        raw = self.steam.get_owned_games(include_free_games=include_free_games)
        return [parse_game(item) for item in raw if _valid_appid(item)]

    def recent_games(self, count: int = 10) -> list[GameRecord]:
        count = _bounded(count, 1, 100)
        raw = self.steam.get_recent_games(count)
        last_played_by_appid: dict[int, int | None] = {}
        try:
            last_played_by_appid = {game.appid: game.rtime_last_played for game in self.owned_games()}
        except AppError:
            # Recently played data can still be useful when owned-game details
            # are private or temporarily unavailable.
            pass
        return [parse_game(_with_last_played(item, last_played_by_appid)) for item in raw if _valid_appid(item)]

    def get_library(self, *, include_free_games: bool = True, sort_by: str = "playtime", order: str = "desc", limit: int | None = None, offset: int = 0) -> dict[str, Any]:
        if sort_by not in {"playtime", "name", "last_played"}:
            raise AppError("INVALID_ARGUMENT", "sort_by must be playtime, name, or last_played.")
        if order not in {"asc", "desc"}:
            raise AppError("INVALID_ARGUMENT", "order must be asc or desc.")
        games = self.owned_games(include_free_games)
        reverse = order == "desc"
        if sort_by == "playtime":
            games.sort(key=lambda game: game.playtime_forever)
        elif sort_by == "name":
            games.sort(key=lambda game: game.name.casefold())
        else:
            games.sort(key=lambda game: game.rtime_last_played or 0)
        if reverse:
            games.reverse()
        page_limit = _bounded(limit if limit is not None else 50, 1, 200)
        offset = max(0, offset)
        page = games[offset : offset + page_limit]
        return {
            "total": len(games),
            "offset": offset,
            "limit": page_limit,
            "has_more": offset + len(page) < len(games),
            "games": [game.public_dict() for game in page],
        }

    def search_library(self, query: str, limit: int = 20) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise AppError("INVALID_ARGUMENT", "query must not be empty.")
        games = self.owned_games()
        normalized = query.casefold()
        ranked = []
        for game in games:
            name = game.name.casefold()
            score = 1.0 if normalized in name else SequenceMatcher(None, normalized, name).ratio()
            if score >= 0.35:
                ranked.append((score, game))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].name.casefold()))
        rows = [{**game.public_dict(), "match_score": round(score, 3)} for score, game in ranked[:_bounded(limit, 1, 100)]]
        return {"query": query, "total_matches": len(ranked), "games": rows}

    def game_in_library(self, *, game: str | None = None, appid: int | None = None) -> GameRecord | None:
        games = self.owned_games()
        if appid is not None:
            return next((item for item in games if item.appid == appid), None)
        if game:
            query = game.casefold().strip()
            exact = next((item for item in games if item.name.casefold() == query), None)
            if exact:
                return exact
            matches = [item for item in games if query in item.name.casefold()]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise AppError("AMBIGUOUS_GAME", "More than one library game matches the name.", {"candidates": [{"appid": item.appid, "name": item.name} for item in matches[:10]]})
        return None

    def resolve_library_game(self, *, game: str | None = None, appid: int | None = None) -> GameRecord:
        resolved = self.game_in_library(game=game, appid=appid)
        if resolved is not None:
            return resolved
        raise AppError("GAME_NOT_FOUND", "The requested game is not in the Steam library.")

    def most_played(self, period: str = "all", count: int = 20) -> list[dict[str, Any]]:
        if period not in {"all", "recent"}:
            raise AppError("INVALID_ARGUMENT", "period must be all or recent.")
        games = self.owned_games()
        key = (lambda game: game.playtime_2weeks) if period == "recent" else (lambda game: game.playtime_forever)
        return [game.public_dict() for game in sorted(games, key=key, reverse=True)[:_bounded(count, 1, 100)]]

    def never_played(self, count: int = 50) -> list[dict[str, Any]]:
        games = [game for game in self.owned_games() if game.playtime_forever == 0]
        games.sort(key=lambda game: game.name.casefold())
        return [game.public_dict() for game in games[:_bounded(count, 1, 200)]]

    def low_playtime(self, max_hours: float = 2, count: int = 50) -> list[dict[str, Any]]:
        if max_hours < 0:
            raise AppError("INVALID_ARGUMENT", "max_hours must be non-negative.")
        games = [game for game in self.owned_games() if game.total_hours <= max_hours]
        games.sort(key=lambda game: (game.playtime_forever, game.name.casefold()))
        return [game.public_dict() for game in games[:_bounded(count, 1, 200)]]

    def abandoned(self, min_hours: float = 1, max_hours: float = 20, inactive_days: int = 180, count: int = 30) -> list[dict[str, Any]]:
        if min_hours < 0 or max_hours < min_hours or inactive_days < 0:
            raise AppError("INVALID_ARGUMENT", "Use min_hours <= max_hours and non-negative inactivity values.")
        now = int(time.time())
        threshold = now - inactive_days * 86400
        games = [game for game in self.owned_games() if min_hours <= game.total_hours <= max_hours and game.rtime_last_played and game.rtime_last_played <= threshold]
        games.sort(key=lambda game: (game.rtime_last_played or now, -game.playtime_forever))
        return [game.public_dict() for game in games[:_bounded(count, 1, 200)]]

    def stats(self) -> dict[str, Any]:
        games = self.owned_games()
        minutes = [game.playtime_forever for game in games]
        recent = sum(game.playtime_2weeks for game in games)
        played = [value for value in minutes if value > 0]
        return {
            "total_games": len(games),
            "played_games": len(played),
            "never_started_games": len(games) - len(played),
            "total_playtime_minutes": sum(minutes),
            "total_playtime_hours": round(sum(minutes) / 60, 2),
            "average_playtime_hours": round(statistics.mean(minutes) / 60, 2) if minutes else 0,
            "median_playtime_hours": round(statistics.median(minutes) / 60, 2) if minutes else 0,
            "hours_thresholds": {str(hours): sum(value >= hours * 60 for value in minutes) for hours in (10, 50, 100, 500)},
            "recent_two_week_minutes": recent,
            "recent_two_week_hours": round(recent / 60, 2),
            "top_games": self.most_played("all", 10),
        }

    def playtime_summary(self, top_n: int = 20) -> dict[str, Any]:
        stats = self.stats()
        recent = self.most_played("recent", min(top_n, 20))
        return {
            "library_size": stats["total_games"],
            "played_games": stats["played_games"],
            "never_started_games": stats["never_started_games"],
            "total_hours": stats["total_playtime_hours"],
            "recent_two_week_hours": stats["recent_two_week_hours"],
            "most_played": self.most_played("all", min(top_n, 20)),
            "most_played_recently": recent,
            "habit_notes": _habit_notes(stats, recent),
        }


def _valid_appid(item: dict[str, Any]) -> bool:
    try:
        return int(item.get("appid", item.get("id", 0))) > 0
    except (TypeError, ValueError):
        return False


def _with_last_played(item: dict[str, Any], last_played_by_appid: dict[int, int | None]) -> dict[str, Any]:
    data = dict(item)
    if data.get("rtime_last_played") not in (None, "", 0, "0"):
        return data
    try:
        appid = int(data.get("appid", data.get("id", 0)) or 0)
    except (TypeError, ValueError):
        return data
    timestamp = last_played_by_appid.get(appid)
    if timestamp:
        data["rtime_last_played"] = timestamp
    return data


def _bounded(value: int | None, minimum: int, maximum: int) -> int:
    if value is None:
        return maximum
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return minimum


def _habit_notes(stats: dict[str, Any], recent: list[dict[str, Any]]) -> list[str]:
    notes = []
    if stats["never_started_games"]:
        notes.append(f"{stats['never_started_games']} owned games have never been launched.")
    if recent and recent[0].get("recent_two_week_hours", 0) >= 10:
        notes.append(f"{recent[0]['name']} is your strongest recent focus.")
    if stats["total_playtime_hours"] > 500:
        notes.append("You have a substantial long-term playtime history.")
    return notes
