from __future__ import annotations

from typing import Any

from tools.common import register


def register_p2_tools(mcp, runtime) -> None:
    def record_play_session_snapshot() -> dict[str, Any]:
        return runtime.activity.record_play_session_snapshot()

    def get_play_session_history(days: int = 365, count: int = 100) -> dict[str, Any]:
        return runtime.p2.play_session_history(days=days, count=count)

    def get_recent_play_sessions(days: int = 30, count: int = 20) -> dict[str, Any]:
        return runtime.p2.recent_play_sessions(days=days, count=count)

    def steam_year_in_review(year: int | None = None) -> dict[str, Any]:
        return runtime.p2.year_in_review(year=year)

    register(mcp, "record_play_session_snapshot", "Record one MCP-observed snapshot if Steam currently reports a game in progress.", record_play_session_snapshot)
    register(mcp, "get_play_session_history", "Return inferred play sessions from MCP-observed profile snapshots. Parameters: days, count.", get_play_session_history)
    register(mcp, "get_recent_play_sessions", "Return recent inferred play sessions from MCP-observed snapshots. Parameters: days, count.", get_recent_play_sessions)
    register(mcp, "steam_year_in_review", "Generate an explicitly non-official year review from MCP-observed activity snapshots. Parameter: year.", steam_year_in_review)
