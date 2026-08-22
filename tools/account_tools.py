from __future__ import annotations

from typing import Any

from tools.common import register


def register_account_tools(mcp, runtime) -> None:
    def get_profile() -> dict[str, Any]:
        return runtime.activity.profile()

    def get_currently_playing() -> dict[str, Any]:
        return runtime.activity.currently_playing()

    def get_account_visibility() -> dict[str, Any]:
        return runtime.activity.visibility()

    register(mcp, "get_profile", "Get the configured Steam profile summary, avatar, visibility-related profile state, country when public, and current game.", get_profile)
    register(mcp, "get_currently_playing", "Return whether the Steam account is currently playing a game; no-game state is a normal response.", get_currently_playing)
    register(mcp, "get_account_visibility", "Check whether profile, owned games, achievements, and friends are readable through Steam's public APIs.", get_account_visibility)
