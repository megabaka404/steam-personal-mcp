from __future__ import annotations

from typing import Any, Literal

from errors import AppError
from tools.common import register


def register_compound_tools(mcp, runtime) -> None:
    def player(action: Literal["profile", "currently_playing", "visibility"] = "profile") -> dict[str, Any]:
        if action == "profile":
            return runtime.activity.profile()
        if action == "currently_playing":
            return runtime.activity.currently_playing()
        if action == "visibility":
            return runtime.activity.visibility()
        raise AppError("INVALID_ARGUMENT", "Unsupported player action.")

    def library(
        action: Literal["search", "stats", "most_played", "recent", "abandoned", "never_played", "low_playtime", "backlog", "return_to", "game"] = "stats",
        query: str | None = None,
        game: str | None = None,
        appid: int | None = None,
        period: str = "all",
        count: int = 20,
        max_hours: float | None = None,
        min_hours: float = 1,
        inactive_days: int = 180,
    ) -> dict[str, Any]:
        if action == "search":
            if not query:
                raise AppError("INVALID_ARGUMENT", "library search requires query.")
            return runtime.library.search_library(query, count)
        if action == "stats":
            return runtime.library.stats()
        if action == "most_played":
            rows = runtime.library.most_played(period, count)
            return {"period": period, "count": len(rows), "games": rows}
        if action == "recent":
            rows = [game.public_dict() for game in runtime.library.recent_games(count)]
            return {"count": len(rows), "games": rows}
        if action == "abandoned":
            rows = runtime.library.abandoned(min_hours, max_hours if max_hours is not None else 20, inactive_days, count)
            return {"count": len(rows), "games": rows}
        if action == "never_played":
            rows = runtime.library.never_played(count)
            return {"count": len(rows), "games": rows}
        if action == "low_playtime":
            rows = runtime.library.low_playtime(max_hours if max_hours is not None else 2, count)
            return {"count": len(rows), "games": rows}
        if action == "backlog":
            rows = runtime.recommendations.backlog(count, max_hours)
            return {"count": len(rows), "games": rows}
        if action == "return_to":
            rows = runtime.recommendations.return_to(count, min_hours)
            return {"count": len(rows), "games": rows}
        if action == "game":
            record = runtime.library.game_in_library(game=game, appid=appid)
            if record is None:
                return {"owned": False, "query": game if game is not None else appid}
            return {
                "owned": True,
                **record.public_dict(),
                "achievement_summary": runtime.achievements.summary(appid=record.appid),
            }
        raise AppError("INVALID_ARGUMENT", "Unsupported library action.")

    def achievements(
        action: Literal["details", "summary", "recent", "almost_completed", "completion_candidates"] = "summary",
        game: str | None = None,
        appid: int | None = None,
        include_locked: bool = True,
        days: int = 30,
        count: int = 20,
        min_completion: float = 70,
        max_completion: float = 99.99,
    ) -> dict[str, Any]:
        if action == "details":
            return runtime.achievements.get_achievements(game=game, appid=appid, include_locked=include_locked)
        if action == "summary":
            return runtime.achievements.summary(game=game, appid=appid)
        if action == "recent":
            return runtime.achievements.recent_achievements(days, count)
        if action == "almost_completed":
            rows = runtime.achievements.almost_completed(min_completion, max_completion, count)
            return {"count": len(rows), "games": rows}
        if action == "completion_candidates":
            rows = runtime.achievements.completion_candidates(count)
            return {"count": len(rows), "games": rows}
        raise AppError("INVALID_ARGUMENT", "Unsupported achievements action.")

    def friends(
        action: Literal["list", "playing", "activity", "shared"] = "list",
        limit: int = 100,
        friend_steam_id: str | None = None,
        count: int = 100,
    ) -> dict[str, Any]:
        if action == "list":
            return runtime.friends.friends(limit)
        if action == "playing":
            return runtime.friends.playing(limit)
        if action == "activity":
            return runtime.friends.activity_summary(limit)
        if action == "shared":
            if not friend_steam_id:
                raise AppError("INVALID_ARGUMENT", "friends shared requires friend_steam_id.")
            return runtime.friends.shared_games(friend_steam_id, count)
        raise AppError("INVALID_ARGUMENT", "Unsupported friends action.")

    def store(
        action: Literal["search", "details", "compare", "dlc"] = "search",
        query: str | None = None,
        game: str | None = None,
        appid: int | None = None,
        games: list[str | int] | None = None,
        count: int = 20,
        only_discounted: bool = False,
    ) -> dict[str, Any]:
        if action == "search":
            if not query:
                raise AppError("INVALID_ARGUMENT", "store search requires query.")
            return runtime.store.search_store(query, count)
        if action == "details":
            return runtime.store.get_game(game=game, appid=appid)
        if action == "compare":
            if not games:
                raise AppError("INVALID_ARGUMENT", "store compare requires games.")
            rows = runtime.store.compare(games)
            return {"count": len(rows), "games": rows}
        if action == "dlc":
            return runtime.store.dlc(game=game, appid=appid, only_discounted=only_discounted)
        raise AppError("INVALID_ARGUMENT", "Unsupported store action.")

    def deals(
        action: Literal["specials", "deep_discounts", "search_sales", "summary"] = "specials",
        query: str | None = None,
        count: int = 30,
        min_discount: int = 0,
        max_price: float | None = None,
        min_price: float | None = None,
        genres: list[str] | None = None,
        sort_by: str = "discount",
        exclude_owned: bool = False,
    ) -> dict[str, Any]:
        if action == "specials":
            rows = runtime.store.specials(count=count, min_discount=min_discount, max_price=max_price, min_price=min_price, sort_by=sort_by, exclude_owned=exclude_owned)
            return {"count": len(rows), "games": rows}
        if action == "deep_discounts":
            rows = runtime.store.deep_discounts(min_discount, count, exclude_owned)
            return {"count": len(rows), "games": rows}
        if action == "search_sales":
            rows = runtime.store.search_sales(query=query, min_discount=min_discount, max_price=max_price, genres=genres, count=count, exclude_owned=exclude_owned)
            return {"count": len(rows), "games": rows}
        if action == "summary":
            specials = runtime.store.specials(count=20, min_discount=0, exclude_owned=exclude_owned)
            deep = runtime.store.deep_discounts(min_discount=70, count=20, exclude_owned=exclude_owned)
            wishlist = runtime.store.wishlist_sales(min_discount=min_discount, max_price=max_price, limit=20)
            return {"specials": specials, "deep_discounts": deep, "wishlist_sales": wishlist}
        raise AppError("INVALID_ARGUMENT", "Unsupported deals action.")

    def wishlist(
        action: Literal["list", "sales", "best_deals", "price_history", "price_drops", "release_watch", "buy_advice", "purchase_candidates"] = "list",
        game: str | None = None,
        appid: int | None = None,
        count: int = 20,
        min_discount: int = 0,
        max_price: float | None = None,
        sort_by: str = "discount",
        limit: int = 100,
    ) -> dict[str, Any]:
        if action == "list":
            return runtime.store.wishlist(limit=limit)
        if action == "sales":
            return runtime.store.wishlist_sales(min_discount=min_discount, max_price=max_price, sort_by=sort_by, limit=limit)
        if action == "best_deals":
            return runtime.store.wishlist_best_deals(limit)
        if action == "price_history":
            return runtime.price_history_service.wishlist_history(appid=appid, limit=limit)
        if action == "price_drops":
            return runtime.price_history_service.wishlist_price_drops()
        if action == "release_watch":
            return runtime.p1.wishlist_release_watch()
        if action == "buy_advice":
            return runtime.game_intel.buy_advice(game=game, appid=appid)
        if action == "purchase_candidates":
            return runtime.game_intel.purchase_candidates(count=count)
        raise AppError("INVALID_ARGUMENT", "Unsupported wishlist action.")

    def recommendations(
        action: Literal["store", "similar", "new_releases", "library", "backlog", "return_to", "next", "overlap", "pick"] = "store",
        game: str | None = None,
        appid: int | None = None,
        count: int = 15,
        max_price: float | None = None,
        max_hours: float | None = None,
        min_discount: int = 0,
        include_wishlist: bool = True,
        exclude_owned: bool = True,
        exclude_early_access: bool = False,
        mode: str = "balanced",
        days: int = 365,
    ) -> dict[str, Any]:
        if action == "store":
            return runtime.store_recommendations.recommend_store_for_me(count=count, max_price=max_price, min_discount=min_discount, include_wishlist=include_wishlist, exclude_early_access=exclude_early_access)
        if action == "similar":
            return runtime.store_recommendations.find_similar_games(game=game, appid=appid, count=count, exclude_owned=exclude_owned, max_price=max_price)
        if action == "new_releases":
            rows = runtime.p1.new_releases_for_me(days=days, count=count, exclude_owned=exclude_owned)
            return rows
        if action == "library":
            rows = runtime.recommendations.recommend(count, mode)
            return {"mode": mode, "count": len(rows), "games": rows}
        if action == "backlog":
            rows = runtime.recommendations.backlog(count, max_hours)
            return {"count": len(rows), "games": rows}
        if action == "return_to":
            rows = runtime.recommendations.return_to(count)
            return {"count": len(rows), "games": rows}
        if action == "next":
            rows = runtime.recommendations.what_should_play_next(count)
            return {"count": len(rows), "games": rows}
        if action == "overlap":
            return runtime.game_intel.library_overlap(game=game, appid=appid)
        if action == "pick":
            rows = runtime.recommendations.pick(count=count, randomize=False)
            return {"count": len(rows), "games": rows}
        raise AppError("INVALID_ARGUMENT", "Unsupported recommendations action.")

    def activity(
        action: Literal["record", "sessions", "recent_sessions", "year_review", "game_change_history"] = "sessions",
        game: str | None = None,
        appid: int | None = None,
        days: int = 365,
        count: int = 100,
        year: int | None = None,
    ) -> dict[str, Any]:
        if action == "record":
            return runtime.activity.record_play_session_snapshot()
        if action == "sessions":
            return runtime.p2.play_session_history(days=days, count=count)
        if action == "recent_sessions":
            return runtime.p2.recent_play_sessions(days=days, count=count)
        if action == "year_review":
            return runtime.p2.year_in_review(year=year)
        if action == "game_change_history":
            return runtime.game_intel.update_impact(game=game, appid=appid)
        raise AppError("INVALID_ARGUMENT", "Unsupported activity action.")

    def game_intel(
        action: Literal["snapshot", "update_impact"] = "snapshot",
        game: str | None = None,
        appid: int | None = None,
        include_local: bool = True,
    ) -> dict[str, Any]:
        if action == "snapshot":
            return runtime.game_intel.snapshot(game=game, appid=appid, include_local=include_local)
        if action == "update_impact":
            return runtime.game_intel.update_impact(game=game, appid=appid)
        raise AppError("INVALID_ARGUMENT", "Unsupported game_intel action.")

    def local_steam(
        action: Literal["scan", "installed", "disk_usage"] = "scan",
        appid: int | None = None,
        include_actual_size: bool = False,
    ) -> dict[str, Any]:
        if action == "scan":
            return runtime.local_steam.scan(include_actual_size=include_actual_size)
        if action in {"installed", "disk_usage"}:
            if appid is not None:
                return runtime.local_steam.game_info(appid, include_actual_size=include_actual_size)
            return runtime.local_steam.scan(include_actual_size=include_actual_size)
        raise AppError("INVALID_ARGUMENT", "Unsupported local_steam action.")

    def storage_cleanup(
        action: Literal["scan", "preview", "clean"] = "scan",
        appids: list[int] | None = None,
        targets: list[str] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if action == "scan":
            return runtime.local_steam.storage_scan()
        if action == "preview":
            return runtime.local_steam.storage_preview(appids=appids, targets=targets)
        if action == "clean":
            return runtime.local_steam.storage_clean(appids=appids, targets=targets, confirm=confirm)
        raise AppError("INVALID_ARGUMENT", "Unsupported storage_cleanup action.")

    register(mcp, "player", "Composite player tool. Actions: profile, currently_playing, visibility.", player)
    register(mcp, "library", "Composite library tool. Actions: search, stats, most_played, recent, abandoned, never_played, low_playtime, backlog, return_to, game.", library)
    register(mcp, "achievements", "Composite achievements tool. Actions: details, summary, recent, almost_completed, completion_candidates.", achievements)
    register(mcp, "friends", "Composite friends tool. Actions: list, playing, activity, shared.", friends)
    register(mcp, "store", "Composite Store tool. Actions: search, details, compare, dlc.", store)
    register(mcp, "deals", "Composite deals tool. Actions: specials, deep_discounts, search_sales, summary.", deals)
    register(mcp, "wishlist", "Composite wishlist tool. Actions: list, sales, best_deals, price_history, price_drops, release_watch, buy_advice, purchase_candidates.", wishlist)
    register(mcp, "recommendations", "Composite recommendations tool. Actions: store, similar, new_releases, library, backlog, return_to, next, overlap, pick.", recommendations)
    register(mcp, "activity", "Composite activity tool. Actions: record, sessions, recent_sessions, year_review, game_change_history.", activity)
    register(mcp, "game_intel", "Composite game intelligence tool. Actions: snapshot, update_impact.", game_intel)
    register(mcp, "local_steam", "Composite local Steam tool for Windows library, installed games, and disk usage.", local_steam)
    register(mcp, "storage_cleanup", "Explicitly guarded local residual scan, preview, and clean actions. Scan never deletes.", storage_cleanup)
