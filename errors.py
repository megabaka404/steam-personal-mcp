from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def error_payload(error: AppError) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.details:
        payload["details"] = error.details
    return {"success": False, "error": payload}


def success_payload(**values: Any) -> dict[str, Any]:
    return {"success": True, **values}
