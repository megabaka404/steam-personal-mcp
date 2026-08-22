from __future__ import annotations

import asyncio

import httpx

from server import build_http_app, build_server


def test_compact_tools_registered():
    mcp, runtime = build_server(mock=True)
    assert len(mcp._tool_manager._tools) == 12
    assert {
        "player",
        "library",
        "achievements",
        "friends",
        "store",
        "deals",
        "wishlist",
        "recommendations",
        "activity",
        "game_intel",
        "local_steam",
        "storage_cleanup",
    } == set(mcp._tool_manager._tools)
    runtime.close()


def test_legacy_tools_can_be_enabled(monkeypatch):
    monkeypatch.setenv("STEAM_MCP_COMPACT_TOOLS", "0")
    monkeypatch.setenv("STEAM_MCP_LEGACY_TOOLS", "1")
    mcp, runtime = build_server(mock=True)
    assert len(mcp._tool_manager._tools) == 52
    assert "get_profile" in mcp._tool_manager._tools
    assert "recommend_store_for_me" in mcp._tool_manager._tools
    runtime.close()


def test_health_and_debug_routes():
    app, runtime = build_http_app(mock=True)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8789") as client:
            health = await client.get("/health")
            debug = await client.get("/debug/status")
            return health, debug

    health, debug = asyncio.run(run())
    runtime.close()
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert debug.status_code == 200
    assert "cache" in debug.json()
