# Steam Personal + Store MCP

一个本地运行的 Steam MCP Server。连接到 ChatGPT、Codex、Claude 等 MCP 客户端后，你可以用自然语言查询自己的 Steam 数据、搜索商店、分析折扣和整理游戏库。

## 可以让ai做什么？

### 1. 查看自己的 Steam

- 查看个人资料、和当前正在玩的游戏。
- 查看游戏库、总游玩时间、最近游玩的游戏和最后游玩时间。
- 搜索游戏库，找出没玩过、低时长或长期没玩的游戏。
- 查看成就完成度、最近解锁成就和接近完成的游戏。
- 查看好友、好友正在玩的游戏以及共同拥有的游戏。

常用工具：

~~~text
get_profile
get_currently_playing
get_library
get_recent_games
get_library_stats
get_playtime_summary
get_achievements
get_achievement_summary
get_friends
get_friends_playing
~~~

### 2. 搜索 Steam 商店

- 按关键词搜索游戏，查看当前价、原价和折扣。
- 查看商店详情、评价、类别、平台和 DLC。
- 查看特惠、深度折扣和促销列表，为你观察打折情况。
- 比较多个游戏，辅助决定先玩或先买哪个。

常用工具：

~~~text
search_store
get_store_game
get_specials
get_deep_discounts
search_sales
compare_store_games
get_game_dlc
~~~

### 3. 分析愿望单和折扣

- 查看愿望单及其中正在打折的游戏。
- 按价格、折扣和可用评价信息筛选 Deal。
- 记录 MCP 观察到的价格变化和降价。
- 查看愿望单游戏的发售状态的变化。

常用工具：

~~~text
get_wishlist
get_wishlist_sales
get_wishlist_best_deals
get_wishlist_price_history
get_wishlist_price_drops
wishlist_release_watch
~~~

### 4. 生成游戏候选

- 根据自己的高时长游戏、最近游玩和愿望单召回未拥有的商店游戏。
- 查找相似游戏、近期发布游戏和已拥有游戏缺少的 DLC。
- 查看游戏库的商店价值和一小时游玩花费美元。

常用工具：

~~~text
recommend_store_for_me
find_similar_games
new_releases_for_me
missing_dlc_for_owned_games
library_value_stats
~~~

推荐工具提供的是“候选召回 + 证据”，不是替你做最终购买判断。candidate_score 只代表一个游戏进入候选集的优先级，不代表最终适配度、购买置信度或“你一定会喜欢”。调用它的 AI 应结合价格、玩法特征、限制条件和你的当前需求继续判断。

候选结果会尽量包含：

- 当前价、原价、折扣、评价百分比和评价数量。
- genres、tags、categories。
- 单人、多人、合作和控制器/键鼠支持信息。
- 是否已拥有、是否在愿望单、是否 Early Access。
- 发售日期。
- 与高时长游戏、最近游玩的具体玩法特征交集。
- 命中的偏好、潜在冲突和缺失数据。

### 5. 记录游玩活动和年度回顾

当 MCP 观察到你正在运行的游戏时，可以保存本地快照，分析被实际观察到的游玩 session，并生成年度回顾。

~~~text
record_play_session_snapshot
get_play_session_history
get_recent_play_sessions
steam_year_in_review
~~~

这些不是 Steam 官方完整游玩日志，只统计 MCP 实际观察到的时间，不会猜测没有被观察到的时段。

## 快速开始

以下命令适用于 Windows PowerShell。

### 第一步：进入项目目录

从 GitHub 下载：

~~~powershell
git clone https://github.com/megabaka404/steam-personal-mcp.git
Set-Location steam-personal-mcp
~~~

如果项目已经在本地：

~~~powershell
Set-Location -LiteralPath '你的项目目录\steam-personal-mcp'
~~~

### 第二步：创建环境并安装依赖

项目需要 Python 3.10 或更高版本。

~~~powershell
py -3 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
~~~

### 第三步：配置 Steam

复制配置文件并编辑：

~~~powershell
Copy-Item .env.example .env
notepad .env
~~~

至少填写：

~~~dotenv
STEAM_API_KEY=你的Steam_Web_API_Key
STEAM_ID=你的SteamID64
~~~

获取 API Key：

<https://steamcommunity.com/dev/apikey>

注意：

- STEAM_ID 必须是 SteamID64。
- Steam Profile 和 Game Details 需要对外可见，否则个人数据可能无法读取。
- 商店价格取决于 STEAM_STORE_COUNTRY 和 STEAM_STORE_LANGUAGE。

可选配置：

~~~dotenv
STEAM_MCP_HOST=127.0.0.1
STEAM_MCP_PORT=8789
STEAM_STORE_COUNTRY=us
STEAM_STORE_LANGUAGE=english
STEAM_HISTORY_DB=data/steam_history.sqlite3
~~~

### 第四步：先用 Mock 模式检查服务

启动 Mock 服务：

~~~powershell
python server.py --mock
~~~

另开一个 PowerShell 窗口检查：

~~~powershell
Invoke-WebRequest http://127.0.0.1:8789/health | Select-Object -ExpandProperty Content
Invoke-WebRequest http://127.0.0.1:8789/debug/status | Select-Object -ExpandProperty Content
~~~

能看到健康检查成功后，再启动真实 Steam 模式。

### 第五步：启动真实服务

HTTP 模式：

~~~powershell
python server.py
~~~

MCP 地址：

~~~text
http://127.0.0.1:8789/mcp
~~~

stdio 模式：

~~~powershell
python server.py --stdio
~~~

需要 Mock 数据时：

~~~powershell
python server.py --stdio --mock
~~~

## MCP 客户端配置

如果客户端支持 Streamable HTTP，添加：

~~~json
{
  "mcpServers": {
    "steam-personal": {
      "url": "http://127.0.0.1:8789/mcp"
    }
  }
}
~~~

不要把 /health 当作 MCP 地址；它只是健康检查接口。

stdio 客户端则配置为启动 python server.py --stdio 的命令，并使用项目虚拟环境中的 Python。

连接成功后，可以直接提问：

~~~text
我的游戏库里有哪些几乎没玩过的游戏？
Darkest Dungeon 现在值得买吗？
把我的愿望单按当前折扣列出来。
根据我最近玩过的游戏召回 15 个候选，但只给证据，不要直接替我下结论。
~~~

## 数据来源和限制

- 个人数据主要来自 Steam Web API；商店数据来自 Steam Store 接口。
- Steam 个人资料、游戏详情或统计隐私设置可能导致数据缺失。
- 某些游戏不支持成就、玩家统计或公开评价，相关字段会为空。
- 商店接口不是完整、稳定的 Steam 全量目录；搜索结果可能受地区、语言和接口限制影响。
- 价格、货币和折扣按配置的商店地区返回。
- 评价数据只有在 Steam 接口可靠提供时才会填充，不会为了完整性猜测。
- 成就读取失败时不会伪造为“全部未解锁”。
- 价格历史、游玩 session 和年度回顾是本 MCP 本地观察结果，不是 Steam 官方完整历史。

## 项目结构

~~~text
server.py          服务入口
config.py          环境变量和启动参数
runtime.py         HTTP/stdio 运行时
clients/           Steam API 和 Store 客户端
services/          业务逻辑、推荐、历史记录
tools/             MCP 工具实现
models/            Pydantic 数据模型
tests/             自动化测试
data/              本地历史数据库目录
~~~

## 许可证

请以仓库中的许可证文件为准。Steam 数据属于 Steam/Valve 的服务内容；本项目只是读取公开接口并在本地进行整理和分析。

---

## 常见问题补充

### Store 搜索结果为什么不全？

公开 Store search / featured endpoint 不是 Steam 商品全量数据库。

因此，以下工具返回的是有界候选集：

~~~text
search_store
search_sales
new_releases_for_me
recommend_store_for_me
~~~

如果需要查询确定的游戏，优先使用 AppID。

### 价格地区不对

修改：

~~~env
STEAM_STORE_COUNTRY=cn
~~~

也可以使用：

~~~text
us
jp
...
~~~

项目不会自动做汇率换算。

---

## 安全

* 不提交 .env
* 不提交 Steam API Key
* 不保存 Steam 密码
* 不保存 Steam Guard
* 不需要 Steam Cookie
* API Key 不打印到日志
* debug endpoint 不返回 secret
* 不绕过 Steam 隐私设置
* 不自动购买、交易或修改 Steam 账户
* 默认只绑定 127.0.0.1

如果部署到公网，必须额外配置：

* HTTPS
* Bearer / OAuth / reverse proxy authentication
* 合理的请求限制
* 日志脱敏

---

## 测试

测试应使用 mock clients 或 httpx.MockTransport，避免依赖真实 Steam 状态。

运行：

~~~powershell
pytest
~~~

Mock MCP 冒烟：

~~~powershell
python server.py --mock

Invoke-WebRequest http://127.0.0.1:8789/health
Invoke-WebRequest http://127.0.0.1:8789/debug/status
~~~


---

本项目由 ChatGPT 和 Codex 协助完成。

