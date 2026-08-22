from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable

from errors import AppError


@dataclass(frozen=True)
class ResolvedGame:
    appid: int
    name: str
    source: str


ALIASES = {
    "sts": 646570,
    "slay the spire": 646570,
    "杀戮尖塔": 646570,
    "杀戮尖塔sts": 646570,
    "hades 2": 1145350,
    "哈迪斯2": 1145350,
    "哈迪斯 ii": 1145350,
    "哈迪斯": 1145360,
    "dead cells": 588650,
    "死亡细胞": 588650,
    "hk": 367520,
    "hollow knight": 367520,
    "空洞骑士": 367520,
    "ror2": 632360,
    "risk of rain 2": 632360,
    "吸血鬼幸存者": 1794680,
}


class GameResolver:
    """Resolve AppID/name with library-first and Store-search fallback semantics."""

    def __init__(self, library_provider: Callable[[], list[dict[str, Any]]], store_search: Callable[[str, int], list[dict[str, Any]]]) -> None:
        self.library_provider = library_provider
        self.store_search = store_search

    def resolve(self, *, game: str | None = None, appid: int | None = None) -> ResolvedGame:
        if appid is None and not (game and game.strip()):
            raise AppError("INVALID_ARGUMENT", "Provide either game or appid.")
        library = self._library_candidates()
        if appid is not None:
            for item in library:
                if int(item.get("appid", 0)) == int(appid):
                    return ResolvedGame(int(appid), str(item.get("name") or f"App {appid}"), "library")
            return ResolvedGame(int(appid), f"App {appid}", "appid")

        query = _normalize(game or "")
        alias_appid = ALIASES.get(query)
        if alias_appid is not None:
            for item in library:
                if int(item.get("appid", 0)) == alias_appid:
                    return ResolvedGame(alias_appid, str(item.get("name") or game), "library-alias")
            try:
                store_items = self.store_search(game or "", 10)
            except Exception:
                store_items = []
            for item in store_items:
                if int(item.get("id", item.get("appid", 0)) or 0) == alias_appid:
                    return ResolvedGame(alias_appid, str(item.get("name") or game), "store-alias")

        candidates = self._name_candidates(library, game or "")
        exact = [item for item in candidates if _normalize(str(item.get("name", ""))) == query]
        if len(exact) == 1:
            return self._to_resolved(exact[0], "library-exact" if exact[0].get("_source") == "library" else "store-exact")
        if len(exact) > 1:
            raise self._ambiguous(exact)

        scored = []
        for item in candidates:
            name = _normalize(str(item.get("name", "")))
            score = max(SequenceMatcher(None, query, name).ratio(), _token_score(query, name))
            if score >= 0.42:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("name", "")).casefold()))
        if not scored:
            raise AppError("GAME_NOT_FOUND", f"Could not find a Steam game matching '{game}'.")
        best_score, best = scored[0]
        close = [item for score, item in scored if score >= max(0.62, best_score - 0.16)]
        if len(close) > 1 and best_score < 0.92:
            raise self._ambiguous(close[:5])
        return self._to_resolved(best, "library-fuzzy" if best.get("_source") == "library" else "store-fuzzy")

    def _library_candidates(self) -> list[dict[str, Any]]:
        try:
            return [dict(item) for item in (self.library_provider() or [])]
        except Exception:
            return []

    def _name_candidates(self, library: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        candidates = [{**item, "_source": "library"} for item in library if item.get("name")]
        # Store search is intentionally a fallback and is bounded to keep ambiguous results small.
        try:
            store_candidates = self.store_search(query, 10) if query else []
        except Exception:
            store_candidates = []
        known = {int(item.get("appid", item.get("id", 0)) or 0) for item in candidates}
        for item in store_candidates:
            item = dict(item)
            item["appid"] = int(item.get("appid", item.get("id", 0)) or 0)
            if item["appid"] and item["appid"] not in known and item.get("name"):
                item["_source"] = "store"
                candidates.append(item)
        return candidates

    def _to_resolved(self, item: dict[str, Any], source: str) -> ResolvedGame:
        return ResolvedGame(int(item.get("appid", item.get("id"))), str(item.get("name") or f"App {item.get('appid', item.get('id'))}"), source)

    @staticmethod
    def _ambiguous(items: list[dict[str, Any]]) -> AppError:
        candidates = [{"appid": int(item.get("appid", item.get("id", 0))), "name": item.get("name", "")} for item in items]
        return AppError("AMBIGUOUS_GAME", "The game name matches multiple Steam games; choose an AppID or candidate.", {"candidates": candidates})


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _token_score(query: str, name: str) -> float:
    q_tokens, n_tokens = set(query.split()), set(name.split())
    if not q_tokens or not n_tokens:
        return 0.0
    return len(q_tokens & n_tokens) / len(q_tokens | n_tokens)
