from __future__ import annotations

from typing import Any

from tools.common import register


def register_p1_tools(mcp, runtime) -> None:
    def new_releases_for_me(days: int = 30, count: int = 20, exclude_owned: bool = True) -> dict[str, Any]:
        return runtime.p1.new_releases_for_me(days=days, count=count, exclude_owned=exclude_owned)

    def library_value_stats() -> dict[str, Any]:
        return runtime.p1.library_value_stats()

    def missing_dlc_for_owned_games(only_discounted: bool = False, min_discount: int = 0, count: int = 100, exclude_soundtracks: bool = False, exclude_cosmetics: bool = False) -> dict[str, Any]:
        return runtime.p1.missing_dlc_for_owned_games(only_discounted=only_discounted, min_discount=min_discount, count=count, exclude_soundtracks=exclude_soundtracks, exclude_cosmetics=exclude_cosmetics)

    def wishlist_release_watch() -> dict[str, Any]:
        return runtime.p1.wishlist_release_watch()

    register(mcp, "new_releases_for_me", "Retrieve recent public Store release candidates with candidate_score, evidence, and possible mismatches. candidate_score is retrieval priority, not final fit or purchase confidence. Parameters: days, count, exclude_owned.", new_releases_for_me)
    register(mcp, "library_value_stats", "Estimate current/MSRP Store value, playtime value, and priced/free/missing-price coverage for the owned library.", library_value_stats)
    register(mcp, "missing_dlc_for_owned_games", "Find unowned DLC for owned games with current Store price and discount. Parameters: only_discounted, min_discount, count, exclude_soundtracks, exclude_cosmetics.", missing_dlc_for_owned_games)
    register(mcp, "wishlist_release_watch", "Track wishlist release status and MCP-observed coming-soon or release-date transitions using public Store appdetails.", wishlist_release_watch)
