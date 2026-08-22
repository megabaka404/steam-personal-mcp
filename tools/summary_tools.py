from __future__ import annotations

from typing import Any

from tools.common import register


def register_summary_tools(mcp, runtime) -> None:
    def steam_activity_summary(include_store: bool = True) -> dict[str, Any]:
        return runtime.activity.activity_summary(include_store)

    def steam_deals_summary(exclude_owned: bool = True) -> dict[str, Any]:
        return runtime.activity.deals_summary(exclude_owned)

    register(mcp, "steam_activity_summary", "Return a bounded one-call summary of profile, current game, recent games, playtime, library stats, recent achievements, near-completion games, and optional wishlist sales.", steam_activity_summary)
    register(mcp, "steam_deals_summary", "Return a bounded deterministic overview of current specials, wishlist deals, deep discounts, and owned-game exclusions.", steam_deals_summary)
