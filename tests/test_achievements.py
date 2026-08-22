from __future__ import annotations

from types import SimpleNamespace

from errors import AppError
from models.account import unix_time_info
from services.achievement_service import AchievementService


def test_completion_summary(runtime):
    summary = runtime.achievements.summary(appid=646570)
    assert summary["available"] is True
    assert summary["total_achievements"] == 20
    assert summary["unlocked"] == 17
    assert summary["completion_percent"] == 85.0


def test_nested_playerstats_are_merged_with_schema(runtime):
    result = runtime.achievements.get_achievements(appid=646570)
    assert result["available"] is True
    assert result["total_achievements"] == 20
    assert result["unlocked"] == 17
    unlocked = [item for item in result["achievements"] if item["achieved"]]
    assert unlocked
    assert unlocked[0]["unlock_time"]["timestamp"] > 0


def test_zero_achievements_is_unavailable(runtime):
    result = runtime.achievements.get_achievements(appid=8930)
    assert result["available"] is False


def test_malformed_timestamp_is_safe():
    assert unix_time_info("not-a-timestamp") is None
    assert unix_time_info(-4) is None


def test_unavailable_achievements():
    class PrivateSteam:
        def get_achievements(self, appid):
            raise AppError("PROFILE_PRIVATE", "private")

        def get_achievement_schema(self, appid):
            raise AssertionError("schema should not be requested after failure")

    service = AchievementService(PrivateSteam(), SimpleNamespace(), SimpleNamespace(resolve=lambda **kwargs: SimpleNamespace(appid=1, name="Private")))
    result = service.get_achievements(appid=1)
    assert result["available"] is False
    assert "unavailable" in result["reason"].lower()


def test_player_status_failure_is_not_all_locked():
    class FailedSteam:
        def get_achievements(self, appid):
            return {"playerstats": {"success": False, "error": "Profile is private."}}

        def get_achievement_schema(self, appid):
            raise AssertionError("schema should not be requested after player status failure")

    service = AchievementService(FailedSteam(), SimpleNamespace(), SimpleNamespace(resolve=lambda **kwargs: SimpleNamespace(appid=1, name="Private")))
    result = service.get_achievements(appid=1)
    assert result["available"] is False
    assert result["reason_code"] == "PROFILE_PRIVATE"
    assert "total_achievements" not in result


def test_recent_achievements_is_bounded(runtime):
    result = runtime.achievements.recent_achievements(days=30, count=5)
    assert result["scanned_recent_games"] <= 30
    assert result["count"] <= 5
