from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from models.account import unix_time_info
from models.store import minor_to_major


class GameObservationStore:
    """SQLite history observed by this MCP; it never claims to be Steam history."""

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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appid INTEGER NOT NULL,
                    name TEXT,
                    observed_at INTEGER NOT NULL,
                    current_players INTEGER,
                    overall_review_pct INTEGER,
                    recent_review_pct INTEGER,
                    review_count INTEGER,
                    recent_review_count INTEGER,
                    price_minor INTEGER,
                    original_price_minor INTEGER,
                    currency TEXT,
                    discount_percent INTEGER,
                    deck_status TEXT,
                    build_identifier TEXT,
                    source TEXT NOT NULL DEFAULT 'MCP-observed history'
                );
                CREATE INDEX IF NOT EXISTS idx_game_observations_appid_time
                    ON game_observations(appid, observed_at DESC);
                """
            )

    def observe(self, *, appid: int, name: str | None, snapshot: dict[str, Any], observed_at: int | None = None) -> dict[str, Any]:
        timestamp = int(observed_at or time.time())
        price = snapshot.get("price") or {}
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO game_observations
                    (appid, name, observed_at, current_players, overall_review_pct,
                     recent_review_pct, review_count, recent_review_count, price_minor,
                     original_price_minor, currency, discount_percent, deck_status,
                     build_identifier, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(appid),
                    name,
                    timestamp,
                    _int_or_none(snapshot.get("current_players")),
                    _int_or_none(snapshot.get("overall_review_pct")),
                    _int_or_none(snapshot.get("recent_review_pct")),
                    _int_or_none(snapshot.get("review_count")),
                    _int_or_none(snapshot.get("recent_review_count")),
                    _int_or_none(price.get("price_minor")),
                    _int_or_none(price.get("original_price_minor")),
                    price.get("currency"),
                    _int_or_none(price.get("discount_percent")) or 0,
                    snapshot.get("deck_status"),
                    snapshot.get("build_identifier"),
                    "MCP-observed history",
                ),
            )
            row_id = cursor.lastrowid
        return {
            "id": row_id,
            "appid": int(appid),
            "observed_at": unix_time_info(timestamp),
            "source": "MCP-observed history",
        }

    def records(self, appid: int, *, limit: int = 5000) -> list[dict[str, Any]]:
        limit = max(1, min(10000, int(limit)))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM game_observations WHERE appid = ? ORDER BY observed_at ASC, id ASC LIMIT ?",
                (int(appid), limit),
            ).fetchall()
        return [_public_record(dict(row)) for row in rows]

    def changes(self, appid: int, *, limit: int = 5000) -> dict[str, Any]:
        records = self.records(appid, limit=limit)
        if not records:
            return {
                "available": False,
                "reason": "No MCP-observed game history is available for this AppID.",
                "source": "MCP-observed history",
                "records": [],
            }
        latest = records[-1]
        previous = records[-2] if len(records) >= 2 else None
        changed = _changes(previous, latest) if previous else {}
        return {
            "available": True,
            "appid": int(appid),
            "latest": latest,
            "previous": previous,
            "changes": changed,
            "records": records,
            "source": "MCP-observed history",
            "interpretation": "Changes are observations. They do not prove that a particular update caused a review, player, or price change.",
        }

    def close(self) -> None:
        return None


def _public_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "appid": row.get("appid"),
        "name": row.get("name") or f"App {row.get('appid')}",
        "observed_at": unix_time_info(row.get("observed_at")),
        "current_players": row.get("current_players"),
        "overall_review_pct": row.get("overall_review_pct"),
        "recent_review_pct": row.get("recent_review_pct"),
        "review_count": row.get("review_count"),
        "recent_review_count": row.get("recent_review_count"),
        "price": {
            "currency": row.get("currency"),
            "price_minor": row.get("price_minor"),
            "price": minor_to_major(row.get("price_minor"), row.get("currency")),
            "original_price_minor": row.get("original_price_minor"),
            "original_price": minor_to_major(row.get("original_price_minor"), row.get("currency")),
            "discount_percent": row.get("discount_percent") or 0,
        },
        "deck_status": row.get("deck_status"),
        "build_identifier": row.get("build_identifier"),
        "source": row.get("source") or "MCP-observed history",
    }


def _changes(previous: dict[str, Any] | None, latest: dict[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {}
    changes: dict[str, Any] = {}
    fields = (
        "current_players",
        "overall_review_pct",
        "recent_review_pct",
        "review_count",
        "recent_review_count",
        "deck_status",
        "build_identifier",
    )
    for field in fields:
        old = previous.get(field)
        new = latest.get(field)
        if old is not None and new is not None and old != new:
            changes[field] = {"before": old, "after": new, "delta": _delta(old, new)}
        elif old != new and (old is not None or new is not None):
            changes[field] = {"before": old, "after": new, "delta": None}
    old_price = (previous.get("price") or {}).get("price_minor")
    new_price = (latest.get("price") or {}).get("price_minor")
    if old_price != new_price and (old_price is not None or new_price is not None):
        changes["price_minor"] = {"before": old_price, "after": new_price, "delta": _delta(old_price, new_price)}
    return changes


def _delta(old: Any, new: Any) -> int | float | None:
    try:
        return new - old
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
