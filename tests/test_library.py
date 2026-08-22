from __future__ import annotations

from types import SimpleNamespace

import pytest

from errors import AppError
from services.library_service import LibraryService


def test_minutes_to_hours(runtime):
    game = runtime.library.owned_games()[0]
    assert game.playtime_forever == 11184
    assert game.total_hours == 186.4


def test_sort_playtime_and_paging(runtime):
    result = runtime.library.get_library(sort_by="playtime", order="desc", limit=3, offset=1)
    assert result["total"] == 20
    assert result["offset"] == 1
    assert result["has_more"] is True
    assert result["games"][0]["name"] == "Hades"


def test_sort_name(runtime):
    result = runtime.library.get_library(sort_by="name", order="asc", limit=3)
    assert [item["name"] for item in result["games"]] == ["Balatro", "Cities: Skylines", "Counter-Strike 2"]


def test_recent_games_backfill_last_played_from_library(runtime):
    runtime.steam.get_recent_games = lambda count: [{"appid": 646570, "name": "Slay the Spire", "playtime_2weeks": 10}]
    rows = runtime.library.recent_games(1)
    assert rows[0].rtime_last_played is not None
    assert rows[0].public_dict()["last_played"]["timestamp"] == runtime.library.owned_games()[0].rtime_last_played


def test_never_played_and_low_playtime(runtime):
    never = runtime.library.never_played(50)
    low = runtime.library.low_playtime(2, 50)
    assert len(never) == 4
    assert any(item["name"] == "The Binding of Isaac: Rebirth" for item in low)


def test_abandoned(runtime):
    rows = runtime.library.abandoned(min_hours=1, max_hours=20, inactive_days=180, count=30)
    assert any(item["name"] == "Portal" for item in rows)
    assert all(item["playtime_hours"] <= 20 for item in rows)


def test_empty_library():
    steam = SimpleNamespace(get_owned_games=lambda include_free_games=True: [], get_recent_games=lambda count: [])
    service = LibraryService(steam, None, None)
    assert service.get_library()["total"] == 0
    assert service.stats()["total_games"] == 0
    assert service.never_played() == []


def test_invalid_library_arguments(runtime):
    with pytest.raises(AppError):
        runtime.library.get_library(sort_by="bad")
