from __future__ import annotations

from models.game import GameRecord
from models.store import StoreGame, parse_price
from services.recommendation_features import compare_features, extract_features
from services.store_recommendation_service import _candidate_score


def test_generic_action_is_weak_and_specific_feature_wins():
    source = extract_features({"genres": [{"description": "Action"}], "categories": [{"description": "Roguelike"}]})
    generic_action = extract_features({"genres": [{"description": "Action"}]})
    specific_roguelike = extract_features({"genres": [{"description": "Action"}], "categories": [{"description": "Roguelike"}]})

    generic_score, generic_reasons = compare_features(source, generic_action)
    specific_score, specific_reasons = compare_features(source, specific_roguelike)

    assert generic_score < 10
    assert specific_score > generic_score
    assert any("specific feature" in reason for reason in specific_reasons)
    assert any("weak evidence" in reason for reason in generic_reasons)


def test_wishlist_and_discount_are_retrieval_signals_not_fit_confidence():
    no_evidence = _candidate_score(0, wishlisted=False, discount=0, review_percentage=None)
    retrieval_signals_only = _candidate_score(0, wishlisted=True, discount=100, review_percentage=100)

    assert no_evidence == 0
    assert retrieval_signals_only > no_evidence
    assert retrieval_signals_only <= 30


def test_candidate_context_exposes_metadata_and_missing_fields(runtime):
    item = StoreGame(
        appid=999001,
        name="Metadata Candidate",
        type="game",
        price=parse_price({"currency": "USD", "initial": 2000, "final": 1000}),
        genres=[{"description": "Action"}],
        categories=[
            {"description": "Single-player"},
            {"description": "Full Controller Support"},
            {"description": "Keyboard & Mouse"},
        ],
        review_percentage=90,
        review_count=100,
    )
    detail = {
        "name": "Metadata Candidate",
        "type": "game",
        "genres": [{"description": "Action"}],
        "categories": item.categories,
        "tags": {"Roguelike": 100, "Deckbuilder": 80},
        "release_date": {"date": "2026-01-01"},
    }
    context = runtime.store_recommendations._candidate_context(item, detail, [], None, ["test fixture"])

    assert context["tags"] == ["Deckbuilder", "Roguelike"]
    assert context["singleplayer"] is True
    assert context["multiplayer"] is False
    assert context["controller_support"] == "full"
    assert context["keyboard_mouse_support"] is True
    assert context["discount_percent"] == 50
    assert context["candidate_score"] > 0
    assert "tags not exposed by this Store response" not in context["missing_data"]

    missing = runtime.store_recommendations._candidate_context(StoreGame(appid=999002, name="Missing"), {}, [], None, [])
    assert missing["candidate_score"] == 0
    assert missing["missing_data"]


def test_recommendation_uses_candidate_score_and_excludes_owned(runtime):
    result = runtime.store_recommendations.recommend_store_for_me(count=999)
    owned = {game.appid for game in runtime.library.owned_games()}

    assert 1 <= len(result["games"]) <= 50
    assert result["interpretation"].startswith("Candidates and evidence only")
    assert all(item["appid"] not in owned for item in result["games"])
    assert all(item["candidate_score"] == item["score"] for item in result["games"])
    assert all(item["score_deprecated"] is True for item in result["games"])
    assert all("candidate_reasons" in item and "potential_mismatches" in item and "evidence" in item for item in result["games"])


def test_recommendation_excludes_wishlist_from_featured_and_search_candidates(runtime):
    wishlist = {int(item["appid"]) for item in runtime.steam.get_wishlist()}
    raw_candidates = runtime.store_recommendations._candidate_pool(["Action"], set(), include_wishlist=False)

    # This proves the fixture can reintroduce wishlist games through a non-wishlist source.
    assert wishlist.intersection(raw_candidates)

    result = runtime.store_recommendations.recommend_store_for_me(count=50, include_wishlist=False)
    included_result = runtime.store_recommendations.recommend_store_for_me(count=50, include_wishlist=True)

    assert result["wishlist_filter"] == {"include_wishlist": False, "available": True, "applied": True}
    assert not wishlist.intersection({int(item["appid"]) for item in result["games"]})
    assert wishlist.intersection({int(item["appid"]) for item in included_result["games"]})


def test_recommendation_count_boundaries_and_deterministic_order(runtime):
    first = runtime.store_recommendations.recommend_store_for_me(count=5)
    second = runtime.store_recommendations.recommend_store_for_me(count=5)
    minimum = runtime.store_recommendations.recommend_store_for_me(count=0)

    assert first["games"] == second["games"]
    assert len(first["games"]) <= 5
    assert len(minimum["games"]) <= 1


def test_new_releases_uses_the_same_candidate_evidence(runtime):
    result = runtime.p1.new_releases_for_me(days=3650, count=5)

    assert result["interpretation"].startswith("Candidates and evidence only")
    assert all("candidate_score" in row for row in result["games"])
    assert all("candidate_reasons" in row and "evidence" in row and "potential_mismatches" in row for row in result["games"])
    assert all(row["score"] == row["candidate_score"] for row in result["games"])
