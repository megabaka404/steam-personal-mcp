from __future__ import annotations

import asyncio

import httpx

from server import build_http_app, build_server


def test_all_tools_registered():
    mcp, runtime = build_server(mock=True)
    assert len(mcp._tool_manager._tools) == 52
    assert "steam_activity_summary" in mcp._tool_manager._tools
    assert "recommend_store_for_me" in mcp._tool_manager._tools
    assert "find_similar_games" in mcp._tool_manager._tools
    assert "get_wishlist_price_history" in mcp._tool_manager._tools
    assert "get_wishlist_price_drops" in mcp._tool_manager._tools
    assert "new_releases_for_me" in mcp._tool_manager._tools
    assert "friend_activity_summary" in mcp._tool_manager._tools
    assert "library_value_stats" in mcp._tool_manager._tools
    assert "missing_dlc_for_owned_games" in mcp._tool_manager._tools
    assert "wishlist_release_watch" in mcp._tool_manager._tools
    assert "record_play_session_snapshot" in mcp._tool_manager._tools
    assert "get_play_session_history" in mcp._tool_manager._tools
    assert "get_recent_play_sessions" in mcp._tool_manager._tools
    assert "steam_year_in_review" in mcp._tool_manager._tools
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
