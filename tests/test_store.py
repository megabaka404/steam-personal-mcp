from __future__ import annotations

from models.store import minor_to_major, normalize_store_type, parse_price


def test_price_parsing_and_currency():
    price = parse_price({"currency": "USD", "initial": 1999, "final": 999, "discount_percent": 50})
    assert price is not None
    assert price.public_dict()["price"] == 9.99
    assert price.public_dict()["price_minor"] == 999
    assert minor_to_major(990, "JPY") == 990


def test_free_and_no_price():
    assert parse_price(None) is None
    free = parse_price({"currency": "USD", "initial": 0, "final": 0, "discount_percent": 0})
    assert free.public_dict()["price"] == 0.0


def test_search_price_computes_discount_when_endpoint_omits_it():
    price = parse_price({"currency": "USD", "initial": 3999, "final": 1239})
    assert price is not None
    assert price.public_dict()["original_price"] == 39.99
    assert price.public_dict()["price"] == 12.39
    assert price.public_dict()["discount_percent"] == 69
    assert parse_price({"currency": "USD", "initial": 3999, "final": 1239, "discount_percent": 0}).discount_percent == 69


def test_store_type_enum_is_normalized_safely():
    assert normalize_store_type(0) == "game"
    assert normalize_store_type(1) == "dlc"
    assert normalize_store_type(999) == "unknown"


def test_featured_integer_type_and_sales_discount(runtime):
    runtime.store_client.featured_items = lambda: [{"id": 999001, "type": 0, "name": "Featured", "currency": "USD", "original_price": 3999, "final_price": 1239, "discount_percent": 69}]
    featured = runtime.store.specials(count=5, min_discount=1)
    assert featured[0]["type"] == "game"
    assert featured[0]["price"]["discount_percent"] == 69

    runtime.store_client.search = lambda query, count: [{"id": 999002, "type": 0, "name": "Darkest Dungeon II", "price": {"currency": "USD", "initial": 3999, "final": 1239}}]
    sales = runtime.store.search_sales(query="Darkest Dungeon", min_discount=1)
    assert len(sales) == 1
    assert sales[0]["price"]["discount_percent"] == 69


def test_reviews_are_enrichment_and_dlc_uses_parent_name(runtime):
    search = runtime.store.search_store("Hades", count=1)
    assert search["games"][0]["review_percentage"] is not None
    assert search["games"][0]["review_count"] is not None
    assert runtime.store.get_game(appid=646570)["review_percentage"] == 96
    assert runtime.store.dlc(appid=646570)["game_name"] == "Slay the Spire"


def test_specials_discount_and_price_filters(runtime):
    rows = runtime.store.specials(count=50, min_discount=70, max_price=20)
    assert rows
    assert all(item["price"]["discount_percent"] >= 70 for item in rows)
    assert all(item["price"]["price"] <= 20 for item in rows)


def test_sales_genre_filter(runtime):
    rows = runtime.store.search_sales(query="Hades", min_discount=20, genres=["Roguelike"], count=10)
    assert rows
    assert all("Roguelike" in {genre["description"] for genre in (item.get("genres") or [])} for item in rows)


def test_wishlist_sales(runtime):
    result = runtime.store.wishlist_sales(min_discount=50)
    assert result["available"] is True
    assert all(item["price"]["discount_percent"] >= 50 for item in result["items"])
