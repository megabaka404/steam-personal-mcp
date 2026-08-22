from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from errors import AppError, error_payload, success_payload


def boundary(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            value = fn(*args, **kwargs)
            if isinstance(value, dict) and "success" in value:
                return value
            return success_payload(**(value if isinstance(value, dict) else {"result": value}))
        except AppError as exc:
            return error_payload(exc)
        except (TypeError, ValueError) as exc:
            return error_payload(AppError("INVALID_ARGUMENT", str(exc)))
        except Exception as exc:  # MCP tool calls must not crash the server.
            return error_payload(AppError("NETWORK_ERROR", "Steam request failed unexpectedly.", {"reason": type(exc).__name__}))
    return wrapped


def register(mcp, name: str, description: str, fn: Callable[..., dict[str, Any]]) -> None:
    mcp.tool(name=name, description=description, structured_output=True)(boundary(fn))
