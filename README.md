# Steam Personal + Store MCP

一个可长期运行的 Steam Personal + Store MCP Server。它把 Steam 个人账户数据和公开 Steam Store 数据分成两个 client，再通过库、成就、好友、愿望单、推荐和综合摘要服务组合成结构化 MCP tools。

它不调用外部 LLM，不保存 Steam 密码、Steam Guard、Cookie 或真实运行时数据库；推荐和愿望单 deal 排序都是确定性算法。

## 功能

- 账户：profile、当前正在玩的游戏、隐私可见性。
- 个人库：最近游戏、分页库、模糊搜索、拥有判断、游玩统计、从未玩/低时长/弃坑分析。
- 成就：单游戏详情、完成摘要、最近解锁、接近全成就和补成就候选。
- 好友：好友列表、好友正在玩的游戏、共同拥有游戏。
- 商店：搜索、详情、价格、折扣、DLC、当前 featured specials、按价格/折扣/评价比较。
- 愿望单：读取公开 wishlist appID，再用 Store appdetails 补全价格和详情；不可读时返回明确的 `available=false`，不会伪造数据。
- 推荐：backlog、return-to、comfort、recent、balanced、随机挑选和“下一款玩什么”。
- 摘要：`steam_activity_summary` 和 `steam_deals_summary` 控制返回大小，适合直接给上层模型使用。

## 当前接口依据

个人接口使用 Steam 官方 Web API 的 `ISteamUser`、`IPlayerService` 和 `ISteamUserStats`。Store 侧只使用 JSON/API 风格接口：`/api/appdetails`、`/api/storesearch/`、`/api/featuredcategories/`。愿望单使用当前可访问的 `IWishlistService/GetWishlist/v1`，它通常只给 appID、priority、date_added，随后逐个获取 Store 详情；该 endpoint 的可用性和返回范围由 Steam 账户隐私及 Valve 运行状态决定。

参考：

- [Steam Web API Overview](https://partner.steamgames.com/doc/webapi_overview)
- [ISteamUser](https://partner.steamgames.com/doc/webapi/ISteamUser)
- [IPlayerService](https://partner.steamgames.com/doc/webapi/IPlayerService)
- [ISteamUserStats](https://partner.steamgames.com/doc/webapi/ISteamUserStats)
- [IStoreService](https://partner.steamgames.com/doc/webapi/IStoreService)

项目不解析 Store HTML，不使用浏览器自动化，不要求 Steam 密码或 Steam Guard。

## 要求与安装

Python 3.10+，建议 Python 3.12+。

PowerShell：

```powershell
cd C:\path\to\steam-personal-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果 PowerShell 禁止激活脚本，可以直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖：当前 MCP Python SDK 2.0.0、Pydantic 2、httpx、pytest。实际启动入口仍是 `server.py`。

## Steam 凭据

1. 在 Steam 登录后打开 [Steam Web API Key 页面](https://steamcommunity.com/dev/apikey)，创建个人 API Key。
2. 使用 SteamID64 填入 `STEAM_ID`。可以从个人 profile URL 的数字路径获取，或使用 Steam OpenID/公开 SteamID 工具确认。
3. 不要把 `.env` 提交到 Git。`.gitignore` 已忽略 `.env`、数据库、缓存和日志。

推荐的 Steam 隐私设置：Profile 设为 Public，Game Details 设为 Public，取消“不让别人看到总游戏时间”的选项；好友列表如果需要读取，也必须公开。隐私设置变化后 Steam API 可能需要一点时间同步。

## 环境变量

`.env.example`：

```env
STEAM_API_KEY=
STEAM_ID=
STEAM_MCP_HOST=127.0.0.1
STEAM_MCP_PORT=8789
STEAM_CACHE_TTL=300
STEAM_HTTP_TIMEOUT=15
STEAM_STORE_COUNTRY=us
STEAM_STORE_LANGUAGE=english
STEAM_MAX_RETRIES=2
STEAM_MIN_REQUEST_INTERVAL=0.15
```

价格按 Steam 返回的真实 currency 和最小货币单位输出，例如 `price_minor` 与转换后的 `price`；项目不做汇率换算，也不把金额强行当成美元。

## 运行

真实模式：

```powershell
python server.py
```

默认地址：

```text
MCP:     http://127.0.0.1:8789/mcp
Health:  http://127.0.0.1:8789/health
Debug:   http://127.0.0.1:8789/debug/status
```

Mock 模式不需要 Steam API Key 和 SteamID：

```powershell
python server.py --mock
```

还保留了 stdio 入口，适合只支持本地进程的 MCP client：

```powershell
python server.py --stdio --mock
```

`/health` 不访问 Steam，始终只报告进程可用性；`/debug/status` 报告 cache entries、hits、misses、uptime、是否 mock 以及最近一次 API connectivity 状态，不返回 API Key。

## MCP 客户端配置示例

支持远程 Streamable HTTP 的 MCP client 通常可使用：

```json
{
  "mcpServers": {
    "steam-personal": {
      "url": "http://127.0.0.1:8789/mcp"
    }
  }
}
```

不同 ChatGPT/Codex/MCP 客户端的配置文件位置和字段名称可能不同；核心是把 URL 指向 `/mcp`，不是 `/health`。本地部署只监听 `127.0.0.1`。若要放到公网，必须在反向代理层增加 HTTPS、认证、请求体限制和访问日志脱敏。

## 实际注册的 MCP Tools

总计 52 个：

### 账户

- `get_profile()`
- `get_currently_playing()`
- `get_account_visibility()`

### 游戏库

- `get_recent_games(count=10)`
- `get_library(include_free_games=true, sort_by="playtime", order="desc", limit=null, offset=0)`
- `search_library(query, limit=20)`
- `get_game_in_library(game=null, appid=null, include_store=false)`
- `get_most_played(period="all", count=20)`，period 为 `all` 或 `recent`
- `get_never_played(count=50)`
- `get_low_playtime_games(max_hours=2, count=50)`
- `get_abandoned_games(min_hours=1, max_hours=20, inactive_days=180, count=30)`
- `get_library_stats()`
- `get_playtime_summary(top_n=20)`

### 成就

- `get_achievements(game=null, appid=null, include_locked=true)`
- `get_achievement_summary(game=null, appid=null)`
- `get_recent_achievements(days=30, count=30)`
- `get_almost_completed_games(min_completion=70, max_completion=99.99, count=20)`
- `get_completion_candidates(count=20)`

### 好友

- `get_friends(limit=100)`
- `get_friends_playing(limit=100)`
- `get_shared_games_with_friend(friend_steam_id, count=100)`

### Store

- `search_store(query, count=20)`
- `get_store_game(game=null, appid=null)`
- `get_specials(count=50, min_discount=0, max_price=null, min_price=null, sort_by="discount", exclude_owned=false)`
- `get_deep_discounts(min_discount=70, count=50, exclude_owned=false)`
- `search_sales(query=null, min_discount=0, max_price=null, genres=null, count=30, exclude_owned=false)`
- `compare_store_games(games)`，最多 10 个字符串或 AppID
- `get_game_dlc(game=null, appid=null, only_discounted=false)`

### 愿望单

- `get_wishlist(only_discounted=false, limit=100)`
- `get_wishlist_sales(min_discount=0, max_price=null, sort_by="discount", limit=100)`
- `get_wishlist_best_deals(limit=20)`
- `get_wishlist_price_history(appid=null, limit=100)`：返回 MCP 自己观察到的价格历史，不是 Steam 官方全平台历史最低价。
- `get_wishlist_price_drops()`：返回 MCP 观察到的降价和本地历史低价。

### 推荐

- `pick_a_game_for_me(count=1, never_played_only=false, max_playtime_hours=null, min_playtime_hours=null, inactive_days=null, exclude_appids=null, randomize=true)`
- `recommend_from_library(count=5, mode="balanced")`，mode 为 `balanced`、`backlog`、`return_to`、`comfort`、`recent`
- `find_backlog_candidates(count=20, max_hours=null)`
- `find_games_to_return_to(count=20, min_hours=1)`
- `compare_my_games(games)`，最多 10 个
- `what_should_i_play_next(count=5)`，返回 3–10 个候选
- `recommend_store_for_me(count=10, max_price=null, min_discount=0, include_wishlist=true, exclude_early_access=false)`
- `find_similar_games(game=null, appid=null, count=20, exclude_owned=true, max_price=null)`

### P1 个性化分析

- `new_releases_for_me(days=30, count=20, exclude_owned=true)`：从可发现的 Store 候选中筛选近期发布且匹配个人库偏好的游戏。
- `friend_activity_summary(limit=100)`：汇总公开好友在线、当前游戏和尽力而为的共同拥有游戏数据。
- `library_value_stats()`：使用当前 Store/MSRP 价格估算库价值、游玩小时和每美元小时数。
- `missing_dlc_for_owned_games(only_discounted=false, min_discount=0, count=100, exclude_soundtracks=false, exclude_cosmetics=false)`。
- `wishlist_release_watch()`：记录愿望单的 released/ upcoming 状态和 MCP 观察到的变化。

### P2 活动观察与年度回顾

- `record_play_session_snapshot()`：当 Steam 当前报告正在游玩的游戏时，保存一次 MCP 观察快照。
- `get_play_session_history(days=365, count=100)`：从连续观察快照推断游玩 session。
- `get_recent_play_sessions(days=30, count=20)`：返回近期推断 session。
- `steam_year_in_review(year=null)`：基于本地 MCP 观察生成非官方年度回顾。

P2 的活动数据只在 MCP 调用 `get_profile`、`get_currently_playing`、`steam_activity_summary` 或显式调用 `record_play_session_snapshot` 时采样。session 时长只计算两个观察点之间的跨度，不填补未观察到的时间，也不声称是 Steam 官方启动日志或官方 Year in Review。

### 综合

- `steam_activity_summary(include_store=true)`
- `steam_deals_summary(exclude_owned=true)`

除明确的 unavailable/private 结果外，工具成功响应带 `success: true`；错误统一为：

```json
{
  "success": false,
  "error": {
    "code": "GAME_NOT_FOUND",
    "message": "..."
  }
}
```

常见 code：`INVALID_API_KEY`、`PROFILE_PRIVATE`、`GAME_DETAILS_PRIVATE`、`ACHIEVEMENTS_UNAVAILABLE`、`GAME_NOT_FOUND`、`AMBIGUOUS_GAME`、`STORE_UNAVAILABLE`、`RATE_LIMITED`、`NETWORK_ERROR`、`INVALID_ARGUMENT`、`UNSUPPORTED`。

## 缓存与 HTTP 稳定性

所有 API 缓存都是单进程内存 TTL。价格观察例外：wishlist、wishlist sales、wishlist best deals 每次成功读取 Store 价格时，会写入 `STEAM_HISTORY_DB` 指定的 SQLite 文件，默认是 `data/steam_history.sqlite3`。相同 AppID、货币和价格状态会合并计数，不会无限重复插入。历史价格只代表 MCP 自己观察到的数据。

库和摘要工具有 limit/offset 或固定上限；最近成就只扫描不超过 30 个最近游戏，避免为几千个库项目制造请求风暴。

## Wishlist 限制

Steam 当前可访问的 wishlist service 主要返回 appID、priority、date_added，不是完整的价格对象。项目会对这些 appID 再请求 Store appdetails；如果 wishlist 为私有、服务不可访问或 Steam 返回空结构，工具返回 `available: false`、`supported: false` 和原因。它不会使用账户密码、Cookie、Steam Guard、浏览器自动化或 HTML wishlistdata 页面。

## 常见问题

### `INVALID_API_KEY`

检查 `.env` 是否在运行目录、变量名是否拼写正确，并重新启动进程。Mock 模式不需要凭据。

### 库为空或 `PROFILE_PRIVATE`

公开 Profile、Game Details 和游戏时间，并确认 `STEAM_ID` 是 SteamID64。Steam Web API 只会返回对当前 API 调用可见的个人数据。

### 成就不可用

有些游戏没有成就、没有公开成就 schema、玩家资料不可读，或 Steam API 对该 AppID 返回拒绝。工具会返回 `available: false`，不会把零成就误报为 100%。

### Store 搜索或 specials 数量较少

Store 公开 JSON 接口返回的是搜索/featured 结果，不是保证完整的全量商品数据库；featured specials 特别适合“当前有什么值得看”，但不能当作 Steam 全目录的严格排序。需要精确商品时使用 AppID。

### 价格不对地区

设置 `STEAM_STORE_COUNTRY`，例如 `cn`、`us`、`jp`。项目不做人民币/美元汇率转换。

## 安全

- 不要提交 `.env`、API Key、密码、Cookie、Steam Guard、用户数据库或真实运行时数据。
- API Key 不写入代码、不打印日志、不出现在 debug endpoint。
- 真实公网部署必须加 HTTPS、Bearer/OAuth 或反向代理认证；当前示例默认只绑定本机地址。
- 只使用公开 Steam API 数据，不尝试绕过 Steam 隐私设置。

## 测试

所有测试使用本地 mock clients 或 `httpx.MockTransport`，不依赖真实 Steam：

```powershell
pytest
```

Mock MCP 冒烟：

```powershell
python server.py --mock
Invoke-WebRequest http://127.0.0.1:8789/health
Invoke-WebRequest http://127.0.0.1:8789/debug/status
```

## 目录结构

```text
server.py
config.py
runtime.py
models/
clients/
services/
resolver/
cache/
tools/
tests/
examples/questions.md
```
