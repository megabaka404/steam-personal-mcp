from __future__ import annotations

from typing import Any

from errors import AppError
from models.account import unix_time_info


class FriendService:
    def __init__(self, steam, library) -> None:
        self.steam = steam
        self.library = library

    def friends(self, limit: int = 100) -> dict[str, Any]:
        try:
            raw = self.steam.get_friends()
            ids = [str(item.get("steamid")) for item in raw if item.get("steamid")][: max(1, min(100, limit))]
            profiles = {str(item.get("steamid")): item for item in self.steam.get_profiles(ids)}
            rows = []
            for item in raw[: len(ids)]:
                profile = profiles.get(str(item.get("steamid")), {})
                rows.append({"steamid": item.get("steamid"), "nickname": profile.get("personaname"), "profile_url": profile.get("profileurl"), "relationship": item.get("relationship"), "friend_since": unix_time_info(item.get("friend_since")), "online": bool(profile.get("personastate")), "current_game": {"appid": profile.get("gameid"), "name": profile.get("gameextrainfo")} if profile.get("gameid") or profile.get("gameextrainfo") else None})
            return {"available": True, "count": len(rows), "friends": rows}
        except AppError as exc:
            return {"available": False, "reason": exc.message, "friends": []}

    def playing(self, limit: int = 100) -> dict[str, Any]:
        result = self.friends(limit)
        if not result.get("available"):
            return result
        playing = [row for row in result["friends"] if row.get("current_game")]
        return {"available": True, "count": len(playing), "friends": playing}

    def activity_summary(self, limit: int = 100) -> dict[str, Any]:
        result = self.friends(limit)
        if not result.get("available"):
            return {**result, "online_count": None, "currently_playing": [], "most_common_current_games": [], "shared_games": []}
        rows = result.get("friends", [])
        currently_playing = [row for row in rows if row.get("current_game")]
        current_counts: dict[int, dict[str, Any]] = {}
        for row in currently_playing:
            game = row.get("current_game") or {}
            try:
                appid = int(game.get("appid"))
            except (TypeError, ValueError):
                continue
            entry = current_counts.setdefault(appid, {"appid": appid, "name": game.get("name") or f"App {appid}", "friend_count": 0, "friends": []})
            entry["friend_count"] += 1
            entry["friends"].append(row.get("nickname") or row.get("steamid"))
        shared_status = "available"
        shared_counts: dict[int, dict[str, Any]] = {}
        try:
            mine = {game.appid: game for game in self.library.owned_games()}
        except AppError:
            mine = {}
            shared_status = "not_available"
        if mine:
            for friend in rows[:25]:
                friend_id = str(friend.get("steamid") or "")
                if not friend_id:
                    continue
                try:
                    other_games = self.steam.get_owned_games(friend_id, include_free_games=True)
                except AppError:
                    shared_status = "partial_private_or_unavailable"
                    continue
                for other in other_games:
                    try:
                        appid = int(other.get("appid"))
                    except (TypeError, ValueError):
                        continue
                    if appid not in mine:
                        continue
                    entry = shared_counts.setdefault(appid, {"appid": appid, "name": mine[appid].name, "friend_count": 0, "friends": []})
                    entry["friend_count"] += 1
                    entry["friends"].append(friend.get("nickname") or friend_id)
        common_current = sorted(current_counts.values(), key=lambda item: (-item["friend_count"], item["name"].casefold()))
        shared = sorted(shared_counts.values(), key=lambda item: (-item["friend_count"], -mine[item["appid"]].playtime_forever, item["name"].casefold()))
        return {
            "available": True,
            "friends_scanned": len(rows),
            "online_count": sum(1 for row in rows if row.get("online")),
            "currently_playing_count": len(currently_playing),
            "currently_playing": currently_playing,
            "most_common_current_games": common_current,
            "shared_games": shared[:100],
            "data_availability": {
                "friend_profiles": "available",
                "friend_current_games": "available",
                "friend_owned_games": shared_status,
            },
            "limitations": [
                "Steam public profiles expose current game state when visible, not a complete friend playtime history.",
                "Friend owned-game overlap depends on each friend's public library and may be partial.",
            ],
        }

    def shared_games(self, friend_steam_id: str, count: int = 100) -> dict[str, Any]:
        if not friend_steam_id or not friend_steam_id.isdigit():
            raise AppError("INVALID_ARGUMENT", "friend_steam_id must be a SteamID64 string.")
        try:
            mine = {game.appid: game for game in self.library.owned_games()}
            other_raw = self.steam.get_owned_games(friend_steam_id, include_free_games=True)
            other = {int(item.get("appid")): item for item in other_raw if str(item.get("appid", "")).isdigit()}
        except AppError as exc:
            return {"available": False, "reason": exc.message, "games": []}
        shared = []
        for appid in sorted(mine.keys() & other.keys(), key=lambda value: mine[value].name.casefold()):
            shared.append({"appid": appid, "name": mine[appid].name, "my_playtime_hours": mine[appid].total_hours, "friend_playtime_hours": round(int(other[appid].get("playtime_forever", 0) or 0) / 60, 2)})
        return {"available": True, "friend_steam_id": friend_steam_id, "count": min(len(shared), max(1, min(500, count))), "games": shared[: max(1, min(500, count))]}
