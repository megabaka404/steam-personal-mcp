from __future__ import annotations

from activity_history import ActivityHistoryStore
from services.p2_service import P2Service


def test_activity_snapshots_merge_into_observed_sessions(tmp_path):
    history = ActivityHistoryStore(tmp_path / "activity.sqlite3")
    history.record_snapshot(appid=1, game_name="One", observed_at=1760000000)
    history.record_snapshot(appid=1, game_name="One", observed_at=1760000600)
    history.record_snapshot(appid=2, game_name="Two", observed_at=1760001200)
    history.record_snapshot(appid=2, game_name="Two", observed_at=1760005000)

    sessions = history.sessions()
    assert len(sessions) == 3
    assert sessions[0]["appid"] == 1
    assert sessions[0]["observed_span_seconds"] == 600
    assert sessions[0]["status"] == "closed_by_different_game_observation"
    assert sessions[1]["appid"] == 2
    assert sessions[1]["status"] == "closed_by_same_game_gap"
    assert sessions[1]["end_observed_at"] is None
    assert sessions[1]["estimated_duration_seconds"] == 0
    assert sessions[1]["end_time_is_not_known"] is True
    assert sessions[2]["status"] == "open_or_unobserved_end"
    history.close()


def test_profile_observation_is_persisted_and_p2_tools_are_explicit(runtime):
    profile = runtime.activity.profile()
    assert profile["current_game"]["appid"] == 646570

    snapshot = runtime.activity.record_play_session_snapshot()
    assert snapshot["recorded"] is True
    assert snapshot["source"] == "MCP-observed Steam profile snapshot"

    history = runtime.p2.play_session_history(days=3650, count=10)
    assert history["available"] is True
    assert history["sessions"]
    assert history["source"] == "MCP-observed Steam profile snapshots"


def test_year_in_review_reports_observation_coverage(tmp_path):
    history = ActivityHistoryStore(tmp_path / "activity.sqlite3")
    history.record_snapshot(appid=10, game_name="First", observed_at=1760000000)
    history.record_snapshot(appid=10, game_name="First", observed_at=1760000600)
    history.record_snapshot(appid=11, game_name="Second", observed_at=1760600000)
    result = P2Service(history).year_in_review(year=2025)

    assert result["available"] is True
    assert result["most_played"]["appid"] == 10
    assert result["total_observed_playtime_seconds"] == 600
    assert result["data_coverage"]["snapshot_count"] == 3
    assert result["data_coverage"]["is_official_steam_year_in_review"] is False
    assert result["new_games_started"]
    assert result["current_api_context"]["available"] is False
    history.close()
