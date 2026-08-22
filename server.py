from __future__ import annotations

import time
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from config import Settings, parse_args
from runtime import Runtime, build_runtime
from tools.account_tools import register_account_tools
from tools.achievement_tools import register_achievement_tools
from tools.friend_tools import register_friend_tools
from tools.library_tools import register_library_tools
from tools.recommendation_tools import register_recommendation_tools
from tools.store_tools import register_store_tools
from tools.summary_tools import register_summary_tools
from tools.store_recommendation_tools import register_store_recommendation_tools
from tools.p1_tools import register_p1_tools
from tools.p2_tools import register_p2_tools
from tools.compound_tools import register_compound_tools

START_TIME = time.time()


def register_tools(mcp: MCPServer, runtime: Runtime) -> None:
    if runtime.settings.compact_tools:
        register_compound_tools(mcp, runtime)
    if runtime.settings.legacy_tools or not runtime.settings.compact_tools:
        register_account_tools(mcp, runtime)
        register_library_tools(mcp, runtime)
        register_achievement_tools(mcp, runtime)
        register_friend_tools(mcp, runtime)
        register_store_tools(mcp, runtime)
        register_recommendation_tools(mcp, runtime)
        register_summary_tools(mcp, runtime)
        register_store_recommendation_tools(mcp, runtime)
        register_p1_tools(mcp, runtime)
        register_p2_tools(mcp, runtime)


def build_server(*, mock: bool = False) -> tuple[MCPServer, Runtime]:
    settings = Settings.from_env(mock=mock)
    runtime = build_runtime(settings)
    mcp = MCPServer(
        name="steam-personal-store",
        version="0.1.0",
        description="Steam Personal + Store MCP with compact domain tools, explainable analysis, public Store data, and guarded local Steam inspection.",
        instructions="Use AppID when a game name is ambiguous. Personal data depends on Steam profile visibility. Store prices use the configured currency. game_intel data is sourced and may be unavailable. storage_cleanup never deletes during scan.",
    )
    register_tools(mcp, runtime)
    return mcp, runtime


def build_http_app(*, mock: bool = False):
    mcp, runtime = build_server(mock=mock)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "service": "steam-personal-store", "mock": runtime.settings.mock})

    async def debug_status(_: Request) -> JSONResponse:
        connectivity = {}
        for name, client in (("steam", runtime.steam), ("store", runtime.store_client)):
            connectivity[name] = getattr(client, "last_connectivity", getattr(getattr(client, "http", None), "last_connectivity", "not_checked"))
        return JSONResponse({
            "ok": True,
            "uptime_seconds": round(max(0, time.time() - START_TIME), 2),
            "config": runtime.settings.public_status(),
            "cache": runtime.cache.snapshot(),
            "api_connectivity": connectivity,
        })

    app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True, host=runtime.settings.host)
    app.routes.insert(0, Route("/debug/status", debug_status, methods=["GET"]))
    app.routes.insert(0, Route("/health", health, methods=["GET"]))
    return app, runtime


def main() -> None:
    args = parse_args()
    if args.stdio:
        mcp, runtime = build_server(mock=args.mock)
        try:
            mcp.run("stdio")
        finally:
            runtime.close()
        return
    import uvicorn

    app, runtime = build_http_app(mock=args.mock)
    try:
        uvicorn.run(app, host=runtime.settings.host, port=runtime.settings.port, log_level="info")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
