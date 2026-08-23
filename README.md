# Steam Personal + Store MCP

一个本地运行的 Steam MCP Server。默认只暴露 12 个按领域组织的复合 tool，降低 MCP schema 和上下文占用；底层 Python 服务仍保留，旧工具可通过兼容开关恢复。

## 可以做什么

### 个人数据

player 查询 Profile、当前游戏和可见性；library 查询游戏库、时长、最近游玩、backlog、弃坑和回坑候选；achievements 查询成就详情、完成度和最近解锁；friends 查询好友和公开的共同游戏。

### 商店、折扣和愿望单

store 搜索详情、比较游戏和查看 DLC；deals 查询特惠、深度折扣和销售；wishlist 查看愿望单、价格历史、降价、发售变化，以及有证据的 buy / wait / skip 建议。

### 推荐和统一游戏画像

recommendations 召回商店候选、相似游戏、新作、backlog 和库重复度分析。候选的 candidate_score 只表示检索优先级，不是最终适配度或购买置信度，最终判断交给调用它的 AI。

game_intel(action="snapshot") 汇总一个游戏的：

- 个人拥有状态、总时长、最近时长、最后游玩和成就。
- 当前价、原价、折扣、MCP 观察到的价格历史。
- 总体评价、近期评价、评价数量和可用的 7/30/90 天趋势。
- Steam Deck 状态、Workshop 支持、当前玩家数和可解释热度指标。
- 发售日期、更新/build 信息、DLC、已拥有 DLC 和缺少的 DLC。
- 本地安装路径、SizeOnDisk、实际目录大小和 shadercache；Windows 的 compatdata 明确标记为 not_applicable。


### 本地 Steam 和安全清理

local_steam 读取 Windows 的 libraryfolders.vdf、appmanifest 文件、已安装游戏和磁盘占用。storage_cleanup 分为 scan、preview、clean 三步，scan 永不删除；clean 必须明确指定 appids、targets 并传入 confirm=true。shadercache 为低风险，compatdata 默认高风险且 Windows 第一版不适用。

## 复合 tool / action

~~~text
player: profile | currently_playing | visibility
library: search | stats | most_played | recent | abandoned | never_played | low_playtime | backlog | return_to | game
achievements: details | summary | recent | almost_completed | completion_candidates
friends: list | playing | activity | shared
store: search | details | compare | dlc
deals: specials | deep_discounts | search_sales | summary
wishlist: list | sales | best_deals | price_history | price_drops | release_watch | buy_advice | purchase_candidates
recommendations: store | similar | new_releases | library | backlog | return_to | next | overlap | pick
activity: record | sessions | recent_sessions | year_review | game_change_history
game_intel: snapshot | update_impact
local_steam: scan | installed | disk_usage
storage_cleanup: scan | preview | clean
~~~

项目本身不调用外部 LLM。它负责读取、过滤、聚合、记录观测和返回结构化证据，最终推荐判断由上层模型完成。

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
- 默认使用中国区商店；商店价格取决于 STEAM_STORE_COUNTRY 和 STEAM_STORE_LANGUAGE。

可选配置：

~~~dotenv
STEAM_MCP_HOST=127.0.0.1
STEAM_MCP_PORT=8789
STEAM_MCP_COMPACT_TOOLS=true
STEAM_MCP_LEGACY_TOOLS=false
STEAM_STORE_COUNTRY=cn
STEAM_STORE_LANGUAGE=english
STEAM_HISTORY_DB=data/steam_history.sqlite3
~~~

默认启用 12 个复合 tool。如果必须继续使用旧的细粒度工具，可设置：

~~~dotenv
STEAM_MCP_COMPACT_TOOLS=false
STEAM_MCP_LEGACY_TOOLS=true
~~~

### 切换 Steam 商店地区

商店地区使用 Steam 的两位国家/地区代码，通过 .env 中的 STEAM_STORE_COUNTRY 修改。修改后重启 MCP 服务才会生效。

中国区：

~~~dotenv
STEAM_STORE_COUNTRY=cn
STEAM_STORE_LANGUAGE=schinese
~~~

美国区：

~~~dotenv
STEAM_STORE_COUNTRY=us
STEAM_STORE_LANGUAGE=english
~~~

日本区：

~~~dotenv
STEAM_STORE_COUNTRY=jp
STEAM_STORE_LANGUAGE=japanese
~~~

其他常见代码包括 gb（英国）、de（德国）、fr（法国）。项目不会自动汇率换算；切换地区后，价格、货币、折扣和部分 Store 搜索结果都可能变化。

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
注：默认中国区。改变区服可在终端启动 MCP 之前输入：
$env:STEAM_STORE_COUNTRY="cn"
$env:STEAM_STORE_LANGUAGE="schinese"
其他国家或地区按相同方式修改代码即可。
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

确认 .env 中的地区和语言，例如：

~~~env
STEAM_STORE_COUNTRY=cn
STEAM_STORE_LANGUAGE=schinese
~~~

也可以改为：

~~~text
us
jp
...
~~~

修改后重启服务。项目不会自动做汇率换算。


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
