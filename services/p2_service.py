from __future__ import annotations

import datetime as dt
import time
from typing import Any

from errors import AppError
from models.account import unix_time_info


class P2Service:
    def __init__(self, activity_history, library=None) -> None:
        self.history = activity_history
        self.library = library

    def play_session_history(self, *, days: int = 365, count: int = 100) -> dict[str, Any]:
        if days < 0:
            raise AppError("INVALID_ARGUMENT", "days must be non-negative.")
        count = _bounded(count, 1, 1000)
        cutoff = int(time.time()) - days * 86400
        sessions = [session for session in self.history.sessions(limit=5000) if (session["last_observed_at"]["timestamp"] or 0) >= cutoff]
        sessions.sort(key=lambda item: (item["last_observed_at"]["timestamp"] or 0, item["appid"]), reverse=True)
        return {
            "available": True,
            "days": days,
            "count": min(count, len(sessions)),
            "sessions": sessions[:count],
            "source": "MCP-observed Steam profile snapshots",
            "note": "Session ends are not claimed unless observed; duration counts only the span between snapshots.",
        }

    def recent_play_sessions(self, *, days: int = 30, count: int = 20) -> dict[str, Any]:
        return self.play_session_history(days=days, count=count)

    def year_in_review(self, *, year: int | None = None) -> dict[str, Any]:
        year = int(year or dt.datetime.now(dt.timezone.utc).year)
        if year < 2000 or year > 2100:
            raise AppError("INVALID_ARGUMENT", "year must be between 2000 and 2100.")
        start_dt = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end_dt = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        start = int(start_dt.timestamp())
        end = int(end_dt.timestamp())
        snapshots = self.history.snapshots(limit=50000)
        sessions = self.history.sessions(limit=5000)
        previous_appids = {row["appid"] for row in snapshots if (row["observed_at"]["timestamp"] or 0) < start}
        year_sessions = []
        for session in sessions:
            session_start = session["start"]["timestamp"] or 0
            session_last = session["last_observed_at"]["timestamp"] or 0
            if session_last < start or session_start >= end:
                continue
            clipped_start = max(start, session_start)
            clipped_last = min(end - 1, session_last)
            year_sessions.append({**session, "_clipped_start": clipped_start, "_clipped_last": clipped_last, "_observed_seconds": max(0, clipped_last - clipped_start)})
        by_appid: dict[int, dict[str, Any]] = {}
        for session in year_sessions:
            appid = session["appid"]
            item = by_appid.setdefault(appid, {"appid": appid, "game_name": session["game_name"], "observed_seconds": 0, "sessions": 0, "first_observed": session["start"], "last_observed": session["last_observed_at"]})
            item["observed_seconds"] += session["_observed_seconds"]
            item["sessions"] += 1
            if (session["start"]["timestamp"] or 0) < (item["first_observed"]["timestamp"] or 0):
                item["first_observed"] = session["start"]
            if (session["last_observed_at"]["timestamp"] or 0) > (item["last_observed"]["timestamp"] or 0):
                item["last_observed"] = session["last_observed_at"]
        top_games = []
        for item in sorted(by_appid.values(), key=lambda value: (-value["observed_seconds"], value["game_name"].casefold())):
            top_games.append({**item, "observed_minutes": round(item["observed_seconds"] / 60, 2), "observed_hours": round(item["observed_seconds"] / 3600, 2)})
        first_observed = min((row["observed_at"] for row in snapshots if start <= (row["observed_at"]["timestamp"] or 0) < end), key=lambda value: value["timestamp"], default=None)
        last_observed = max((row["observed_at"] for row in snapshots if start <= (row["observed_at"]["timestamp"] or 0) < end), key=lambda value: value["timestamp"], default=None)
        new_games = []
        for item in top_games:
            first_year_session = min((session for session in year_sessions if session["appid"] == item["appid"]), key=lambda value: value["_clipped_start"], default=None)
            if first_year_session and item["appid"] not in previous_appids:
                new_games.append({"appid": item["appid"], "game_name": item["game_name"], "first_observed": first_year_session["start"], "note": "First observed by MCP in this year; not proof of purchase or first launch."})
        returned_to = []
        for appid, item in by_appid.items():
            starts = sorted(session["_clipped_start"] for session in year_sessions if session["appid"] == appid)
            if len(starts) >= 2 and any(right - left >= 7 * 86400 for left, right in zip(starts, starts[1:])):
                returned_to.append({"appid": appid, "game_name": item["game_name"], "sessions": len(starts), "note": "Returned-to classification is based on observed session gaps."})
        total_seconds = sum(item["observed_seconds"] for item in top_games)
        current_api_context = self._current_api_context(snapshots=snapshots, year_sessions=year_sessions)
        return {
            "available": True,
            "year": year,
            "top_games": top_games[:20],
            "most_played": top_games[0] if top_games else None,
            "new_games_started": new_games,
            "returned_to": returned_to,
            "total_observed_playtime_seconds": total_seconds,
            "total_observed_playtime_minutes": round(total_seconds / 60, 2),
            "total_observed_playtime_hours": round(total_seconds / 3600, 2),
            "total_observed_playtime": {
                "seconds": total_seconds,
                "minutes": round(total_seconds / 60, 2),
                "hours": round(total_seconds / 3600, 2),
            },
            "current_api_context": current_api_context,
            "data_coverage": {
                "snapshot_count": sum(1 for row in snapshots if start <= (row["observed_at"]["timestamp"] or 0) < end),
                "session_count": len(year_sessions),
                "first_observed": first_observed,
                "last_observed": last_observed,
                "source": "MCP-observed snapshots only",
                "is_official_steam_year_in_review": False,
                "limitations": "No unobserved playtime, purchase history, launch history, or wishlist history is inferred.",
            },
        }

    def _current_api_context(self, *, snapshots: list[dict[str, Any]], year_sessions: list[dict[str, Any]]) -> dict[str, Any]:
        if snapshots and year_sessions:
            return {
                "available": False,
                "reason": "Historical MCP observations are available for this year; no fallback was needed.",
                "recent_games": [],
                "source": "Steam Web API fallback not queried",
            }
        if self.library is None:
            return {
                "available": False,
                "reason": "No current Steam library service is attached.",
                "recent_games": [],
                "source": "not_available",
            }
        try:
            recent = self.library.recent_games(20)
            return {
                "available": True,
                "recent_games": [game.public_dict() for game in recent],
                "source": "current Steam Web API recent-games response",
                "note": "These are current API facts, not reconstructed historical sessions.",
            }
        except AppError as exc:
            return {
                "available": False,
                "reason": exc.message,
                "recent_games": [],
                "source": "current Steam Web API",
            }
        except Exception:
            return {
                "available": False,
                "reason": "Current Steam recent-games data is unavailable.",
                "recent_games": [],
                "source": "current Steam Web API",
            }


def _bounded(value: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return minimum
