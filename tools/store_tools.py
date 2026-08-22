from __future__ import annotations

from typing import Any

from tools.common import register


def register_store_tools(mcp, runtime) -> None:
    def search_store(query: str, count: int = 20) -> dict[str, Any]:
        return runtime.store.search_store(query, count)

    def get_store_game(game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        return runtime.store.get_game(game=game, appid=appid)

    def get_specials(count: int = 50, min_discount: int = 0, max_price: float | None = None, min_price: float | None = None, sort_by: str = "discount", exclude_owned: bool = False) -> dict[str, Any]:
        rows = runtime.store.specials(count=count, min_discount=min_discount, max_price=max_price, min_price=min_price, sort_by=sort_by, exclude_owned=exclude_owned)
        return {"count": len(rows), "games": rows}

    def get_deep_discounts(min_discount: int = 70, count: int = 50, exclude_owned: bool = False) -> dict[str, Any]:
        rows = runtime.store.deep_discounts(min_discount, count, exclude_owned)
        return {"count": len(rows), "games": rows}

    def search_sales(query: str | None = None, min_discount: int = 0, max_price: float | None = None, genres: list[str] | None = None, count: int = 30, exclude_owned: bool = False) -> dict[str, Any]:
        rows = runtime.store.search_sales(query=query, min_discount=min_discount, max_price=max_price, genres=genres, count=count, exclude_owned=exclude_owned)
        return {"count": len(rows), "games": rows}

    def compare_store_games(games: list[str | int]) -> dict[str, Any]:
        rows = runtime.store.compare(games)
        return {"count": len(rows), "games": rows}

    def get_game_dlc(game: str | None = None, appid: int | None = None, only_discounted: bool = False) -> dict[str, Any]:
        return runtime.store.dlc(game=game, appid=appid, only_discounted=only_discounted)

    def get_wishlist(only_discounted: bool = False, limit: int = 100) -> dict[str, Any]:
        return runtime.store.wishlist(only_discounted=only_discounted, limit=limit)

    def get_wishlist_sales(min_discount: int = 0, max_price: float | None = None, sort_by: str = "discount", limit: int = 100) -> dict[str, Any]:
        return runtime.store.wishlist_sales(min_discount=min_discount, max_price=max_price, sort_by=sort_by, limit=limit)

    def get_wishlist_best_deals(limit: int = 20) -> dict[str, Any]:
        return runtime.store.wishlist_best_deals(limit)

    register(mcp, "search_store", "Search Steam's public Store JSON search endpoint. Parameters: query, count.", search_store)
    register(mcp, "get_store_game", "Get Store details, pricing in configured currency, DLC IDs, platforms, metadata, and owned/wishlisted flags for a game or AppID.", get_store_game)
    register(mcp, "get_specials", "List current featured Steam Store specials with discount and price filters. Parameters: count, min_discount, max_price, min_price, sort_by, exclude_owned.", get_specials)
    register(mcp, "get_deep_discounts", "Find featured games at or above a discount threshold. Parameters: min_discount, count, exclude_owned.", get_deep_discounts)
    register(mcp, "search_sales", "Search current Store results or featured specials with discount, price, genre, and owned-exclusion filters.", search_sales)
    register(mcp, "compare_store_games", "Compare up to ten Store games by price, reviews, genres, release data, ownership, and wishlist status.", compare_store_games)
    register(mcp, "get_game_dlc", "List DLC from a Store game's public DLC list, optionally only discounted DLC.", get_game_dlc)
    register(mcp, "get_wishlist", "Read wishlist appIDs through Steam's public wishlist service and enrich them with Store details; returns explicit unsupported/private status when unavailable.", get_wishlist)
    register(mcp, "get_wishlist_sales", "Filter wishlist items currently discounted by minimum discount, price, and sort order.", get_wishlist_sales)
    register(mcp, "get_wishlist_best_deals", "Rank wishlist deals deterministically using discount, price, and review percentage.", get_wishlist_best_deals)
