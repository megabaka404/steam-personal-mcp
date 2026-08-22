from __future__ import annotations

import random
import time
from typing import Any

from errors import AppError


class RecommendationService:
    def __init__(self, library, achievements) -> None:
        self.library = library
        self.achievements = achievements

    def pick(self, *, count: int = 1, never_played_only: bool = False, max_playtime_hours: float | None = None, min_playtime_hours: float | None = None, inactive_days: int | None = None, exclude_appids: list[int] | None = None, randomize: bool = True) -> list[dict[str, Any]]:
        now = int(time.time())
        excluded = {int(value) for value in (exclude_appids or [])}
        games = []
        for game in self.library.owned_games():
            if game.appid in excluded or (never_played_only and game.playtime_forever > 0):
                continue
            if max_playtime_hours is not None and game.total_hours > max_playtime_hours:
                continue
            if min_playtime_hours is not None and game.total_hours < min_playtime_hours:
                continue
            if inactive_days is not None and (not game.rtime_last_played or now - game.rtime_last_played < inactive_days * 86400):
                continue
            games.append(game)
        if not games:
            return []
        if randomize:
            rng = random.SystemRandom()
            return [game.public_dict() for game in rng.sample(games, min(max(1, min(20, count)), len(games)))]
        games.sort(key=lambda game: (game.playtime_forever, game.name.casefold()))
        return [game.public_dict() for game in games[: max(1, min(20, count))]]

    def recommend(self, count: int = 5, mode: str = "balanced") -> list[dict[str, Any]]:
        if mode not in {"balanced", "backlog", "return_to", "comfort", "recent"}:
            raise AppError("INVALID_ARGUMENT", "mode must be balanced, backlog, return_to, comfort, or recent.")
        now = int(time.time())
        rows = []
        for game in self.library.owned_games():
            inactivity = (now - game.rtime_last_played) / 86400 if game.rtime_last_played else None
            score, reasons = _score(game, inactivity, mode)
            rows.append({**game.public_dict(), "score": round(score, 2), "reasons": reasons})
        rows.sort(key=lambda item: (-item["score"], item["name"].casefold()))
        return rows[: max(1, min(50, count))]

    def backlog(self, count: int = 20, max_hours: float | None = None) -> list[dict[str, Any]]:
        rows = []
        for game in self.library.owned_games():
            if game.name.casefold().endswith(("soundtrack", "utility")) or "software" in game.name.casefold():
                continue
            if game.playtime_forever > 0 and (max_hours is None or game.total_hours > max_hours):
                continue
            score = 100 - min(game.total_hours * 5, 50) + (8 if game.playtime_forever == 0 else 0)
            rows.append({**game.public_dict(), "score": round(score, 2), "reasons": ["owned but never launched" if game.playtime_forever == 0 else f"only {game.total_hours} hours played", "backlog candidate"]})
        rows.sort(key=lambda item: (-item["score"], item["name"].casefold()))
        return rows[: max(1, min(100, count))]

    def return_to(self, count: int = 20, min_hours: float = 1) -> list[dict[str, Any]]:
        now = int(time.time())
        rows = []
        for game in self.library.owned_games():
            if game.total_hours < min_hours or not game.rtime_last_played:
                continue
            inactive = max(0, (now - game.rtime_last_played) / 86400)
            if inactive < 30:
                continue
            score = min(game.total_hours, 100) * 0.35 + min(inactive, 730) * 0.08 + (game.playtime_2weeks == 0) * 15
            rows.append({**game.public_dict(), "inactive_days": round(inactive), "score": round(score, 2), "reasons": [f"played for {game.total_hours} hours", f"not played for {round(inactive)} days"]})
        rows.sort(key=lambda item: (-item["score"], item["name"].casefold()))
        return rows[: max(1, min(100, count))]

    def compare_my_games(self, games: list[str | int]) -> list[dict[str, Any]]:
        if not games or len(games) > 10:
            raise AppError("INVALID_ARGUMENT", "games must contain between 1 and 10 items.")
        rows = []
        for value in games:
            record = self.library.game_in_library(appid=value if isinstance(value, int) else None, game=value if isinstance(value, str) else None)
            if record is None:
                rows.append({"query": value, "owned": False})
                continue
            achievement = self.achievements.summary(appid=record.appid)
            rows.append({"appid": record.appid, "name": record.name, "owned": True, "playtime_hours": record.total_hours, "recent_two_week_hours": record.recent_hours, "last_played": record.public_dict()["last_played"], "achievements": achievement})
        return rows

    def what_should_play_next(self, count: int = 5) -> list[dict[str, Any]]:
        rows = self.recommend(max(3, min(10, count)), "balanced")
        # Add achievement completion only for the small returned set, keeping this summary bounded.
        for row in rows:
            summary = self.achievements.summary(appid=row["appid"])
            row["achievement_completion"] = summary.get("completion_percent") if summary.get("available") else None
            if row["achievement_completion"] is not None and row["achievement_completion"] >= 70:
                row["reasons"].append(f"{row['achievement_completion']}% achievement completion makes it easy to continue")
        return rows


def _score(game, inactivity: float | None, mode: str) -> tuple[float, list[str]]:
    recent = game.recent_hours
    total = game.total_hours
    inactive = inactivity or 0
    if mode == "backlog":
        score = 85 - min(total * 4, 50) + (10 if total == 0 else 0)
        reasons = ["not started" if total == 0 else "lightly played", "good backlog candidate"]
    elif mode == "return_to":
        score = min(total, 100) * 0.25 + min(inactive, 730) * 0.12 if total > 0 else -100
        reasons = [f"{round(total, 1)} total hours", f"inactive for about {round(inactive)} days"]
    elif mode == "comfort":
        score = min(total, 200) * 0.35 + recent * 1.5
        reasons = ["familiar game" if total >= 5 else "low-commitment option", f"{round(total, 1)} total hours"]
    elif mode == "recent":
        score = recent * 6 - total * 0.02
        reasons = [f"{round(recent, 1)} hours in the last two weeks"]
    else:
        score = 35 + (25 if total == 0 else 0) + max(0, 30 - total) + recent * 2 + min(inactive, 365) * 0.04
        reasons = ["balances backlog and recent momentum"]
        if total == 0:
            reasons.append("never played")
        elif total < 5:
            reasons.append("barely started")
        if recent > 0:
            reasons.append("recently active")
    return score, reasons
