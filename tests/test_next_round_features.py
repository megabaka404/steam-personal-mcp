from __future__ import annotations

from pathlib import Path

import pytest

from cache.memory_cache import MemoryTTLCache
from clients.store_client import StoreClient
from config import Settings
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


def test_local_scan_uses_global_installed_set_across_libraries(tmp_path):
    c_root = Path(tmp_path) / "C-Steam"
    e_root = Path(tmp_path) / "E-SteamLibrary"
    (c_root / "steamapps" / "shadercache" / "123").mkdir(parents=True)
    (c_root / "steamapps" / "shadercache" / "123" / "cache.bin").write_bytes(b"cache")
    (e_root / "steamapps" / "common" / "Balatro").mkdir(parents=True)
    (e_root / "steamapps" / "appmanifest_123.acf").parent.mkdir(parents=True, exist_ok=True)
    (e_root / "steamapps" / "appmanifest_123.acf").write_text(
        '"appid" "123"\n"name" "Balatro"\n"installdir" "Balatro"\n"SizeOnDisk" "456"\n',
        encoding="utf-8",
    )
    service = LocalSteamService(roots=[c_root, e_root], platform_name="Windows")
    scan = service.scan()
    assert any(game["appid"] == 123 and str(e_root) in game["install_path"] for game in scan["installed_games"])
    assert not any(item["appid"] == 123 for item in scan["residuals"])
    preview = service.storage_preview(appids=[123], targets=["shadercache"])
    assert preview["preview"] == []
    cleaned = service.storage_clean(appids=[123], targets=["shadercache"], confirm=True)
    assert cleaned["items"] == []
    assert (c_root / "steamapps" / "shadercache" / "123").exists()


def test_next_action_explicitly_reports_exclude_owned_is_ignored():
    from server import build_server

    mcp, runtime = build_server(mock=True)
    result = mcp._tool_manager._tools["recommendations"].fn(action="next", exclude_owned=True, count=3)
    assert result["success"] is True
    assert "owned library" in result["parameter_notes"]["exclude_owned"]
    owned = {game.appid for game in runtime.library.owned_games()}
    assert all(item["appid"] in owned for item in result["games"])
    runtime.close()


class _ReviewHTTP:
    def __init__(self) -> None:
        self.filters: list[str] = []

    def get_json(self, _url, *, params, **_kwargs):
        self.filters.append(params["filter"])
        return {
            "query_summary": {
                "total_reviews": 159504,
                "total_positive": 156314,
                "review_score": 8,
            }
        }


def test_recent_review_summary_does_not_copy_lifetime_summary():
    http = _ReviewHTTP()
    client = StoreClient(
        Settings(api_key=None, steam_id=None, mock=True),
        MemoryTTLCache(),
        http=http,
    )
    result = client.review_summary(123)
    assert result is not None
    assert http.filters == ["summary", "recent"]
    assert result["review_count"] == 159504
    assert result["recent_review_count"] is None
    assert result["recent_review_percentage"] is None
    assert result["recent_review_available"] is False
    assert "independently verifiable" in result["recent_review_reason"]
