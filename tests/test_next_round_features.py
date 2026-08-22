from __future__ import annotations

from pathlib import Path

import pytest

from game_history import GameObservationStore
from services.local_steam_service import LocalSteamService


def test_game_snapshot_is_single_sourced_and_explicit(runtime):
    snapshot = runtime.game_intel.snapshot(appid=646570, include_local=False)
    assert snapshot["available"] is True
    assert snapshot["appid"] == 646570
    assert snapshot["achievements"]["available"] is True
    assert snapshot["deck_compatibility"]["status"] == "verified"
    assert snapshot["workshop_support"]["workshop_supported"] is True
    assert snapshot["review_trend"]["status"] == "insufficient_history"
    assert snapshot["sources"]["history"] == "MCP-observed history"
    assert "Steam Deck compatibility" not in snapshot["missing_data"]


def test_library_overlap_returns_reasons_and_playtime(runtime):
    result = runtime.game_intel.library_overlap(appid=1145350)
    assert result["available"] is True
    assert result["closest_owned_games"]
    assert result["owned_similar_count"] >= 1
    assert all(row["similarity_reasons"] for row in result["closest_owned_games"])
    assert all("playtime_hours" in row for row in result["closest_owned_games"])


def test_game_history_distinguishes_observed_correlation_from_causality(tmp_path):
    history = GameObservationStore(tmp_path / "game-history.sqlite3")
    history.observe(
        appid=10,
        name="Game",
        snapshot={"current_players": 100, "recent_review_pct": 90, "review_count": 1000, "recent_review_count": 10, "build_identifier": "a"},
        observed_at=1760000000,
    )
    history.observe(
        appid=10,
        name="Game",
        snapshot={"current_players": 20, "recent_review_pct": 70, "review_count": 1100, "recent_review_count": 20, "build_identifier": "b"},
        observed_at=1760000600,
    )
    result = history.changes(10)
    assert result["available"] is True
    assert result["changes"]["current_players"]["delta"] == -80
    assert "do not prove" in result["interpretation"].casefold()
    history.close()


def test_buy_advice_is_explainable_not_opaque_score(runtime):
    result = runtime.game_intel.buy_advice(appid=1627720)
    assert result["verdict"] in {"buy", "wait", "skip"}
    assert result["confidence"] in {"low", "medium", "high"}
    assert result["positive_factors"] or result["negative_factors"] or result["uncertainties"]
    assert "purchase_score" not in result


def test_local_scan_is_read_only_and_windows_compatdata_is_explicit(tmp_path):
    root = Path(tmp_path)
    steamapps = root / "steamapps"
    (steamapps / "common" / "Installed").mkdir(parents=True)
    (steamapps / "shadercache" / "999").mkdir(parents=True)
    (steamapps / "shadercache" / "999" / "cache.bin").write_bytes(b"cache")
    (steamapps / "appmanifest_10.acf").write_text(
        '"appid" "10"\n"name" "Installed"\n"installdir" "Installed"\n"SizeOnDisk" "123"\n',
        encoding="utf-8",
    )
    service = LocalSteamService(roots=[root], platform_name="Windows")
    scan = service.scan()
    assert scan["available"] is True
    assert scan["installed_games"][0]["size_on_disk"] == 123
    assert scan["installed_games"][0]["compatdata_status"] == "not_applicable"
    assert scan["residuals"][0]["appid"] == 999
    residual_path = Path(scan["residuals"][0]["path"])
    assert residual_path.exists()
    preview = service.storage_preview(appids=[999], targets=["shadercache"])
    assert preview["will_delete"] is False
    with pytest.raises(Exception):
        service.storage_clean(appids=[999], targets=["shadercache"], confirm=False)
    assert residual_path.exists()
    cleaned = service.storage_clean(appids=[999], targets=["shadercache"], confirm=True)
    assert cleaned["items"][0]["cleaned"] is True
    assert not residual_path.exists()
