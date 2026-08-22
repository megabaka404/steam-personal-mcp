from __future__ import annotations


def test_new_releases_for_me_returns_scored_rows(runtime):
    result = runtime.p1.new_releases_for_me(days=3650, count=5)
    assert result["count"] <= 5
    assert all("score" in row and row["reasons"] and "release_date" in row for row in result["games"])
    owned = {game.appid for game in runtime.library.owned_games()}
    assert all(row["appid"] not in owned for row in result["games"])


def test_friend_activity_summary_distinguishes_current_and_shared_data(runtime):
    result = runtime.friends.activity_summary()
    assert result["available"] is True
    assert result["online_count"] == 2
    assert result["currently_playing_count"] == 2
    assert result["data_availability"]["friend_current_games"] == "available"
    assert result["shared_games"]


def test_library_value_stats_is_explicitly_estimated(runtime):
    result = runtime.p1.library_value_stats()
    assert result["available"] is True
    assert result["games_scanned"] == 20
    assert result["priced_games"] > 0
    assert result["total_playtime_hours"] > 0
    assert "actual purchase prices" in result["estimate_note"]


def test_missing_dlc_for_owned_games(runtime):
    result = runtime.p1.missing_dlc_for_owned_games(count=10)
    assert result["available"] is True
    assert any(row["parent_appid"] == 646570 for row in result["dlc"])
    discounted = runtime.p1.missing_dlc_for_owned_games(only_discounted=True, min_discount=70, count=10)
    assert all(row["discount_percent"] >= 70 for row in discounted["dlc"])


def test_wishlist_release_watch_persists_transition(runtime):
    first = runtime.p1.wishlist_release_watch()
    assert first["available"] is True
    assert first["count"] == 3
    second = runtime.p1.wishlist_release_watch()
    assert all(row["transition"] is None for row in second["items"])
