from __future__ import annotations

import time
from typing import Any

from errors import AppError
from models.achievement import Achievement


class AchievementService:
    def __init__(self, steam, library, resolver) -> None:
        self.steam = steam
        self.library = library
        self.resolver = resolver

    def get_achievements(self, *, game: str | None = None, appid: int | None = None, include_locked: bool = True) -> dict[str, Any]:
        resolved = self.resolver.resolve(game=game, appid=appid)
        try:
            raw = self.steam.get_achievements(resolved.appid)
        except AppError as exc:
            return _unavailable(resolved.appid, resolved.name, exc.code, exc.message)

        player = _player_payload(raw)
        if player is None:
            return _unavailable(resolved.appid, resolved.name, "INVALID_RESPONSE", "Steam did not return player achievement data.")
        if player.get("success") is False:
            return _unavailable(
                resolved.appid,
                _game_name(player, resolved.name),
                _player_failure_code(player),
                str(player.get("error") or "Steam could not read player achievement data."),
            )
        raw_items = player.get("achievements")
        if not isinstance(raw_items, list):
            return _unavailable(resolved.appid, _game_name(player, resolved.name), "PLAYER_STATS_UNAVAILABLE", "Steam did not expose player achievement status for this game.")

        schema: dict[str, Any] = {}
        schema_available = True
        try:
            value = self.steam.get_achievement_schema(resolved.appid)
            schema = value if isinstance(value, dict) else {}
        except AppError:
            # The player state is still useful without display metadata; do not
            # turn a schema-only outage into a false all-locked result.
            schema_available = False
        rows = _merge_achievements(raw, schema)
        if not rows:
            return {
                "available": True,
                "appid": resolved.appid,
                "game_name": _game_name(player, resolved.name),
                "total_achievements": 0,
                "unlocked": 0,
                "locked": 0,
                "completion_percent": 0.0,
                "achievements": [],
                "schema_available": schema_available,
            }
        visible = rows if include_locked else [item for item in rows if item.achieved]
        game_name = _game_name(player, str((schema.get("game") or {}).get("gameName") or resolved.name))
        unlocked = sum(item.achieved for item in rows)
        result = {
            "available": True,
            "appid": resolved.appid,
            "game_name": game_name,
            "total_achievements": len(rows),
            "unlocked": unlocked,
            "locked": len(rows) - unlocked,
            "completion_percent": round(unlocked * 100 / len(rows), 2),
            "achievements": [item.public_dict() for item in visible],
        }
        if not schema_available:
            result["schema_available"] = False
        return result

    def summary(self, *, game: str | None = None, appid: int | None = None) -> dict[str, Any]:
        result = self.get_achievements(game=game, appid=appid, include_locked=False)
        if not result.get("available"):
            return {key: result[key] for key in ("available", "reason", "appid", "game_name") if key in result}
        return {key: result[key] for key in ("available", "appid", "game_name", "total_achievements", "unlocked", "locked", "completion_percent")}

    def recent_achievements(self, days: int = 30, count: int = 30) -> dict[str, Any]:
        if days < 0 or count < 1:
            raise AppError("INVALID_ARGUMENT", "days must be non-negative and count must be positive.")
        threshold = int(time.time()) - days * 86400
        rows: list[dict[str, Any]] = []
        games = self.library.recent_games(min(30, max(10, count)))
        for game in games:
            result = self.get_achievements(appid=game.appid, include_locked=True)
            if not result.get("available"):
                continue
            for achievement in result.get("achievements", []):
                unlock = (achievement.get("unlock_time") or {}).get("timestamp")
                if unlock and unlock >= threshold:
                    rows.append({"appid": game.appid, "game_name": result.get("game_name", game.name), **achievement})
        rows.sort(key=lambda item: (item.get("unlock_time") or {}).get("timestamp", 0), reverse=True)
        return {"days": days, "scanned_recent_games": len(games), "count": min(count, len(rows)), "achievements": rows[:count]}

    def almost_completed(self, min_completion: float = 70, max_completion: float = 99.99, count: int = 20) -> list[dict[str, Any]]:
        if not 0 <= min_completion <= max_completion <= 100:
            raise AppError("INVALID_ARGUMENT", "Completion bounds must satisfy 0 <= min <= max <= 100.")
        rows = []
        for game in self._candidate_games():
            summary = self.summary(appid=game.appid)
            if summary.get("available") and min_completion <= summary.get("completion_percent", 0) <= max_completion:
                rows.append({**summary, "playtime_hours": game.total_hours, "last_played": game.public_dict().get("last_played")})
        rows.sort(key=lambda item: (-item["completion_percent"], item.get("playtime_hours", 0)))
        return rows[: max(1, min(100, count))]

    def completion_candidates(self, count: int = 20) -> list[dict[str, Any]]:
        rows = []
        for game in self._candidate_games():
            summary = self.summary(appid=game.appid)
            if not summary.get("available") or summary.get("unlocked", 0) <= 0:
                continue
            remaining = summary["locked"]
            score = summary["completion_percent"] * 0.75 + max(0, 20 - remaining) * 1.5 + min(game.total_hours, 100) * 0.05
            rows.append({**summary, "playtime_hours": game.total_hours, "remaining_achievements": remaining, "score": round(score, 2), "reasons": _completion_reasons(summary, game.total_hours)})
        rows.sort(key=lambda item: (-item["score"], -item["completion_percent"]))
        return rows[: max(1, min(100, count))]

    def _candidate_games(self):
        # A bounded scan protects accounts with very large libraries from a request storm.
        games = self.library.owned_games()
        games.sort(key=lambda item: item.playtime_forever, reverse=True)
        return [game for game in games[:50] if game.playtime_forever > 0]


def _merge_achievements(raw: dict[str, Any], schema: dict[str, Any]) -> list[Achievement]:
    schema_items = ((schema.get("game") or {}).get("availableGameStats") or {}).get("achievements") or []
    player = _player_payload(raw) or {}
    raw_items = player.get("achievements") or []
    raw_by_name = {str(item.get("apiname") or item.get("name")): item for item in raw_items if isinstance(item, dict)}
    rows = []
    for item in schema_items:
        if not isinstance(item, dict):
            continue
        api_name = str(item.get("name") or item.get("apiname") or "")
        current = raw_by_name.get(api_name, {})
        rows.append(Achievement(
            api_name=api_name,
            display_name=str(item.get("displayName") or item.get("display_name") or api_name),
            description=str(item.get("description") or ""),
            achieved=_as_bool(current.get("achieved", False)),
            unlocktime=_timestamp_or_none(current.get("unlocktime")),
            hidden=bool(int(item.get("hidden", 0) or 0)),
            icon=item.get("icon"),
            icongray=item.get("icongray"),
        ))
    if not rows:
        for item in raw_items:
            if isinstance(item, dict):
                rows.append(Achievement(api_name=str(item.get("apiname") or item.get("name") or ""), achieved=_as_bool(item.get("achieved", False)), unlocktime=_timestamp_or_none(item.get("unlocktime"))))
    return rows


def _player_payload(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    nested = raw.get("playerstats")
    if isinstance(nested, dict):
        return nested
    # Keep compatibility with older/mock clients that returned the inner
    # object directly, while preferring Steam's actual nested response.
    return raw if "achievements" in raw else None


def _game_name(player: dict[str, Any], fallback: str) -> str:
    return str(player.get("gameName") or fallback)


def _player_failure_code(player: dict[str, Any]) -> str:
    error = str(player.get("error") or "").casefold()
    if "private" in error:
        return "PROFILE_PRIVATE"
    if "stats" in error or "achievement" in error:
        return "PLAYER_STATS_UNAVAILABLE"
    return "PLAYER_STATS_UNAVAILABLE"


def _unavailable(appid: int, game_name: str, code: str, detail: str) -> dict[str, Any]:
    reasons = {
        "PROFILE_PRIVATE": "Achievements are unavailable because the Steam profile or game stats are private.",
        "HTTP_UNAUTHORIZED": "Achievements are unavailable because Steam rejected the request.",
        "HTTP_FORBIDDEN": "Achievements are unavailable because Steam rejected the request.",
        "INVALID_API_KEY": "Achievements are unavailable because Steam API credentials are not configured or invalid.",
        "NETWORK_ERROR": "Achievements are unavailable because the Steam request failed.",
        "PLAYER_STATS_UNAVAILABLE": "Achievements are unavailable because Steam did not expose player status for this game.",
        "INVALID_RESPONSE": "Achievements are unavailable because Steam returned no usable player data.",
    }
    return {
        "available": False,
        "reason": reasons.get(code, detail or "Achievements are unavailable for this game."),
        "reason_code": code,
        "appid": appid,
        "game_name": game_name,
    }


def _timestamp_or_none(value: Any) -> int | None:
    try:
        number = int(value or 0)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _completion_reasons(summary: dict[str, Any], hours: float) -> list[str]:
    reasons = [f"{summary['completion_percent']}% complete", f"{summary['locked']} achievements remaining"]
    if hours >= 10:
        reasons.append(f"already invested {round(hours, 1)} hours")
    return reasons
