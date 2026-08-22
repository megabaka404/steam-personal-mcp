from __future__ import annotations

import time
from typing import Any


def _game(appid: int, name: str, hours: float, recent: float, last_days: int | None, *, free: bool = False) -> dict[str, Any]:
    now = int(time.time())
    return {
        "appid": appid,
        "name": name,
        "playtime_forever": int(hours * 60),
        "playtime_2weeks": int(recent * 60),
        "rtime_last_played": now - last_days * 86400 if last_days is not None else None,
        "img_icon_url": f"https://mock.invalid/{appid}.jpg",
        "is_free": free,
    }


class MockSteamClient:
    def __init__(self) -> None:
        self.last_connectivity = "mock"
        self.games = [
            _game(646570, "Slay the Spire", 186.4, 11.5, 1),
            _game(1145360, "Hades", 92.1, 0, 45),
            _game(1145350, "Hades II", 61.2, 8.2, 2),
            _game(588650, "Dead Cells", 54.0, 0, 220),
            _game(367520, "Hollow Knight", 47.5, 0, 410),
            _game(413150, "Stardew Valley", 38.6, 0, 190),
            _game(620, "Portal 2", 25.0, 0, 900),
            _game(105600, "Terraria", 22.5, 0, 280),
            _game(400, "Portal", 17.4, 0, 760),
            _game(72850, "The Elder Scrolls V: Skyrim", 14.2, 0, 600),
            _game(632360, "Risk of Rain 2", 12.0, 0, 240),
            _game(2379780, "Balatro", 10.5, 1.3, 6),
            _game(292030, "The Witcher 3: Wild Hunt", 8.7, 0, 500),
            _game(440, "Team Fortress 2", 5.0, 0, 120, free=True),
            _game(730, "Counter-Strike 2", 3.1, 0, 100, free=True),
            _game(250900, "The Binding of Isaac: Rebirth", 1.6, 0, 200),
            _game(8930, "Sid Meier's Civilization V", 0, 0, None),
            _game(255710, "Cities: Skylines", 0, 0, None),
            _game(1250410, "Microsoft Flight Simulator", 0, 0, None),
            _game(1056000, "Mock Software Utility", 0, 0, None),
        ]
        self.profile = {
            "steamid": "76561198000000000",
            "personaname": "Mock Steam User",
            "profileurl": "https://steamcommunity.com/profiles/76561198000000000/",
            "avatar": "https://mock.invalid/avatar.jpg",
            "avatarfull": "https://mock.invalid/avatar-full.jpg",
            "personastate": 1,
            "communityvisibilitystate": 3,
            "profilestate": 1,
            "timecreated": 1420070400,
            "loccountrycode": "US",
            "gameid": 646570,
            "gameextrainfo": "Slay the Spire",
        }
        self.friends = [
            {"steamid": "76561198000000001", "relationship": "friend", "friend_since": 1700000000},
            {"steamid": "76561198000000002", "relationship": "friend", "friend_since": 1705000000},
            {"steamid": "76561198000000003", "relationship": "friend", "friend_since": 1710000000},
        ]
        self.friend_profiles = [
            {"steamid": "76561198000000001", "personaname": "Rogue Friend", "profileurl": "https://steamcommunity.com/profiles/76561198000000001/", "personastate": 1, "gameid": 1145350, "gameextrainfo": "Hades II"},
            {"steamid": "76561198000000002", "personaname": "Co-op Friend", "profileurl": "https://steamcommunity.com/profiles/76561198000000002/", "personastate": 1, "gameid": 440, "gameextrainfo": "Team Fortress 2"},
            {"steamid": "76561198000000003", "personaname": "Away Friend", "profileurl": "https://steamcommunity.com/profiles/76561198000000003/", "personastate": 0},
        ]
        self.achievements = _mock_achievements()
        self.wishlist = [
            {"appid": 1627720, "priority": 1, "date_added": int(time.time()) - 86400 * 80},
            {"appid": 1794680, "priority": 2, "date_added": int(time.time()) - 86400 * 50},
            {"appid": 632360, "priority": 3, "date_added": int(time.time()) - 86400 * 20},
        ]

    def get_profile(self) -> dict[str, Any]:
        return dict(self.profile)

    def get_owned_games(self, steamid: str | None = None, *, include_free_games: bool = True) -> list[dict[str, Any]]:
        if steamid and steamid != self.profile["steamid"]:
            return [game for game in self.games[:10] if game["appid"] % 2 == 0]
        return [game for game in self.games if include_free_games or not game.get("is_free")]

    def get_recent_games(self, count: int = 10) -> list[dict[str, Any]]:
        return [game for game in sorted(self.games, key=lambda item: item.get("playtime_2weeks", 0), reverse=True) if game.get("playtime_2weeks", 0)][:count]

    def get_achievements(self, appid: int) -> dict[str, Any]:
        if appid not in self.achievements:
            return {
                "playerstats": {
                    "success": False,
                    "error": "Game stats are unavailable for this game.",
                    "gameName": next((g["name"] for g in self.games if g["appid"] == appid), "Unknown"),
                }
            }
        data = self.achievements[appid]
        return {
            "playerstats": {
                "success": True,
                "gameName": data["gameName"],
                "achievements": [dict(item) for item in data["achievements"]],
            }
        }

    def get_achievement_schema(self, appid: int) -> dict[str, Any]:
        data = self.achievements.get(appid)
        return {"game": {"gameName": data["gameName"], "availableGameStats": {"achievements": data["schema"]}}} if data else {"game": {"gameName": "Unknown", "availableGameStats": {"achievements": []}}}

    def get_player_stats(self, appid: int) -> dict[str, Any]:
        return {"playerstats": {"steamID": self.profile["steamid"], "gameName": "Mock", "stats": []}}

    def get_friends(self, steamid: str | None = None) -> list[dict[str, Any]]:
        return [dict(item) for item in self.friends]

    def get_profiles(self, steamids: list[str]) -> list[dict[str, Any]]:
        return [dict(item) for item in self.friend_profiles if item["steamid"] in steamids]

    def get_wishlist(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.wishlist]


class MockStoreClient:
    def __init__(self) -> None:
        self.last_connectivity = "mock"
        self.items = _mock_store_items()

    def search(self, query: str, count: int = 20) -> list[dict[str, Any]]:
        q = query.casefold().strip()
        items = [item for item in self.items if not q or q in item["name"].casefold()]
        return [self._search_item(item) for item in items[:count]]

    def details(self, appid: int) -> dict[str, Any] | None:
        item = next((item for item in self.items if item["appid"] == appid), None)
        return dict(item["details"]) if item else None

    def review_summary(self, appid: int) -> dict[str, Any] | None:
        item = next((item for item in self.items if item["appid"] == appid), None)
        if not item:
            return None
        percentage = int(item.get("review_percentage") or 0)
        return {
            "review_score": min(9, max(0, round(percentage / 10))),
            "review_percentage": percentage,
            "review_count": percentage * 100,
        }

    def featured_items(self) -> list[dict[str, Any]]:
        return [self._search_item(item) for item in self.items if item["details"].get("price_overview", {}).get("discount_percent", 0) > 0]

    @staticmethod
    def _search_item(item: dict[str, Any]) -> dict[str, Any]:
        price = item["details"].get("price_overview")
        return {"id": item["appid"], "appid": item["appid"], "type": 0, "name": item["name"], "price": {"currency": price.get("currency"), "initial": price.get("initial"), "final": price.get("final")} if price else None, "discount_percent": price.get("discount_percent", 0) if price else 0}


def _mock_achievements() -> dict[int, dict[str, Any]]:
    def pack(name: str, total: int, unlocked: int) -> dict[str, Any]:
        rows = []
        schema = []
        now = int(time.time())
        for index in range(total):
            achieved = index < unlocked
            rows.append({"apiname": f"ACH_{index}", "achieved": 1 if achieved else 0, "unlocktime": now - index * 86400 if achieved else 0})
            schema.append({"name": f"ACH_{index}", "displayName": f"{name} Achievement {index + 1}", "description": f"Complete challenge {index + 1}.", "hidden": 0, "icon": "https://mock.invalid/icon.png", "icongray": "https://mock.invalid/icon-gray.png"})
        return {"gameName": name, "achievements": rows, "schema": schema}

    return {646570: pack("Slay the Spire", 20, 17), 1145350: pack("Hades II", 10, 8), 1145360: pack("Hades", 49, 30), 588650: pack("Dead Cells", 30, 12), 2379780: pack("Balatro", 10, 7), 367520: pack("Hollow Knight", 63, 20)}


def _mock_store_items() -> list[dict[str, Any]]:
    def item(appid: int, name: str, initial: int | None, final: int | None, discount: int, genres: list[str], score: int, percentage: int, dlc: list[int] | None = None) -> dict[str, Any]:
        price = None if initial is None else {"currency": "USD", "initial": initial, "final": final, "discount_percent": discount}
        return {"appid": appid, "name": name, "review_score": score, "review_percentage": percentage, "details": {"type": "game", "name": name, "steam_appid": appid, "header_image": f"https://mock.invalid/{appid}/header.jpg", "developers": ["Mock Studio"], "publishers": ["Mock Publisher"], "release_date": {"date": "2024-01-01"}, "genres": [{"id": str(index), "description": genre} for index, genre in enumerate(genres)], "categories": [], "short_description": f"Mock details for {name}.", "price_overview": price, "dlc": dlc or [], "supported_languages": "English", "platforms": {"windows": True, "mac": False, "linux": True}, "metacritic": {"score": score} if score else None, "recommendations": {"total": percentage * 100}}}

    return [
        item(646570, "Slay the Spire", 2499, 2499, 0, ["Indie", "Strategy"], 95, 96, [877620]),
        item(1145350, "Hades II", 2999, 2099, 30, ["Action", "Roguelike"], 92, 95),
        item(1145360, "Hades", 2499, 624, 75, ["Action", "Roguelike"], 93, 98),
        item(588650, "Dead Cells", 2499, 999, 60, ["Action", "Roguelike"], 89, 95, [8800]),
        item(367520, "Hollow Knight", 1499, 749, 50, ["Action", "Metroidvania"], 90, 96),
        item(1627720, "Lies of P", 5999, 1799, 70, ["Action", "RPG"], 80, 90),
        item(1794680, "Vampire Survivors", 499, 249, 50, ["Action", "Roguelike"], 87, 98),
        item(632360, "Risk of Rain 2", 2499, 624, 75, ["Action", "Roguelike"], 93, 96),
        item(877620, "Slay the Spire Soundtrack", 399, 99, 75, ["DLC", "Soundtrack"], 90, 90),
    ]
