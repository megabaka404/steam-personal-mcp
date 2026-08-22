from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .account import unix_time_info


class Achievement(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_name: str = ""
    display_name: str = ""
    description: str = ""
    achieved: bool = False
    unlocktime: int | None = None
    hidden: bool = False
    icon: str | None = None
    icongray: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "api_name": self.api_name,
            "display_name": self.display_name,
            "description": self.description,
            "achieved": self.achieved,
            "unlock_time": unix_time_info(self.unlocktime),
            "hidden": self.hidden,
            "icon": self.icon,
            "icon_gray": self.icongray,
        }


def completion(achievements: list[Achievement]) -> float:
    if not achievements:
        return 0.0
    return round(sum(1 for item in achievements if item.achieved) * 100 / len(achievements), 2)
