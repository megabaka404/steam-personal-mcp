# Steam Personal + Store MCP

一个面向个人 Steam 账户与公开 Steam Store 数据的只读 MCP Server。

它可以让 ChatGPT、Codex、Claude 等 MCP 客户端直接读取你的 Steam 游戏库、游玩时间、成就、好友、愿望单和商店数据，并进一步完成 backlog 分析、折扣筛选、游戏比较、推荐候选、DLC 检查、价格观察和游玩记录总结。

例如可以直接问：

* “我最近都在玩什么？”
* “从我的库里挑几个现在适合玩的游戏。”
* “我的愿望单现在有什么值得看的折扣？”
* “找一些和 Slay the Spire 类似、但我还没买的游戏。”
* “根据我的游玩历史给我一批打折游戏候选。”
* “我有哪些买了但几乎没玩的游戏？”
* “哪些游戏快全成就了？”
* “我拥有的游戏还有哪些 DLC 没买？”
* “我的 Steam 库按当前商店价格大概值多少？”
* “总结一下 MCP 最近观察到的游玩记录。”

项目本身不调用外部 LLM。它负责读取、过滤、聚合和结构化 Steam 数据，最终判断可以交给上层模型完成。

---

## 特性

### 个人账户

* Profile、在线状态和当前游戏
* 最近游玩
* 完整游戏库
* 总游玩时间与分布
* 从未启动、低时长和长期弃坑游戏
* 回坑候选与 backlog 分析
* 库价值估算

### 成就

* 单游戏完整成就
* 完成度摘要
* 最近解锁
* 接近全成就的游戏
* 补成就候选

### 好友

* 好友列表
* 当前正在玩游戏的好友
* 与指定好友的共同游戏
* 好友活动摘要

### Steam Store

* 游戏搜索
* Store 详情
* 当前价格与折扣
* Featured specials
* 深度折扣
* 销售搜索
* 游戏比较
* DLC
* 相似游戏
* 最近发售游戏
* 根据个人库生成 Store 候选

### 愿望单

* 愿望单读取
* 当前折扣
* deal 排序
* MCP 本地观察到的价格历史
* 价格下降检测
* 发售状态变化观察

### 活动记录

Steam Web API 不提供完整的历史启动记录，因此本项目支持记录 MCP 自己观察到的当前游戏 snapshot，并据此推断有限的 play sessions。

它还可以生成一个明确标注为 **非 Steam 官方年度回顾** 的 year review。

没有被 MCP 观察到的游玩行为不会被凭空补全。

---

## 推荐设计

推荐类工具的目标不是让 MCP 自己替用户做最终决定。

推荐流程更适合拆成两层：

```text
Steam / Store 数据
        ↓
候选召回与过滤
        ↓
结构化证据
        ↓
LLM 根据用户上下文做最终判断
```

MCP 可以提供：

* 当前价格和折扣
* review percentage / count
* genres
* categories
* Store metadata
* 是否已拥有
* 是否在愿望单
* 用户高时长游戏
* 最近游玩游戏
* 候选与这些游戏之间的具体共同特征
* candidate reasons
* potential mismatches
* deterministic candidate score

其中 `candidate_score` 只用于候选召回和粗排，不应被解释为“用户喜欢这款游戏的概率”。

像 `Indie`、`Single-player`、`Family Sharing` 这类非常宽泛的 metadata 本身不应成为强玩法相似证据。

更具体的玩法特征，例如：

* roguelike
* deckbuilder
* turn-based
* tactical
* CRPG
* management
* platformer
* FPS
* action combat

应拥有更高的信息价值。

最终的：

> “这游戏到底适不适合这个用户？”

交给调用 MCP 的 LLM 判断。

---

## 数据来源

个人账户相关数据主要来自 Steam 官方 Web API：

* `ISteamUser`
* `IPlayerService`
* `ISteamUserStats`

Store 侧使用公开 JSON/API 风格接口，例如：

* `/api/appdetails`
* `/api/storesearch/`
* `/api/featuredcategories/`

愿望单使用当前可访问的：

```text
IWishlistService/GetWishlist/v1
```

该接口通常只返回 appID、priority 和 date_added，因此项目会再通过 Store 数据补充游戏名称、价格、折扣等信息。

参考：

* [Steam Web API Overview](https://partner.steamgames.com/doc/webapi_overview)
* [ISteamUser](https://partner.steamgames.com/doc/webapi/ISteamUser)
* [IPlayerService](https://partner.steamgames.com/doc/webapi/IPlayerService)
* [ISteamUserStats](https://partner.steamgames.com/doc/webapi/ISteamUserStats)
* [IStoreService](https://partner.steamgames.com/doc/webapi/IStoreService)

项目不解析 Steam Store HTML，不使用浏览器自动化，也不需要 Steam 密码、Steam Guard 或 Cookie。

---

## 要求

Python 3.10+。

建议使用较新的 Python 3.12+。

安装项目依赖：

```powershell
cd C:\path\to\steam-personal-mcp

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果 PowerShell 禁止激活脚本，也可以直接：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

实际启动入口：

```text
server.py
```

---

## Steam 凭据

### 1. Steam Web API Key

登录 Steam 后打开：

https://steamcommunity.com/dev/apikey

创建个人 API Key。

### 2. SteamID64

把自己的 SteamID64 填入 `STEAM_ID`。

### 3. 隐私设置

建议：

* Profile：Public
* Game Details：Public
* 游戏总时长：允许公开
* 如果需要好友工具，Friends List 也需要公开

Steam 隐私设置修改后可能需要一些时间同步。

不要把 `.env` 提交到 Git。

---

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

Store 价格使用 Steam 实际返回的 currency 和最小货币单位。

例如：

```json
{
  "currency": "USD",
  "price_minor": 1239,
  "price": 12.39
}
```

项目不自行进行汇率换算。

---

## 启动

真实 Steam 数据：

```powershell
python server.py
```

默认：

```text
MCP:     http://127.0.0.1:8789/mcp
Health:  http://127.0.0.1:8789/health
Debug:   http://127.0.0.1:8789/debug/status
```

Mock 模式：

```powershell
python server.py --mock
```

Mock 不需要 Steam API Key 或 SteamID。

stdio：

```powershell
python server.py --stdio --mock
```

`/health` 只检查服务本身是否存活，不请求 Steam。

`/debug/status` 可以查看：

* uptime
* mock 状态
* cache entries
* cache hits / misses
* 最近 API connectivity

不会返回 API Key。

---

## MCP 客户端

支持 Streamable HTTP 的 MCP 客户端可以使用：

```json
{
  "mcpServers": {
    "steam-personal": {
      "url": "http://127.0.0.1:8789/mcp"
    }
  }
}
```

不同 ChatGPT、Codex、Claude 和其他 MCP 客户端的外层配置格式可能不同。

核心 endpoint 是：

```text
/mcp
```

而不是：

```text
/health
```

默认只监听 `127.0.0.1`。

如果将服务暴露到公网，应在外部增加 HTTPS 和认证，不建议直接公开 Python MCP endpoint。

---

# MCP Tools

当前版本共注册 **52 个 tools**。

## Account

| Tool                     | 作用                       |
| ------------------------ | ------------------------ |
| `get_profile`            | Profile、头像、账户状态与当前游戏     |
| `get_currently_playing`  | 判断当前是否正在玩游戏              |
| `get_account_visibility` | 检查 Profile、游戏库、成就和好友是否可读 |

## Library

| Tool                      | 作用                            |
| ------------------------- | ----------------------------- |
| `get_recent_games`        | 最近游玩的游戏                       |
| `get_library`             | 分页、排序读取完整游戏库                  |
| `search_library`          | 模糊搜索已拥有游戏                     |
| `get_game_in_library`     | 判断是否拥有某游戏并返回个人数据              |
| `get_most_played`         | 总时长或近两周最高游戏                   |
| `get_never_played`        | 从未启动游戏                        |
| `get_low_playtime_games`  | 低时长游戏                         |
| `get_abandoned_games`     | 玩过但长期未打开的游戏                   |
| `get_library_stats`       | 游戏库整体统计                       |
| `get_playtime_summary`    | 面向 LLM 的精简游玩摘要                |
| `find_backlog_candidates` | backlog 候选                    |
| `find_games_to_return_to` | 回坑候选                          |
| `recommend_from_library`  | 从已拥有游戏中进行确定性粗排                |
| `pick_a_game_for_me`      | 按条件随机选择游戏                     |
| `what_should_i_play_next` | 下一款游戏候选                       |
| `compare_my_games`        | 比较最多十个游戏的个人数据                 |
| `library_value_stats`     | 估算当前/MSRP 库价值和 playtime value |

## Achievements

| Tool                         | 作用        |
| ---------------------------- | --------- |
| `get_achievements`           | 完整成就与锁定状态 |
| `get_achievement_summary`    | 精简成就完成度   |
| `get_recent_achievements`    | 最近解锁成就    |
| `get_almost_completed_games` | 接近全成就游戏   |
| `get_completion_candidates`  | 补全成就候选    |

## Friends

| Tool                           | 作用            |
| ------------------------------ | ------------- |
| `get_friends`                  | 好友列表          |
| `get_friends_playing`          | 当前正在玩游戏的好友    |
| `get_shared_games_with_friend` | 与指定好友共同拥有的游戏  |
| `friend_activity_summary`      | 好友当前活动与共同游戏摘要 |

## Store

| Tool                          | 作用                       |
| ----------------------------- | ------------------------ |
| `search_store`                | 搜索 Steam Store           |
| `get_store_game`              | 游戏详情、价格、平台、DLC 等         |
| `get_specials`                | 当前 featured specials     |
| `get_deep_discounts`          | 深度折扣                     |
| `search_sales`                | 按关键词、折扣、价格、genre 搜索促销    |
| `compare_store_games`         | 比较最多十个 Store 游戏          |
| `get_game_dlc`                | 获取游戏 DLC                 |
| `find_similar_games`          | 根据 Store metadata 寻找相似游戏 |
| `new_releases_for_me`         | 从近期公开 Store 候选中寻找可能相关的新作 |
| `missing_dlc_for_owned_games` | 查找已拥有游戏但尚未拥有的 DLC        |
| `recommend_store_for_me`      | 根据个人库和 Store 数据生成未拥有游戏候选 |

Store 搜索与推荐不是 Steam 全目录扫描。

它们基于公开 Store search、featured specials、wishlist 和能够获取到的 Store metadata，因此结果应该理解为：

> “当前候选集合中值得进一步判断的项目”

而不是严格意义上的全 Steam 最优推荐。

## Wishlist

| Tool                         | 作用                                 |
| ---------------------------- | ---------------------------------- |
| `get_wishlist`               | 读取愿望单并补全 Store 数据                  |
| `get_wishlist_sales`         | 当前打折愿望单                            |
| `get_wishlist_best_deals`    | 根据折扣、价格和评价进行确定性 deal 粗排            |
| `get_wishlist_price_history` | MCP 自己观察到的价格历史                     |
| `get_wishlist_price_drops`   | 检测 wishlist 价格下降与本地观察低价            |
| `wishlist_release_watch`     | 观察 coming soon / release date 状态变化 |

`get_wishlist_price_history` 不是 Steam 官方历史最低价数据库。

它只记录 MCP 实际观察过的数据。

## Activity / Summary

| Tool                           | 作用                             |
| ------------------------------ | ------------------------------ |
| `record_play_session_snapshot` | 如果当前正在玩游戏，记录一次 MCP snapshot    |
| `get_play_session_history`     | 根据 snapshot 推断历史 play sessions |
| `get_recent_play_sessions`     | 最近推断出的 sessions                |
| `steam_year_in_review`         | 基于 MCP 观察记录生成非官方年度回顾           |
| `steam_activity_summary`       | 一次返回账户、最近游戏、库统计、成就等精简摘要        |
| `steam_deals_summary`          | 当前 specials、愿望单折扣和深度折扣摘要       |

---

## 错误格式

正常工具通常返回：

```json
{
  "success": true
}
```

错误统一使用类似：

```json
{
  "success": false,
  "error": {
    "code": "GAME_NOT_FOUND",
    "message": "..."
  }
}
```

常见错误：

* `INVALID_API_KEY`
* `PROFILE_PRIVATE`
* `GAME_DETAILS_PRIVATE`
* `ACHIEVEMENTS_UNAVAILABLE`
* `GAME_NOT_FOUND`
* `AMBIGUOUS_GAME`
* `STORE_UNAVAILABLE`
* `RATE_LIMITED`
* `NETWORK_ERROR`
* `INVALID_ARGUMENT`
* `UNSUPPORTED`

对于正常但数据不可获得的情况，例如：

* 私有愿望单
* 某游戏没有公开成就
* Steam 没有返回所需数据

工具会尽量使用：

```json
{
  "available": false
}
```

而不是伪造空数据。

---

## Cache 与 HTTP

缓存为单进程内存 TTL，不写入用户文件。

典型缓存包括：

* Profile
* Currently Playing
* Recent Games
* Owned Games
* Achievements
* Store Details
* Featured Sales

HTTP client 包含：

* User-Agent
* timeout
* 请求间隔
* retry
* exponential backoff
* 429 处理
* 5xx 处理
* 非 JSON 返回处理
* 缺字段容错

大型库分析和摘要工具会设置边界，避免一次调用对 Steam API 产生大量请求。

---

## Wishlist 限制

Steam Wishlist API 的实际可用性受：

* Steam 隐私设置
* Valve endpoint 状态
* 返回字段范围

影响。

Wishlist service 通常只直接提供：

```text
appid
priority
date_added
```

项目随后使用 Store 接口补充详情。

如果愿望单不可读取，会明确返回 unavailable / unsupported，而不会使用：

* Steam 密码
* Cookie
* Steam Guard
* 浏览器自动化
* HTML scraping

作为替代方案。

---

## Play Session 限制

Steam Web API 不提供完整的逐次启动历史。

因此：

```text
record_play_session_snapshot
```

只能记录 MCP **实际观察到** 的当前游戏。

由这些 snapshot 推断出的：

* session duration
* yearly activity
* returned-to games
* new games started

都只能代表 MCP 的观察范围。

`steam_year_in_review` 会明确标记：

```text
is_official_steam_year_in_review = false
```

不会把当前累计 playtime 倒推成虚假的年度历史。

---

## 常见问题

### `INVALID_API_KEY`

检查：

* `.env` 是否正确注入
* 环境变量名称
* Steam API Key 是否仍然有效

Mock 模式不需要凭据。

### 游戏库为空

确认：

* Profile 是 Public
* Game Details 是 Public
* `STEAM_ID` 是正确的 SteamID64

### 成就不可用

并不是所有游戏都有：

* Steam achievements
* 公开 achievement schema
* 可读玩家成就

这种情况会返回 unavailable，而不是把“没有数据”解释成 0% 或 100%。

### Store 搜索结果为什么不全？

公开 Store search / featured endpoint 不是 Steam 商品全量数据库。

因此：

```text
search_store
search_sales
new_releases_for_me
recommend_store_for_me
```

返回的是有界候选集。

如果需要查询确定的游戏，优先使用 AppID。

### 价格地区不对

修改：

```env
STEAM_STORE_COUNTRY=cn
```

也可以使用：

```text
us
jp
...
```

项目不会自动做汇率换算。

---

## 安全

* 不提交 `.env`
* 不提交 Steam API Key
* 不保存 Steam 密码
* 不保存 Steam Guard
* 不需要 Steam Cookie
* API Key 不打印到日志
* debug endpoint 不返回 secret
* 不绕过 Steam 隐私设置
* 不自动购买、交易或修改 Steam 账户
* 默认只绑定 `127.0.0.1`

如果部署到公网，必须额外配置：

* HTTPS
* Bearer / OAuth / reverse proxy authentication
* 合理的请求限制
* 日志脱敏

---

## 测试

测试应使用 mock clients 或 `httpx.MockTransport`，避免依赖真实 Steam 状态。

运行：

```powershell
pytest
```

Mock MCP 冒烟：

```powershell
python server.py --mock

Invoke-WebRequest http://127.0.0.1:8789/health
Invoke-WebRequest http://127.0.0.1:8789/debug/status
```

推荐与发现相关测试应特别覆盖：

* deterministic ordering
* owned exclusion
* count / pagination bounds
* 缺失 Store metadata
* private/unavailable 数据
* 泛 genre 不制造虚假高相似度
* wishlist / discount 与玩法适配度分离
* 新作推荐不会因为 `Indie` 等宽泛标签产生强关联

---



Co-authored-by: Codex  and ChatGPT   by OpenAI

