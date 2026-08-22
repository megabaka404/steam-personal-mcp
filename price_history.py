from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from models.account import unix_time_info
from models.store import minor_to_major


class PriceHistoryStore:
    """Small persistent store for prices observed by this MCP instance."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        target = str(self.path)
        connection = sqlite3.connect(target, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS price_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appid INTEGER NOT NULL,
                    name TEXT,
                    currency TEXT,
                    original_price_minor INTEGER,
                    current_price_minor INTEGER NOT NULL,
                    discount_percent INTEGER NOT NULL DEFAULT 0,
                    first_observed_at INTEGER NOT NULL,
                    last_observed_at INTEGER NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(appid, currency, original_price_minor, current_price_minor, discount_percent)
                );
                CREATE INDEX IF NOT EXISTS idx_price_observations_appid
                    ON price_observations(appid, last_observed_at DESC);
                CREATE TABLE IF NOT EXISTS release_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appid INTEGER NOT NULL,
                    name TEXT,
                    release_date TEXT,
                    coming_soon INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    first_observed_at INTEGER NOT NULL,
                    last_observed_at INTEGER NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(appid, release_date, coming_soon, status)
                );
                CREATE INDEX IF NOT EXISTS idx_release_observations_appid
                    ON release_observations(appid, last_observed_at DESC);
                """
            )

    def observe(self, *, appid: int, name: str | None, price: dict[str, Any] | None, observed_at: int | None = None) -> bool:
        if not price or price.get("price_minor") is None:
            return False
        try:
            appid = int(appid)
            current = int(price["price_minor"])
        except (KeyError, TypeError, ValueError):
            return False
        if appid <= 0:
            return False
        timestamp = int(observed_at or time.time())
        original = _int_or_none(price.get("original_price_minor"))
        discount = _int_or_none(price.get("discount_percent")) or 0
        currency = str(price.get("currency") or "")
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO price_observations
                    (appid, name, currency, original_price_minor, current_price_minor,
                     discount_percent, first_observed_at, last_observed_at, observation_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(appid, currency, original_price_minor, current_price_minor, discount_percent)
                DO UPDATE SET
                    name = excluded.name,
                    last_observed_at = excluded.last_observed_at,
                    observation_count = price_observations.observation_count + 1
                """,
                (appid, name, currency, original, current, discount, timestamp, timestamp),
            )
        return True

    def records(self, appid: int | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        limit = max(1, min(5000, int(limit)))
        query = "SELECT * FROM price_observations"
        params: tuple[Any, ...] = ()
        if appid is not None:
            query += " WHERE appid = ?"
            params = (int(appid),)
        query += " ORDER BY first_observed_at ASC, id ASC LIMIT ?"
        params += (limit,)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_public_record(dict(row)) for row in rows]

    def summary(self, appid: int | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for record in self.records(appid=appid, limit=limit):
            grouped.setdefault(int(record["appid"]), []).append(record)
        result = []
        for current_appid, records in grouped.items():
            latest = max(records, key=lambda item: (item["last_observed_at"]["timestamp"] or 0, item["first_observed_at"]["timestamp"] or 0))
            currency = latest.get("currency")
            same_currency = [item for item in records if item.get("currency") == currency]
            low = min(same_currency, key=lambda item: item["current_price_minor"])
            chronological = sorted(records, key=lambda item: (item["last_observed_at"]["timestamp"] or 0, item["first_observed_at"]["timestamp"] or 0), reverse=True)
            previous = chronological[1] if len(chronological) > 1 else None
            result.append(
                {
                    "appid": current_appid,
                    "name": latest.get("name") or f"App {current_appid}",
                    "currency": currency,
                    "current_price": latest.get("current_price"),
                    "current_price_minor": latest.get("current_price_minor"),
                    "discount_percent": latest.get("discount_percent", 0),
                    "historical_low": low.get("current_price"),
                    "historical_low_minor": low.get("current_price_minor"),
                    "historical_low_date": low.get("first_observed_at"),
                    "is_local_historical_low": latest.get("current_price_minor") == low.get("current_price_minor"),
                    "difference_from_historical_low": _major_difference(latest, low),
                    "last_observed_at": latest.get("last_observed_at"),
                    "previous_price": previous.get("current_price") if previous else None,
                    "previous_observed_at": previous.get("last_observed_at") if previous else None,
                    "cheaper_than_previous_observation": bool(previous and latest.get("current_price_minor") < previous.get("current_price_minor")),
                    "last_price_drop_at": latest.get("last_observed_at") if previous and latest.get("current_price_minor") < previous.get("current_price_minor") else None,
                    "record_count": len(records),
                    "records": records,
                }
            )
        result.sort(key=lambda item: (item["name"] or "").casefold())
        return result

    def close(self) -> None:
        return None

    def observe_release(self, *, appid: int, name: str | None, release_date: str | None, coming_soon: bool, status: str, observed_at: int | None = None) -> dict[str, Any] | None:
        timestamp = int(observed_at or time.time())
        with self._lock, self._connect() as connection:
            previous = connection.execute(
                "SELECT * FROM release_observations WHERE appid = ? ORDER BY last_observed_at DESC, id DESC LIMIT 1",
                (int(appid),),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO release_observations
                    (appid, name, release_date, coming_soon, status, first_observed_at, last_observed_at, observation_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(appid, release_date, coming_soon, status)
                DO UPDATE SET
                    name = excluded.name,
                    last_observed_at = excluded.last_observed_at,
                    observation_count = release_observations.observation_count + 1
                """,
                (int(appid), name, release_date, int(bool(coming_soon)), status, timestamp, timestamp),
            )
        return _public_release_record(dict(previous)) if previous else None

    def release_summaries(self, appid: int | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        limit = max(1, min(5000, int(limit)))
        query = "SELECT * FROM release_observations"
        params: tuple[Any, ...] = ()
        if appid is not None:
            query += " WHERE appid = ?"
            params = (int(appid),)
        query += " ORDER BY first_observed_at ASC, id ASC LIMIT ?"
        params += (limit,)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(int(row["appid"]), []).append(_public_release_record(dict(row)))
        result = []
        for current_appid, records in grouped.items():
            ordered = sorted(records, key=lambda item: (item["last_observed_at"]["timestamp"] or 0, item["first_observed_at"]["timestamp"] or 0), reverse=True)
            latest = ordered[0]
            previous = ordered[1] if len(ordered) > 1 else None
            result.append({
                "appid": current_appid,
                "name": latest["name"],
                "release_date": latest["release_date"],
                "coming_soon": latest["coming_soon"],
                "status": latest["status"],
                "previous_status": previous["status"] if previous else None,
                "release_changed": bool(previous and (previous["release_date"], previous["coming_soon"], previous["status"]) != (latest["release_date"], latest["coming_soon"], latest["status"])),
                "coming_soon_changed": bool(previous and previous["coming_soon"] != latest["coming_soon"]),
                "last_observed_at": latest["last_observed_at"],
                "record_count": len(records),
                "records": records,
            })
        result.sort(key=lambda item: (item["name"] or "").casefold())
        return result


def _public_record(row: dict[str, Any]) -> dict[str, Any]:
    currency = row.get("currency")
    return {
        "appid": row["appid"],
        "name": row.get("name") or f"App {row['appid']}",
        "currency": currency,
        "original_price_minor": row.get("original_price_minor"),
        "original_price": minor_to_major(row.get("original_price_minor"), currency),
        "current_price_minor": row.get("current_price_minor"),
        "current_price": minor_to_major(row.get("current_price_minor"), currency),
        "discount_percent": row.get("discount_percent", 0),
        "first_observed_at": unix_time_info(row.get("first_observed_at")),
        "last_observed_at": unix_time_info(row.get("last_observed_at")),
        "observation_count": row.get("observation_count", 1),
    }


def _major_difference(latest: dict[str, Any], low: dict[str, Any]) -> float | None:
    current = latest.get("current_price")
    historical_low = low.get("current_price")
    if current is None or historical_low is None:
        return None
    return round(float(current) - float(historical_low), 2)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _public_release_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "appid": row["appid"],
        "name": row.get("name") or f"App {row['appid']}",
        "release_date": row.get("release_date"),
        "coming_soon": bool(row.get("coming_soon")),
        "status": row.get("status") or "unknown",
        "first_observed_at": unix_time_info(row.get("first_observed_at")),
        "last_observed_at": unix_time_info(row.get("last_observed_at")),
        "observation_count": row.get("observation_count", 1),
    }
