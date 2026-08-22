from __future__ import annotations

from typing import Any

from errors import AppError
from models.account import Profile


class ActivityService:
    def __init__(self, steam, library, achievements, store, settings, activity_history=None) -> None:
        self.steam = steam
        self.library = library
        self.achievements = achievements
        self.store = store
        self.settings = settings
        self.activity_history = activity_history

    def profile(self) -> dict[str, Any]:
        profile = Profile.model_validate(self.steam.get_profile())
        self._record_profile_activity(profile)
        return profile.public_dict()

    def currently_playing(self) -> dict[str, Any]:
        profile = Profile.model_validate(self.steam.get_profile())
        if not profile.gameid and not profile.gameextrainfo:
            return {"playing": False}
        result = {"playing": True, "appid": profile.gameid, "name": profile.gameextrainfo or f"App {profile.gameid}"}
        self._record_profile_activity(profile)
        return result

    def record_play_session_snapshot(self) -> dict[str, Any]:
        playing = self.currently_playing()
        if not playing.get("playing"):
            return {"recorded": False, "playing": False, "reason": "Steam does not currently report a game in progress."}
        return {"recorded": True, **playing, "source": "MCP-observed Steam profile snapshot"}

    def _record_profile_activity(self, profile: Profile) -> None:
        if self.activity_history is None or not profile.gameid:
            return
        try:
            self.activity_history.record_snapshot(appid=profile.gameid, game_name=profile.gameextrainfo or f"App {profile.gameid}")
        except Exception:
            # Activity history is enrichment and must never break profile reads.
            return

    def visibility(self) -> dict[str, Any]:
        profile_public = False
        games_accessible = False
        achievements_possible = False
        friends_accessible = False
        profile_reason = None
        try:
            profile = Profile.model_validate(self.steam.get_profile())
            profile_public = profile.communityvisibilitystate == 3
            if not profile_public:
                profile_reason = "Profile is not public according to communityvisibilitystate."
        except AppError as exc:
            profile_reason = exc.message
        try:
            self.steam.get_owned_games()
            games_accessible = True
            achievements_possible = True
        except AppError:
            pass
        try:
            self.steam.get_friends()
            friends_accessible = True
        except AppError:
            pass
        return {
            "profile_public": profile_public,
            "games_readable": games_accessible,
            "achievements_may_be_readable": achievements_possible,
            "friends_readable": friends_accessible,
            "explanation": {
                "profile": profile_reason or "Profile summary was readable.",
                "games": "Owned games were readable." if games_accessible else "Owned games are private or unavailable.",
                "achievements": "Achievement calls remain game-specific and can still be unavailable." if achievements_possible else "Achievements cannot be checked until game details are readable.",
                "friends": "Friend list was readable." if friends_accessible else "Friend list is private or unavailable.",
            },
        }

    def activity_summary(self, include_store: bool = True) -> dict[str, Any]:
        recent = self.library.recent_games(5)
        summary: dict[str, Any] = {
            "profile": self.profile(),
            "currently_playing": self.currently_playing(),
            "recent_games": [game.public_dict() for game in recent],
            "recent_two_week_playtime_hours": round(sum(game.recent_hours for game in recent), 2),
            "top_recent_games": self.library.most_played("recent", 5),
            "library_stats": self.library.stats(),
            "recent_achievements": self.achievements.recent_achievements(30, 10),
            "near_completion_games": self.achievements.almost_completed(70, 99.99, 5),
        }
        if include_store:
            summary["wishlist_sales"] = self.store.wishlist_sales(limit=20)
        return summary

    def deals_summary(self, exclude_owned: bool = True) -> dict[str, Any]:
        specials = self.store.specials(count=15, min_discount=0, sort_by="discount", exclude_owned=exclude_owned)
        wishlist = self.store.wishlist_best_deals(10)
        deep = self.store.deep_discounts(70, 15, exclude_owned=exclude_owned)
        return {
            "exclude_owned": exclude_owned,
            "current_discount_overview": {"specials_count": len(specials), "deep_discount_count": len(deep)},
            "wishlist_deals": wishlist,
            "deep_discounts": deep,
            "user_already_owns_exclusions": exclude_owned,
            "notable_candidates": specials[:10],
        }
