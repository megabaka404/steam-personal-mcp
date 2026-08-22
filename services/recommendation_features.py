from __future__ import annotations

import re
from typing import Any


BROAD_FEATURES = frozenset({
    "action", "adventure", "casual", "indie", "rpg", "simulation", "strategy", "sports",
})

SPECIFIC_FEATURE_ALIASES = {
    "roguelike": ("roguelike", "rogue-like"),
    "roguelite": ("roguelite", "rogue-lite"),
    "deckbuilder": ("deckbuilder", "deck-building", "deck building"),
    "card battler": ("card battler", "card battle"),
    "turn-based": ("turn-based", "turn based"),
    "soulslike": ("soulslike", "souls-like"),
    "metroidvania": ("metroidvania",),
    "co-op": ("co-op", "cooperative", "online co-op", "local co-op"),
    "multiplayer": ("multiplayer", "multi-player"),
    "singleplayer": ("single-player", "single player"),
    "survival": ("survival",),
    "city builder": ("city builder", "city-building", "city building"),
    "4x": ("4x",),
    "tactical": ("tactical",),
    "crpg": ("crpg", "computer rpg"),
    "management": ("management", "manager"),
    "platformer": ("platformer", "platforming"),
    "fps": ("fps", "first-person shooter", "first person shooter"),
    "third-person shooter": ("third-person shooter", "third person shooter"),
    "stealth": ("stealth",),
    "puzzle": ("puzzle",),
    "sandbox": ("sandbox",),
    "open world": ("open world",),
    "horror": ("horror",),
    "visual novel": ("visual novel",),
    "story rich": ("story rich", "story-driven", "story driven"),
    "racing": ("racing",),
}


def extract_features(detail: dict[str, Any]) -> dict[str, set[str]]:
    genres = _text_values(detail.get("genres"))
    categories = _text_values(detail.get("categories"))
    tags = _tag_values(detail.get("tags"))
    text = " ".join(
        [
            str(detail.get("name") or ""),
            str(detail.get("short_description") or ""),
            *genres,
            *categories,
            *tags,
        ]
    ).casefold()
    specific = {
        canonical
        for canonical, aliases in SPECIFIC_FEATURE_ALIASES.items()
        if any(_contains_phrase(text, alias) for alias in aliases)
    }
    return {
        "genres": {item for item in genres if item},
        "categories": {item for item in categories if item},
        "tags": {item for item in tags if item},
        "specific": specific,
        "broad": {item for item in genres | categories | tags if item in BROAD_FEATURES},
        "modes": _mode_values(categories),
        "developers": {normalize_text(item) for item in (detail.get("developers") or []) if normalize_text(item)},
        "publishers": {normalize_text(item) for item in (detail.get("publishers") or []) if normalize_text(item)},
    }


def compare_features(source: dict[str, set[str]], candidate: dict[str, set[str]]) -> tuple[float, list[str]]:
    overlaps = feature_overlaps(source, candidate)
    score = 0.0
    reasons: list[str] = []

    specific = overlaps["specific"]
    if specific:
        score += min(60.0, 28.0 * len(specific))
        reasons.extend(f"Shared specific feature: {value}" for value in specific[:3])

    tags = overlaps["tags"]
    if tags:
        score += min(24.0, 12.0 * len(tags))
        reasons.extend(f"Shared Store tag: {value}" for value in tags[:2])

    categories = overlaps["categories"]
    if categories:
        score += min(16.0, 6.0 * len(categories))
        reasons.extend(f"Shared category: {value}" for value in categories[:2])

    genres = overlaps["genres"]
    if genres:
        score += min(10.0, 4.0 * len(genres))
        reasons.extend(f"Shared broad genre (weak evidence): {value}" for value in genres[:2])

    if source.get("developers") and source.get("developers") & candidate.get("developers", set()):
        score += 4.0
        reasons.append("Same developer")
    if source.get("publishers") and source.get("publishers") & candidate.get("publishers", set()):
        score += 4.0
        reasons.append("Same publisher")
    return min(100.0, score), unique(reasons)


def feature_overlaps(source: dict[str, set[str]], candidate: dict[str, set[str]]) -> dict[str, list[str]]:
    return {
        key: sorted(source.get(key, set()) & candidate.get(key, set()))
        for key in ("specific", "tags", "categories", "genres")
    }


def best_profile_match(detail: dict[str, Any], profile: list[dict[str, Any]]):
    if not profile:
        return 0.0, [], None
    candidate = extract_features(detail)
    ranked = []
    for entry in profile:
        score, reasons = compare_features(entry["features"], candidate)
        ranked.append((score, reasons, entry))
    ranked.sort(key=lambda value: (value[0], value[2]["weight"]), reverse=True)
    best = ranked[0]
    return best[0], best[1], best[2]


def profile_evidence(detail: dict[str, Any], profile: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = extract_features(detail)
    matches: list[dict[str, Any]] = []
    matched_preferences: set[str] = set()
    for entry in profile:
        overlaps = feature_overlaps(entry["features"], candidate)
        matched = [value for values in overlaps.values() for value in values]
        if not matched:
            continue
        score, _ = compare_features(entry["features"], candidate)
        game = entry["game"]
        matched_preferences.update(value for group in ("specific", "tags") for value in overlaps[group])
        matches.append({
            "appid": game.appid,
            "name": game.name,
            "playtime_hours": game.total_hours,
            "recent_two_week_hours": game.recent_hours,
            "matched_features": overlaps,
            "match_strength": "specific" if overlaps["specific"] or overlaps["tags"] else "broad_only",
            "feature_match_score": round(score, 2),
        })
    matches.sort(key=lambda item: (-item["feature_match_score"], -item["playtime_hours"], item["name"].casefold(), item["appid"]))
    high_playtime = [item for item in matches if item["playtime_hours"] >= 20]
    recent = [item for item in matches if item["recent_two_week_hours"] > 0]
    return {
        "candidate_features": {
            "specific": sorted(candidate["specific"]),
            "tags": sorted(candidate["tags"]),
            "genres": sorted(candidate["genres"]),
            "categories": sorted(candidate["categories"]),
        },
        "all_matches": matches,
        "high_playtime_intersections": high_playtime[:8],
        "recent_intersections": recent[:8],
        "matched_preferences": sorted(matched_preferences),
        "profile_games_considered": len(profile),
        "user_modes": sorted({mode for entry in profile for mode in entry["features"].get("modes", set())}),
    }


def profile_terms(profile: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, float] = {}
    group_weights = {"specific": 3.0, "tags": 2.0, "categories": 1.0, "genres": 0.5}
    for entry in profile:
        for group, group_weight in group_weights.items():
            for value in entry["features"].get(group, set()):
                counts[value] = counts.get(value, 0) + entry["weight"] * group_weight
    return [value for value, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _text_values(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    result = set()
    for item in values:
        value = item.get("description") if isinstance(item, dict) else item
        normalized = normalize_text(value)
        if normalized:
            result.add(normalized)
    return result


def _tag_values(values: Any) -> set[str]:
    if isinstance(values, dict):
        return {normalize_text(key) for key in values if normalize_text(key)}
    if isinstance(values, list):
        result = set()
        for item in values:
            value = item.get("name") if isinstance(item, dict) else item
            normalized = normalize_text(value)
            if normalized:
                result.add(normalized)
        return result
    return set()


def _mode_values(categories: set[str]) -> set[str]:
    modes = set()
    if any(value in categories for value in ("single-player", "single player")):
        modes.add("singleplayer")
    if any(value in categories for value in ("multi-player", "multiplayer", "online multiplayer")):
        modes.add("multiplayer")
    if any("co-op" in value or "cooperative" in value for value in categories):
        modes.add("co-op")
    return modes


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.casefold()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))
