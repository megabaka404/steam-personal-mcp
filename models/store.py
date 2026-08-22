from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}

STORE_TYPE_ENUM = {
    0: "game",
    1: "dlc",
    2: "software",
    3: "video",
    4: "hardware",
    5: "music",
    6: "series",
}


def normalize_store_type(value: Any) -> str:
    """Normalize Store search/featured enum or string values before Pydantic."""
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized or "unknown"
    if isinstance(value, bool):
        return "unknown"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return STORE_TYPE_ENUM.get(number, "unknown")


def minor_to_major(minor: int | None, currency: str | None) -> float | None:
    if minor is None:
        return None
    digits = 0 if (currency or "").upper() in ZERO_DECIMAL_CURRENCIES else 2
    return round(int(minor) / (10**digits), digits)


class Price(BaseModel):
    model_config = ConfigDict(extra="allow")

    currency: str | None = None
    initial: int | None = None
    final: int | None = None
    discount_percent: int = 0

    def public_dict(self) -> dict[str, Any]:
        currency = self.currency
        return {
            "currency": currency,
            "original_price_minor": self.initial,
            "original_price": minor_to_major(self.initial, currency),
            "price_minor": self.final,
            "price": minor_to_major(self.final, currency),
            "discount_percent": self.discount_percent,
        }


class StoreGame(BaseModel):
    model_config = ConfigDict(extra="allow")

    appid: int
    name: str = "Unknown game"
    type: str | None = None
    header_image: str | None = None
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    release_date: dict[str, Any] | None = None
    genres: list[dict[str, Any]] = Field(default_factory=list)
    categories: list[dict[str, Any]] = Field(default_factory=list)
    short_description: str | None = None
    price: Price | None = None
    dlc: list[int] = Field(default_factory=list)
    supported_languages: str | None = None
    platforms: dict[str, bool] = Field(default_factory=dict)
    metacritic: dict[str, Any] | None = None
    recommendations: dict[str, Any] | None = None
    review_score: int | None = None
    review_percentage: int | None = None
    review_count: int | None = None
    owned_by_user: bool = False
    wishlisted_by_user: bool | None = None

    def public_dict(self, *, compact: bool = False) -> dict[str, Any]:
        data = {
            "appid": self.appid,
            "name": self.name,
            "type": self.type,
            "header_image": self.header_image,
            "developers": self.developers,
            "publishers": self.publishers,
            "release_date": self.release_date,
            "genres": self.genres,
            "categories": self.categories,
            "short_description": self.short_description,
            "price": self.price.public_dict() if self.price else None,
            "dlc": self.dlc,
            "supported_languages": self.supported_languages,
            "platforms": self.platforms,
            "metacritic": self.metacritic,
            "recommendations": self.recommendations,
            "review_score": self.review_score,
            "review_percentage": self.review_percentage,
            "review_count": self.review_count,
            "owned_by_user": self.owned_by_user,
            "wishlisted_by_user": self.wishlisted_by_user,
        }
        if compact:
            return {key: data[key] for key in ("appid", "name", "type", "price", "review_score", "review_percentage", "review_count", "genres", "owned_by_user", "wishlisted_by_user")}
        return data


def parse_price(raw: dict[str, Any] | None) -> Price | None:
    if not raw:
        return None
    try:
        initial = _int_or_none(raw.get("initial", raw.get("initial_price")))
        final = _int_or_none(raw.get("final", raw.get("final_price")))
        explicit_discount = _int_or_none(raw.get("discount_percent"))
        computed_discount = _calculate_discount(initial, final)
        discount = computed_discount if explicit_discount in (None, 0) and computed_discount > 0 else (explicit_discount if explicit_discount is not None else computed_discount)
        return Price(
            currency=raw.get("currency"),
            initial=initial,
            final=final,
            discount_percent=discount,
        )
    except (TypeError, ValueError):
        return None


def price_payload(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize Store search/featured price shapes before Price validation."""
    if not isinstance(raw, dict):
        return None
    nested = raw.get("price") or raw.get("price_overview")
    if isinstance(nested, dict):
        payload = dict(nested)
        if payload.get("discount_percent") is None and raw.get("discount_percent") is not None:
            payload["discount_percent"] = raw.get("discount_percent")
        return payload
    if any(raw.get(key) is not None for key in ("initial", "final", "original_price", "final_price", "initial_price")):
        return {
            "currency": raw.get("currency") or raw.get("currency_code"),
            "initial": raw.get("initial", raw.get("original_price", raw.get("initial_price"))),
            "final": raw.get("final", raw.get("final_price")),
            "discount_percent": raw.get("discount_percent"),
        }
    return None


def _calculate_discount(initial: int | None, final: int | None) -> int:
    if initial is None or final is None or initial <= 0 or final >= initial:
        return 0
    return max(0, min(100, int(round((initial - final) * 100 / initial))))


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
