from __future__ import annotations

from typing import Any

from tools.common import register


def register_friend_tools(mcp, runtime) -> None:
    def get_friends(limit: int = 100) -> dict[str, Any]:
        return runtime.friends.friends(limit)

    def get_friends_playing(limit: int = 100) -> dict[str, Any]:
        return runtime.friends.playing(limit)

    def friend_activity_summary(limit: int = 100) -> dict[str, Any]:
        return runtime.friends.activity_summary(limit)

    def get_shared_games_with_friend(friend_steam_id: str, count: int = 100) -> dict[str, Any]:
        return runtime.friends.shared_games(friend_steam_id, count)

    register(mcp, "get_friends", "Read the public friend list and profile summaries when Steam permits it. Parameter: limit.", get_friends)
    register(mcp, "get_friends_playing", "List friends whose public profile currently reports a game. Parameter: limit.", get_friends_playing)
    register(mcp, "friend_activity_summary", "Summarize public friend online/current-game activity and best-effort shared library overlap. Parameter: limit.", friend_activity_summary)
    register(mcp, "get_shared_games_with_friend", "Compare owned games with a friend's public library. Parameters: friend_steam_id, count.", get_shared_games_with_friend)
