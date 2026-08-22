from __future__ import annotations

from typing import Any

from tools.common import register


def register_recommendation_tools(mcp, runtime) -> None:
    def pick_a_game_for_me(count: int = 1, never_played_only: bool = False, max_playtime_hours: float | None = None, min_playtime_hours: float | None = None, inactive_days: int | None = None, exclude_appids: list[int] | None = None, randomize: bool = True) -> dict[str, Any]:
        rows = runtime.recommendations.pick(count=count, never_played_only=never_played_only, max_playtime_hours=max_playtime_hours, min_playtime_hours=min_playtime_hours, inactive_days=inactive_days, exclude_appids=exclude_appids, randomize=randomize)
        return {"count": len(rows), "games": rows}

    def recommend_from_library(count: int = 5, mode: str = "balanced") -> dict[str, Any]:
        rows = runtime.recommendations.recommend(count, mode)
        return {"mode": mode, "count": len(rows), "games": rows}

    def find_backlog_candidates(count: int = 20, max_hours: float | None = None) -> dict[str, Any]:
        rows = runtime.recommendations.backlog(count, max_hours)
        return {"count": len(rows), "games": rows}

    def find_games_to_return_to(count: int = 20, min_hours: float = 1) -> dict[str, Any]:
        rows = runtime.recommendations.return_to(count, min_hours)
        return {"count": len(rows), "games": rows}

    def compare_my_games(games: list[str | int]) -> dict[str, Any]:
        rows = runtime.recommendations.compare_my_games(games)
        return {"count": len(rows), "games": rows}

    def what_should_i_play_next(count: int = 5) -> dict[str, Any]:
        rows = runtime.recommendations.what_should_play_next(count)
        return {"count": len(rows), "games": rows}

    register(mcp, "pick_a_game_for_me", "Pick owned games using explicit playtime, inactivity, exclusion, and randomized filters; no LLM is called.", pick_a_game_for_me)
    register(mcp, "recommend_from_library", "Rank owned games with an explainable deterministic scoring system. Parameters: count, mode.", recommend_from_library)
    register(mcp, "find_backlog_candidates", "Find owned games never or barely played, excluding obvious software and soundtrack entries.", find_backlog_candidates)
    register(mcp, "find_games_to_return_to", "Find games with meaningful prior playtime and long inactivity. Parameters: count, min_hours.", find_games_to_return_to)
    register(mcp, "compare_my_games", "Compare up to ten owned or unowned game queries using personal playtime and achievement data.", compare_my_games)
    register(mcp, "what_should_i_play_next", "Return three to ten deterministic next-play candidates combining playtime, recency, inactivity, backlog, and achievements.", what_should_i_play_next)
