from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from models.account import unix_time_info


SESSION_GAP_SECONDS = 30 * 60


class ActivityHistoryStore:
    """Persistent MCP-observed activity snapshots and derived play sessions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._memory_connection = (
            sqlite3.connect(":memory:", timeout=10, check_same_thread=False)
            if str(path) == ":memory:"
            else None
        )
        if self._memory_connection is not None:
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at INTEGER NOT NULL,
                    appid INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    UNIQUE(observed_at, appid)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_activity_snapshots_observed_at ON activity_snapshots(observed_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_activity_snapshots_appid ON activity_snapshots(appid, observed_at ASC)")

    def record_snapshot(self, *, appid: int, game_name: str, observed_at: int | None = None) -> dict[str, Any]:
        timestamp = int(observed_at or time.time())
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO activity_snapshots(observed_at, appid, game_name) VALUES (?, ?, ?)",
                (timestamp, int(appid), str(game_name or f"App {appid}")),
            )
            row = connection.execute(
                "SELECT * FROM activity_snapshots WHERE observed_at = ? AND appid = ? ORDER BY id DESC LIMIT 1",
                (timestamp, int(appid)),
            ).fetchone()
        return _public_snapshot(dict(row))

    def snapshots(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        limit = max(1, min(50000, int(limit)))
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM activity_snapshots ORDER BY observed_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        rows.reverse()
        return [_public_snapshot(dict(row)) for row in rows]

    def sessions(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        snapshots = self.snapshots()
        if not snapshots:
            return []
        derived: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for snapshot in snapshots:
            timestamp = snapshot["observed_at"]["timestamp"]
            if current is None:
                current = _new_session(snapshot)
                continue
            same_game = current["appid"] == snapshot["appid"]
            gap = timestamp - current["last_observed_at"]["timestamp"]
            if same_game and gap <= SESSION_GAP_SECONDS:
                current["last_observed_at"] = snapshot["observed_at"]
                current["observations"] += 1
                continue
            current["status"] = "closed_by_same_game_gap" if same_game else "closed_by_different_game_observation"
            derived.append(_finish_session(current))
            current = _new_session(snapshot)
        if current is not None:
            current["status"] = "open_or_unobserved_end"
            derived.append(_finish_session(current))
        derived.sort(key=lambda item: (item["start"]["timestamp"] or 0, item["appid"]))
        return derived[-max(1, min(5000, limit)) :]

    def close(self) -> None:
        if self._memory_connection is not None:
            with self._lock:
                self._memory_connection.close()
                self._memory_connection = None


def _new_session(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "appid": snapshot["appid"],
        "game_name": snapshot["game_name"],
        "start": snapshot["observed_at"],
        "last_observed_at": snapshot["observed_at"],
        "observations": 1,
    }


def _finish_session(session: dict[str, Any]) -> dict[str, Any]:
    start = session["start"]["timestamp"] or 0
    last = session["last_observed_at"]["timestamp"] or 0
    observed_span = max(0, last - start)
    return {
        "appid": session["appid"],
        "game_name": session["game_name"],
        "start": session["start"],
        "start_is_observed_boundary": True,
        "last_observed_at": session["last_observed_at"],
        "end_observed_at": None,
        "session_end": session["last_observed_at"] if session["status"] != "open_or_unobserved_end" else None,
        "session_end_kind": "last_observation_before_transition" if session["status"] != "open_or_unobserved_end" else "unknown",
        "observed_span_seconds": observed_span,
        "observed_span_minutes": round(observed_span / 60, 2),
        "estimated_duration_seconds": observed_span,
        "estimated_duration_minutes": round(observed_span / 60, 2),
        "observations": session["observations"],
        "status": session["status"],
        "end_time_is_not_known": True,
        "note": "Duration is only the span between MCP observations; unobserved time is not counted.",
    }


def _public_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "observed_at": unix_time_info(row.get("observed_at")),
        "appid": row.get("appid"),
        "game_name": row.get("game_name") or f"App {row.get('appid')}",
    }
