from __future__ import annotations

from typing import Any

from tools.common import register


def register_achievement_tools(mcp, runtime) -> None:
    def get_achievements(game: str | None = None, appid: int | None = None, include_locked: bool = True) -> dict[str, Any]:
        return runtime.achievements.get_achievements(game=game, appid=appid, include_locked=include_locked)

    def get_achievement_summary(game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        return runtime.achievements.summary(game=game, appid=appid)

    def get_recent_achievements(days: int = 30, count: int = 30) -> dict[str, Any]:
        return runtime.achievements.recent_achievements(days, count)

    def get_almost_completed_games(min_completion: float = 70, max_completion: float = 99.99, count: int = 20) -> dict[str, Any]:
        rows = runtime.achievements.almost_completed(min_completion, max_completion, count)
        return {"count": len(rows), "games": rows}

    def get_completion_candidates(count: int = 20) -> dict[str, Any]:
        rows = runtime.achievements.completion_candidates(count)
        return {"count": len(rows), "games": rows}

    register(mcp, "get_achievements", "Get per-game achievements with display names, descriptions, locked state, and UTC unlock timestamps; supports game or appid.", get_achievements)
    register(mcp, "get_achievement_summary", "Return only compact achievement completion data for a game or AppID.", get_achievement_summary)
    register(mcp, "get_recent_achievements", "Aggregate recent unlocks from a bounded set of recently played games. Parameters: days, count.", get_recent_achievements)
    register(mcp, "get_almost_completed_games", "Find games within a completion percentage range, scanning a bounded set of played games.", get_almost_completed_games)
    register(mcp, "get_completion_candidates", "Rank deterministic achievement-completion candidates by completion, remaining achievements, and playtime.", get_completion_candidates)
