from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def unix_time_info(value: Any) -> dict[str, Any] | None:
    """Return UTC ISO data for valid Steam timestamps; never fail on bad input."""
    if value in (None, "", 0, "0"):
        return None
    try:
        timestamp = int(value)
        if timestamp <= 0:
            return None
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return {"timestamp": timestamp, "datetime": dt.isoformat().replace("+00:00", "Z")}
    except (TypeError, ValueError, OSError, OverflowError):
        return None


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")

    steamid: str
    personaname: str = ""
    profileurl: str = ""
    avatar: str = ""
    avatarfull: str = ""
    personastate: int | None = None
    communityvisibilitystate: int | None = None
    profilestate: int | None = None
    realname: str | None = None
    timecreated: int | None = None
    loccountrycode: str | None = None
    locstatecode: str | None = None
    gameid: int | None = None
    gameextrainfo: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "steamid": self.steamid,
            "nickname": self.personaname,
            "profile_url": self.profileurl,
            "avatar": self.avatarfull or self.avatar,
            "online_state": self.personastate,
            "account_created": unix_time_info(self.timecreated),
            "country": self.loccountrycode,
            "state": self.locstatecode,
            "current_game": {
                "appid": self.gameid,
                "name": self.gameextrainfo,
            }
            if self.gameid or self.gameextrainfo
            else None,
        }
