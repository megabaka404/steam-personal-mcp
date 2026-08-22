from __future__ import annotations

from typing import Any

from cache.memory_cache import MemoryTTLCache
from clients.http_client import JsonHttpClient
from config import Settings
from errors import AppError


class SteamClient:
    """Personal account client. Store calls intentionally live in StoreClient."""

    base_url = "https://api.steampowered.com"

    def __init__(self, settings: Settings, cache: MemoryTTLCache, http: JsonHttpClient | None = None) -> None:
        self.settings = settings
        self.cache = cache
        self.http = http or JsonHttpClient(
            timeout=settings.http_timeout,
            max_retries=settings.max_retries,
            min_request_interval=settings.min_request_interval,
            cache=cache,
        )

    def _require_credentials(self, steamid: str | None = None) -> tuple[str, str]:
        if not self.settings.api_key:
            raise AppError("INVALID_API_KEY", "STEAM_API_KEY is not configured.")
        resolved_id = steamid or self.settings.steam_id
        if not resolved_id:
            raise AppError("INVALID_ARGUMENT", "STEAM_ID is not configured.")
        return self.settings.api_key, resolved_id

    def _get(self, interface: str, method: str, *, params: dict[str, Any], cache_key: str, cache_ttl: int) -> dict[str, Any]:
        data = self.http.get_json(
            f"{self.base_url}/{interface}/{method}/v1/" if not method.endswith("v2") else f"{self.base_url}/{interface}/{method}/",
            params={**params, "format": "json"},
            cache_key=cache_key,
            cache_ttl=cache_ttl,
            error_context=f"Steam {interface}/{method}",
        )
        if not isinstance(data, dict):
            raise AppError("NETWORK_ERROR", "Steam returned an unexpected response shape.")
        return data

    def get_profile(self) -> dict[str, Any]:
        key, steamid = self._require_credentials()
        data = self.http.get_json(
            f"{self.base_url}/ISteamUser/GetPlayerSummaries/v2/",
            params={"key": key, "steamids": steamid, "format": "json"},
            cache_key=f"profile:{steamid}", cache_ttl=60,
            error_context="Steam profile API",
        )
        players = (data.get("response") or {}).get("players") if isinstance(data, dict) else None
        if not players:
            raise AppError("PROFILE_PRIVATE", "Steam profile is private or the SteamID was not found.")
        return players[0]

    def get_owned_games(self, steamid: str | None = None, *, include_free_games: bool = True) -> list[dict[str, Any]]:
        key, resolved_id = self._require_credentials(steamid)
        data = self.http.get_json(
            f"{self.base_url}/IPlayerService/GetOwnedGames/v1/",
            params={
                "key": key, "steamid": resolved_id, "format": "json",
                "include_appinfo": "1", "include_played_free_games": "1" if include_free_games else "0",
            },
            cache_key=f"owned:{resolved_id}:{include_free_games}", cache_ttl=600,
            error_context="Steam owned games API",
        )
        response = data.get("response") if isinstance(data, dict) else None
        if not isinstance(response, dict) or "games" not in response:
            raise AppError("PROFILE_PRIVATE", "Steam game details are not publicly available.")
        return response.get("games") or []

    def get_recent_games(self, count: int = 10) -> list[dict[str, Any]]:
        key, steamid = self._require_credentials()
        data = self.http.get_json(
            f"{self.base_url}/IPlayerService/GetRecentlyPlayedGames/v1/",
            params={"key": key, "steamid": steamid, "format": "json", "count": count},
            cache_key=f"recent:{steamid}:{count}", cache_ttl=120,
            error_context="Steam recently played games API",
        )
        response = data.get("response") if isinstance(data, dict) else None
        return (response or {}).get("games") or [] if isinstance(response, dict) else []

    def get_achievements(self, appid: int) -> dict[str, Any]:
        key, steamid = self._require_credentials()
        return self.http.get_json(
            f"{self.base_url}/ISteamUserStats/GetPlayerAchievements/v1/",
            params={"key": key, "steamid": steamid, "appid": appid, "format": "json"},
            cache_key=f"achievements:{steamid}:{appid}", cache_ttl=300,
            error_context="Steam achievements API",
        )

    def get_achievement_schema(self, appid: int) -> dict[str, Any]:
        key, _ = self._require_credentials()
        return self.http.get_json(
            f"{self.base_url}/ISteamUserStats/GetSchemaForGame/v2/",
            params={"key": key, "appid": appid, "format": "json"},
            cache_key=f"achievement-schema:{appid}", cache_ttl=3600,
            error_context="Steam achievement schema API",
        )

    def get_player_stats(self, appid: int) -> dict[str, Any]:
        key, steamid = self._require_credentials()
        return self.http.get_json(
            f"{self.base_url}/ISteamUserStats/GetUserStatsForGame/v2/",
            params={"key": key, "steamid": steamid, "appid": appid, "format": "json"},
            cache_key=f"player-stats:{steamid}:{appid}", cache_ttl=300,
            error_context="Steam player stats API",
        )

    def current_players(self, appid: int) -> int | None:
        key, _ = self._require_credentials()
        data = self.http.get_json(
            f"{self.base_url}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
            params={"key": key, "appid": appid, "format": "json"},
            cache_key=f"current-players:{appid}", cache_ttl=120,
            error_context="Steam current players API",
        )
        response = data.get("response") if isinstance(data, dict) else None
        value = response.get("player_count") if isinstance(response, dict) else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def get_friends(self, steamid: str | None = None) -> list[dict[str, Any]]:
        key, resolved_id = self._require_credentials(steamid)
        data = self.http.get_json(
            f"{self.base_url}/ISteamUser/GetFriendList/v1/",
            params={"key": key, "steamid": resolved_id, "relationship": "friend", "format": "json"},
            cache_key=f"friends:{resolved_id}", cache_ttl=300,
            error_context="Steam friend list API",
        )
        friends = (data.get("friendslist") or {}).get("friends") if isinstance(data, dict) else None
        if friends is None:
            raise AppError("PROFILE_PRIVATE", "Steam friend list is private or unavailable.")
        return friends

    def get_profiles(self, steamids: list[str]) -> list[dict[str, Any]]:
        key, _ = self._require_credentials()
        data = self.http.get_json(
            f"{self.base_url}/ISteamUser/GetPlayerSummaries/v2/",
            params={"key": key, "steamids": ",".join(steamids), "format": "json"},
            cache_key=f"profiles:{','.join(steamids)}", cache_ttl=60,
            error_context="Steam profile API",
        )
        return (data.get("response") or {}).get("players") or []

    def get_wishlist(self) -> list[dict[str, Any]]:
        _, steamid = self._require_credentials()
        data = self.http.get_json(
            f"{self.base_url}/IWishlistService/GetWishlist/v1/",
            params={"steamid": steamid},
            cache_key=f"wishlist:{steamid}", cache_ttl=600,
            error_context="Steam wishlist API",
        )
        items = (data.get("response") or {}).get("items") if isinstance(data, dict) else None
        if items is None:
            raise AppError("UNSUPPORTED", "Steam wishlist data is not publicly available for this account.")
        return items
