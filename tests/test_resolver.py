from __future__ import annotations

import pytest

from errors import AppError
from resolver.game_resolver import GameResolver


def make_resolver():
    library = [{"appid": 646570, "name": "Slay the Spire"}, {"appid": 620, "name": "Portal 2"}, {"appid": 400, "name": "Portal"}]
    store = [{"id": 1145350, "name": "Hades II"}, {"id": 1145360, "name": "Hades"}]
    return GameResolver(lambda: library, lambda query, count: [item for item in store if query.casefold() in item["name"].casefold()])


def test_exact_case_insensitive_and_appid():
    resolver = make_resolver()
    assert resolver.resolve(game="slay the spire").appid == 646570
    assert resolver.resolve(game="STS").appid == 646570
    assert resolver.resolve(appid=620).name == "Portal 2"


def test_fuzzy_and_store_fallback():
    resolver = make_resolver()
    assert resolver.resolve(game="slay spire").appid == 646570
    assert resolver.resolve(game="Hades II").appid == 1145350


def test_ambiguous_match():
    resolver = make_resolver()
    with pytest.raises(AppError) as exc:
        resolver.resolve(game="port")
    assert exc.value.code == "AMBIGUOUS_GAME"


def test_missing_query():
    with pytest.raises(AppError) as exc:
        make_resolver().resolve()
    assert exc.value.code == "INVALID_ARGUMENT"
