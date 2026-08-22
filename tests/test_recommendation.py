from __future__ import annotations


def test_backlog_scoring(runtime):
    rows = runtime.recommendations.backlog(10)
    assert rows
    assert rows[0]["playtime_hours"] == 0.0
    assert "reasons" in rows[0]


def test_return_to_scoring(runtime):
    rows = runtime.recommendations.return_to(10, min_hours=10)
    assert rows
    assert all(item["inactive_days"] >= 30 for item in rows)


def test_owned_exclusion(runtime):
    rows = runtime.recommendations.pick(count=50, exclude_appids=[646570], randomize=False)
    assert all(item["appid"] != 646570 for item in rows)


def test_deterministic_mode(runtime):
    first = runtime.recommendations.recommend(5, "balanced")
    second = runtime.recommendations.recommend(5, "balanced")
    assert [item["appid"] for item in first] == [item["appid"] for item in second]


def test_randomized_mode_shape(runtime):
    rows = runtime.recommendations.pick(count=3, randomize=True)
    assert len(rows) == 3
    assert len({item["appid"] for item in rows}) == 3
