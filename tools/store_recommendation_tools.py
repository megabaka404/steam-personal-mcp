from __future__ import annotations

from typing import Any

from tools.common import register


def register_store_recommendation_tools(mcp, runtime) -> None:
    def recommend_store_for_me(count: int = 10, max_price: float | None = None, min_discount: int = 0, include_wishlist: bool = True, exclude_early_access: bool = False) -> dict[str, Any]:
        return runtime.store_recommendations.recommend_store_for_me(count=count, max_price=max_price, min_discount=min_discount, include_wishlist=include_wishlist, exclude_early_access=exclude_early_access)

    def find_similar_games(game: str | None = None, appid: int | None = None, count: int = 20, exclude_owned: bool = True, max_price: float | None = None) -> dict[str, Any]:
        return runtime.store_recommendations.find_similar_games(game=game, appid=appid, count=count, exclude_owned=exclude_owned, max_price=max_price)

    def get_wishlist_price_history(appid: int | None = None, limit: int = 100) -> dict[str, Any]:
        return runtime.price_history_service.wishlist_history(appid=appid, limit=limit)

    def get_wishlist_price_drops() -> dict[str, Any]:
        return runtime.price_history_service.wishlist_price_drops()

    register(mcp, "recommend_store_for_me", "Recommend unowned Store games using weighted library playtime, recent activity, genres, categories, wishlist, reviews, and discounts. Parameters: count, max_price, min_discount, include_wishlist, exclude_early_access.", recommend_store_for_me)
    register(mcp, "find_similar_games", "Find games similar to a source game using public Store genres, categories, tags when available, developer, and publisher metadata. Parameters: game, appid, count, exclude_owned, max_price.", find_similar_games)
    register(mcp, "get_wishlist_price_history", "Return price history observed by this MCP for one AppID or the wishlist. This is not Steam's official all-time price history. Parameters: appid, limit.", get_wishlist_price_history)
    register(mcp, "get_wishlist_price_drops", "Report wishlist price drops, local observed lows, and changes since the previous MCP observation.", get_wishlist_price_drops)
