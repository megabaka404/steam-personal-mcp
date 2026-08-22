from __future__ import annotations

from price_history import PriceHistoryStore


def test_store_recommendation_is_deterministic_and_excludes_owned(runtime):
    first = runtime.store_recommendations.recommend_store_for_me(count=5)
    second = runtime.store_recommendations.recommend_store_for_me(count=5)
    assert first["games"] == second["games"]
    owned = {game.appid for game in runtime.library.owned_games()}
    assert all(item["appid"] not in owned for item in first["games"])
    assert all("score" in item and "reasons" in item for item in first["games"])


def test_similar_games_has_explainable_scores(runtime):
    result = runtime.store_recommendations.find_similar_games(game="Slay the Spire", count=10)
    assert result["source_game"]["appid"] == 646570
    assert all("similarity_score" in item and item["similarity_reasons"] for item in result["games"])
    assert all(item["appid"] != 646570 for item in result["games"])


def test_price_history_deduplicates_and_reports_drop(tmp_path):
    history = PriceHistoryStore(tmp_path / "prices.sqlite3")
    history.observe(appid=1, name="Example", price={"currency": "USD", "original_price_minor": 1000, "price_minor": 800, "discount_percent": 20}, observed_at=100)
    history.observe(appid=1, name="Example", price={"currency": "USD", "original_price_minor": 1000, "price_minor": 800, "discount_percent": 20}, observed_at=200)
    history.observe(appid=1, name="Example", price={"currency": "USD", "original_price_minor": 1000, "price_minor": 500, "discount_percent": 50}, observed_at=300)
    summary = history.summary(1)[0]
    assert summary["record_count"] == 2
    assert summary["historical_low"] == 5.0
    assert summary["is_local_historical_low"] is True
    assert summary["cheaper_than_previous_observation"] is True
    assert summary["records"][0]["observation_count"] == 2
    history.close()


def test_existing_wishlist_path_records_observation(runtime):
    result = runtime.store.wishlist(limit=3)
    assert result["available"] is True
    history = runtime.price_history.summary()
    assert history
    assert all(item["record_count"] >= 1 for item in history)


def test_release_history_detects_status_transition(tmp_path):
    history = PriceHistoryStore(tmp_path / "releases.sqlite3")
    assert history.observe_release(appid=7, name="Future", release_date="2026-09-01", coming_soon=True, status="upcoming", observed_at=100) is None
    previous = history.observe_release(appid=7, name="Future", release_date="2026-09-01", coming_soon=False, status="released", observed_at=200)
    assert previous["status"] == "upcoming"
    summary = history.release_summaries(7)[0]
    assert summary["status"] == "released"
    assert summary["coming_soon_changed"] is True
    assert summary["release_changed"] is True
    history.close()
