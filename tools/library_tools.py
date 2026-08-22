from __future__ import annotations

from typing import Any

from tools.common import register


def register_library_tools(mcp, runtime) -> None:
    def get_recent_games(count: int = 10) -> dict[str, Any]:
        games = runtime.library.recent_games(count)
        return {"count": len(games), "games": [game.public_dict() for game in games]}

    def get_library(include_free_games: bool = True, sort_by: str = "playtime", order: str = "desc", limit: int | None = None, offset: int = 0) -> dict[str, Any]:
        return runtime.library.get_library(include_free_games=include_free_games, sort_by=sort_by, order=order, limit=limit, offset=offset)

    def search_library(query: str, limit: int = 20) -> dict[str, Any]:
        return runtime.library.search_library(query, limit)

    def get_game_in_library(game: str | None = None, appid: int | None = None, include_store: bool = False) -> dict[str, Any]:
        record = runtime.library.game_in_library(game=game, appid=appid)
        if record is None and (game is not None or appid is not None):
            resolved = runtime.resolver.resolve(game=game, appid=appid)
            record = runtime.library.game_in_library(appid=resolved.appid)
        if record is None:
            return {"owned": False, "query": game if game is not None else appid}
        result: dict[str, Any] = {"owned": True, **record.public_dict()}
        result["achievement_summary"] = runtime.achievements.summary(appid=record.appid)
        if include_store:
            try:
                result["store_information"] = runtime.store.get_game(appid=record.appid)
            except Exception:
                result["store_information"] = None
        return result

    def get_most_played(period: str = "all", count: int = 20) -> dict[str, Any]:
        return {"period": period, "games": runtime.library.most_played(period, count)}

    def get_never_played(count: int = 50) -> dict[str, Any]:
        rows = runtime.library.never_played(count)
        return {"count": len(rows), "games": rows}

    def get_low_playtime_games(max_hours: float = 2, count: int = 50) -> dict[str, Any]:
        rows = runtime.library.low_playtime(max_hours, count)
        return {"max_hours": max_hours, "count": len(rows), "games": rows}

    def get_abandoned_games(min_hours: float = 1, max_hours: float = 20, inactive_days: int = 180, count: int = 30) -> dict[str, Any]:
        rows = runtime.library.abandoned(min_hours, max_hours, inactive_days, count)
        return {"count": len(rows), "games": rows}

    def get_library_stats() -> dict[str, Any]:
        return runtime.library.stats()

    def get_playtime_summary(top_n: int = 20) -> dict[str, Any]:
        return runtime.library.playtime_summary(top_n)

    register(mcp, "get_recent_games", "List games played recently with total and two-week playtime, icons, and last-played UTC timestamps. Parameter: count.", get_recent_games)
    register(mcp, "get_library", "Return a bounded, sortable, pageable Steam library. Parameters: include_free_games, sort_by, order, limit, offset.", get_library)
    register(mcp, "search_library", "Fuzzy-search games owned by the configured Steam account. Parameters: query, limit.", search_library)
    register(mcp, "get_game_in_library", "Check whether a game or AppID is owned, with playtime, last played, achievement summary, and optional Store details.", get_game_in_library)
    register(mcp, "get_most_played", "Get top games by all-time or recent-two-week playtime. Parameters: period, count.", get_most_played)
    register(mcp, "get_never_played", "Find owned games with exactly zero minutes played. Parameter: count.", get_never_played)
    register(mcp, "get_low_playtime_games", "Find owned games at or below a playtime threshold. Parameters: max_hours, count.", get_low_playtime_games)
    register(mcp, "get_abandoned_games", "Find games played for a bounded amount but not opened for a long time. Parameters: min_hours, max_hours, inactive_days, count.", get_abandoned_games)
    register(mcp, "get_library_stats", "Return compact library-wide playtime statistics and top games without dumping the library.", get_library_stats)
    register(mcp, "get_playtime_summary", "Return a compact LLM-friendly summary of library size, habits, all-time leaders, and recent focus. Parameter: top_n.", get_playtime_summary)
