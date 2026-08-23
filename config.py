from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    steam_id: str | None
    host: str = "127.0.0.1"
    port: int = 8789
    cache_ttl: int = 300
    http_timeout: float = 15.0
    store_country: str = "cn"
    store_language: str = "english"
    max_retries: int = 2
    min_request_interval: float = 0.15
    history_db_path: str = "data/steam_history.sqlite3"
    mock: bool = False
    compact_tools: bool = True
    legacy_tools: bool = False

    @classmethod
    def from_env(cls, *, mock: bool = False, env_file: Path | None = None) -> "Settings":
        _load_dotenv(env_file or Path.cwd() / ".env")
        return cls(
            api_key=os.getenv("STEAM_API_KEY") or None,
            steam_id=os.getenv("STEAM_ID") or None,
            host=os.getenv("STEAM_MCP_HOST", "127.0.0.1"),
            port=_int_env("STEAM_MCP_PORT", 8789, 1, 65535),
            cache_ttl=_int_env("STEAM_CACHE_TTL", 300, 1),
            http_timeout=_float_env("STEAM_HTTP_TIMEOUT", 15.0, 1.0),
            store_country=os.getenv("STEAM_STORE_COUNTRY", "cn").lower(),
            store_language=os.getenv("STEAM_STORE_LANGUAGE", "english"),
            max_retries=_int_env("STEAM_MAX_RETRIES", 2, 0, 5),
            min_request_interval=_float_env("STEAM_MIN_REQUEST_INTERVAL", 0.15, 0.0),
            history_db_path=os.getenv("STEAM_HISTORY_DB", "data/steam_history.sqlite3"),
            mock=mock,
            compact_tools=_bool_env("STEAM_MCP_COMPACT_TOOLS", True),
            legacy_tools=_bool_env("STEAM_MCP_LEGACY_TOOLS", False),
        )

    def public_status(self) -> dict[str, object]:
        return {"mock": self.mock, "api_key_configured": bool(self.api_key), "steam_id_configured": bool(self.steam_id), "host": self.host, "port": self.port, "store_country": self.store_country, "cache_ttl": self.cache_ttl, "http_timeout": self.http_timeout, "compact_tools": self.compact_tools, "legacy_tools": self.legacy_tools}


def _int_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _float_env(name: str, default: float, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value) if minimum is not None else value


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Steam Personal + Store MCP Server")
    parser.add_argument("--mock", action="store_true", help="Run with deterministic in-memory data")
    parser.add_argument("--stdio", action="store_true", help="Use MCP stdio transport instead of HTTP")
    return parser.parse_args()
