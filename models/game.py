from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .account import unix_time_info


class GameRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    appid: int
    name: str = "Unknown game"
    playtime_forever: int = Field(0, ge=0)
    playtime_2weeks: int = Field(0, ge=0)
    rtime_last_played: int | None = None
    img_icon_url: str | None = None
    img_logo_url: str | None = None
    is_free: bool | None = None
    type: str | None = None

    @property
    def total_hours(self) -> float:
        return round(self.playtime_forever / 60, 2)

    @property
    def recent_hours(self) -> float:
        return round(self.playtime_2weeks / 60, 2)

    def public_dict(self) -> dict[str, Any]:
        return {
            "appid": self.appid,
            "name": self.name,
            "playtime_minutes": self.playtime_forever,
            "playtime_hours": self.total_hours,
            "recent_two_week_minutes": self.playtime_2weeks,
            "recent_two_week_hours": self.recent_hours,
            "icon": self.img_icon_url,
            "logo": self.img_logo_url,
            "last_played": unix_time_info(self.rtime_last_played),
            "is_free": self.is_free,
        }


def parse_game(raw: dict[str, Any]) -> GameRecord:
    data = dict(raw)
    data["appid"] = int(data.get("appid", data.get("id", 0)))
    data["playtime_forever"] = _nonnegative_int(data.get("playtime_forever", data.get("playtime", 0)))
    data["playtime_2weeks"] = _nonnegative_int(data.get("playtime_2weeks", 0))
    if data.get("rtime_last_played") in ("", "0"):
        data["rtime_last_played"] = None
    return GameRecord.model_validate(data)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
