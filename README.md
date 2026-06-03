# DaimsenGogo 股票供应链大屏

## 项目简介

DaimsenGogo 是一个面向 A 股产业链研究场景的 AI 分析与可视化平台。用户输入一个产业主题，例如“苹果手机供应链”“宁德时代电池供应链”“华为昇腾供应链”，系统会调用大模型进行供应链拆解，生成主题、产业分类、相关上市公司及业务说明，并在看板中展示实时行情、涨跌幅、近一个月日 K 线和主题分类结构。

项目采用前后端分离架构：前端使用 React + TypeScript + Vite 构建交互式大屏，后端使用 FastAPI 提供 AI 分析、主题管理、行情代理、模型配置、历史任务和个股盘面洞察接口。数据持久化以本地 JSON 文件为主，适合演示、学习、面试项目复盘和个人研究使用。

## 核心功能

### 1. AI 供应链分析

- 支持用户输入自然语言主题，自动生成供应链分析结果。
- 后端通过 Plan-and-Execute + ReAct 混合流程组织大模型分析。
- 使用 SSE 流式返回分析进度，前端可实时展示执行过程、等待用户确认并继续执行。
- 分析任务会保存检查点、事件流和最终结果，便于历史回看和调试。
- 自动沉淀分析结果为“主题”，供后续看板复用。

### 2. 供应链主题看板

- 左侧展示已保存主题列表。
- 支持切换主题、保留当前主题状态、删除主题。
- 看板按供应链分类展示相关股票。
- 支持“全部视图”和分类视图，方便快速查看主题整体结构。

### 3. 股票实时行情

- 对主题下股票按代码获取实时行情。
- 现价、涨跌额、涨跌幅、开盘价、最高价、最低价和成交额优先来自雪球行情接口。
- 当雪球返回空数据、登录态失效或触发风控时，后端会依次尝试 AkShare 实时行情接口和 AkShare 历史日线接口兜底，避免看板价格长期显示为 `--`。
- 前端每 30 秒轮询一次当前主题股票行情。
- 后端对实时行情设置短缓存与并发限制，避免频繁请求外部数据源。

### 4. K 线与均线图

- 每只股票展示近一个月日 K 线走势。
- K 线数据固定取最近 22 个交易日。
- 使用前复权日线数据，适合在卡片中展示近期趋势。
- 前端使用 IntersectionObserver 懒加载 K 线，只有进入视口附近的图表才会请求数据。
- 卡片蜡烛图、个股洞察的均线图与 MACD 图均为自绘 SVG（红涨绿跌、含日期 X 轴），不依赖第三方图表库。
- 个股盘面洞察中额外展示近一年收盘价曲线，以及 MA5、MA20、MA120、MA240 均线。

### 5. 模型配置管理

- 支持配置大模型 API 地址、API Key 和模型名称。
- 支持 OpenAI 协议兼容的大模型服务，不限定 OpenAI 官方接口。
- 配置会同步写入 `.env`，前端“模型配置”页也会读取 `.env` 的最新值。
- AI 分析前会校验模型配置是否完整。
- 支持网页搜索开关与 Tavily API Key 配置；关闭后即使 `.env` 中存在 `TAVILY_API_KEY`，分析流程也不会使用 `web_search`。

### 6. 历史任务管理

- 保存 AI 分析任务执行记录，状态机覆盖 `pending / running / paused / failed / completed`。
- 支持查看、继续（从断点恢复）和删除历史分析任务，方便复盘分析过程。
- 任务恢复有三重保护：SSE 客户端断开（刷新/关页）时自动将 `running` 复位为 `paused`；服务重启时复位残留的 `running` 任务；前端对长时间无更新仍显示 `running` 的任务也放开「继续/删除」，避免任务卡死无法恢复。

### 7. 个股盘面洞察

- 用户在看板中点击个股后才触发洞察取数，不在后台预加载。
- 后端并行调取历史收盘价、股东人数、财报和大事提醒，并在本地计算指标。
- 历史收盘价优先使用雪球 K 线；雪球失败时回退 AkShare 腾讯日线和新浪日线，用于保障 MA / MACD 图表可用。
- 若外部接口均失败，后端会在 `data_errors` 中返回失败原因，前端在盘面洞察右侧展示“接口取数异常”，提示检查数据接口。
- 左侧展示收盘价均线、DIF / DEA / MACD、股东人数变化、归母净利润与同比、筹码分布等图表。
- 右侧默认展示纯数据规则摘要，点击“智能解盘”后才将清洗后的结构化数据发送给大模型生成“综合解读”。
- “智能解盘”结果在前端缓存，点击“返回”可回到本地规则摘要，再次点击不会重复请求大模型。

### 8. 筹码分布与本地指标计算

- 筹码分布不依赖第三方成品接口，采用 K 线 + 换手率 + CYQ 本地算法计算。
- 默认口径为 120 个交易日计算窗口、150 个价格档、210 根日 K 预热、最近 90 个交易日快照。
- 输出平均成本、获利比例、70/90 成本区间、集中度、支撑位、压力位和横向柱状分布图。
- 筹码分布作为技术面估算指标使用，不代表真实账户持仓成本。

## 产业链生成链路

当前项目的产业链生成以“用户主题输入 -> 后端任务编排 -> 股票候选验证 -> 人工确认 -> 主题保存”为主线。核心链路如下：

1. 用户在前端“AI分析”页面输入产业链主题，前端通过 `POST /api/analysis-tasks/run` 创建分析任务。
2. 后端 `analysis_task_router` 生成 `analysis_xxx` 任务 ID，将任务状态、事件流、检查点和结果写入 `data/analysis_tasks/`。
3. `plan_execute_react_loop` 进入固定 SOP：候选发现、业务确认、候选补全、结果分组、代码校验、最终组装。
4. Agent 会调用本地工具检索股票：`search_stocks` 从 A 股股票基础列表中查找候选，`get_company_info` 补充公司业务信息，`verify_stock_code` 校验代码与市场前缀。
5. `web_search` 在启用后会先参与规划前证据校准，用于识别真实主题边界和直接命中的A股候选；随后仍可在“业务确认”步骤补强公开网页证据，不参与代码校验或最终组装。
6. A 股股票基础列表来自 AkShare 的全市场接口，并缓存到 `data/task_cache/_shared/stock_list.json`；外部接口异常时优先使用本地缓存。
7. 前端通过 SSE 接收任务事件，展示推理过程、候选股票、确认节点和最终主题结构。
8. 用户确认或调整结果后，后端将最终 `Theme` 保存到 `data/themes/{theme_id}.json`，看板页读取该主题并展示分类股票、行情和图表。

这条链路的重点是：大模型负责产业链理解和结构化推理，本地工具负责股票代码、公司信息和数据一致性校验，最终结果以本地 JSON 主题文件沉淀，便于后续看板复用和二次开发。

## 外部接口与数据源

### 1. 前端调用本项目后端接口

| 用途 | 方法 | 接口 |
|---|---:|---|
| 批量实时行情 | GET | `/api/stocks/quotes?codes=SZ:000725,SH:600000&task_id=xxx` |
| 股票卡片近一月 K 线 | GET | `/api/stocks/kline?code=SZ:000725&period=daily&count=22&task_id=xxx` |
| 近一年收盘价 | GET | `/api/stocks/close-history?code=SZ:000725&count=250` |
| 个股盘面洞察 | GET | `/api/stocks/diagnosis?code=SZ:000725&name=京东方A` |
| 智能解盘 | POST | `/api/stocks/diagnosis/enhance?code=SZ:000725&name=京东方A` |
| 股票搜索 | GET | `/api/stocks/search?q=京东方&task_id=xxx` |
| 模型配置读取 | GET | `/api/config/` |
| 模型配置保存 | PUT | `/api/config/` |
| 拉取模型列表 | POST | `/api/config/fetch-models` |
| 选择模型 | PUT | `/api/config/select-model` |
| 产业链分析任务 | POST | `/api/analysis-tasks/run` |
| 继续分析任务 | POST | `/api/analysis-tasks/{task_id}/continue` |
| 历史任务列表 | GET | `/api/analysis-tasks/` |
| 历史任务详情 | GET | `/api/analysis-tasks/{task_id}` |
| 主题列表 | GET | `/api/themes/` |
| 主题详情 | GET | `/api/themes/{theme_id}` |

### 2. 雪球接口

| 用途 | 接口 |
|---|---|
| 预热 Cookie | `https://xueqiu.com/S/{symbol}` |
| 实时行情 | `https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}&extend=detail` |
| 历史 K 线 / 收盘价 | `https://stock.xueqiu.com/v5/stock/chart/kline.json` |
| 股东人数 | `https://stock.xueqiu.com/v5/stock/f10/cn/holders.json?symbol={symbol}&count=20` |
| 财务指标 | `https://stock.xueqiu.com/v5/stock/finance/cn/indicator.json?symbol={symbol}&type=Q4&is_detail=true&count=5` |
| 大事提醒 | `https://stock.xueqiu.com/v5/stock/screener/event/list.json?symbol={symbol}&page=1&size=200` |

雪球 symbol 格式是 `SZ000725`、`SH600000` 这种。

### 3. 东方财富接口

| 用途 | 接口 |
|---|---|
| 筹码分布输入 K 线 | `https://push2his.eastmoney.com/api/qt/stock/kline/get` |

当前参数大概是：

```text
secid=0.000725
fields1=f1,f2,f3,f4,f5,f6
fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61
klt=101
fqt=0
end=YYYYMMDD
lmt=210
```

这里取 `open/high/low/close/volume/amount/turnoverRate`，再用本地 CYQ 算法算筹码分布。

### 4. AkShare / Baostock 本地封装

| 用途 | 调用 |
|---|---|
| A 股股票列表 | `ak.stock_zh_a_spot_em()` |
| 实时行情兜底 | `ak.stock_zh_a_spot()` / `ak.stock_zh_a_spot_em()` |
| 股票近一月 K 线兜底 | `ak.stock_zh_a_hist_tx(symbol="sz000725", adjust="qfq")` |
| 历史收盘价兜底 | `ak.stock_zh_a_hist_tx(symbol="sz000725", adjust="qfq")` / `ak.stock_zh_a_daily(symbol="sz000725", adjust="qfq")` |
| 报价非实时兜底 | `ak.stock_zh_a_hist_tx(...)` / `ak.stock_zh_a_daily(...)` 取最近两根日 K 计算涨跌 |
| 公司基础信息 | `ak.stock_individual_info_em(symbol="000725")` |
| 股票列表兜底 | `baostock.query_stock_basic()` |

行情链路说明：

1. 股票卡片现价：先请求雪球 `quote.json`；失败后请求 AkShare 实时行情；实时行情也失败时，使用 AkShare 历史日线最近两根 K 线计算非实时涨跌。
2. 股票卡片近一月 K 线：先请求雪球 K 线；失败后使用 AkShare 腾讯日线。
3. 个股盘面洞察 MA / MACD：先请求雪球历史收盘价；失败后依次使用 AkShare 腾讯日线、AkShare 新浪日线。
4. 股东人数、财务指标、大事提醒仍来自雪球 F10 相关接口；若雪球取数失败，会记录到 `data_errors` 并在前端提示。
5. A 股股票列表：启动时后台线程优先用 AkShare 全市场接口；失败后用 Baostock `query_stock_basic()` 子进程兜底（隔离 `bs.login()` 卡死风险，子进程超时 40 秒）。

### 5. 网页搜索接口

| 用途 | 接口 |
|---|---|
| 公开网页证据补强 | `https://api.tavily.com/search` |

网页搜索由 `WEB_SEARCH_ENABLED` 控制：

- `WEB_SEARCH_ENABLED=true` 且配置了 `TAVILY_API_KEY` 时，规划前证据校准和业务确认步骤可使用 `web_search`
- `WEB_SEARCH_ENABLED=false` 时，即使 `.env` 里存在 `TAVILY_API_KEY`，分析流程也不会调用 `web_search`

### 6. 大模型接口

| 用途 | 接口 |
|---|---|
| 获取模型列表 | `{LLM_BASE_URL}/models` |
| 产业链分析 / 智能解盘 | OpenAI SDK 调用 `{LLM_BASE_URL}/chat/completions` |

配置来自 `.env` 或前端“模型配置”页：

```text
LLM_PROVIDER_NAME
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
WEB_SEARCH_ENABLED
TAVILY_API_KEY
```

## 主题与任务数据

### 主题数据

主题数据来自 AI 分析结果并保存为本地 JSON 文件，结构包括：

- 主题 ID
- 主题名称
- 主题描述
- 供应链分类
- 每个分类下的股票列表
- 股票业务说明和供应链占比

### 分析任务数据

- 历史分析任务保存在 `data/analysis_tasks/`。
- 每个任务会保留事件流、检查点、步骤状态和最终结果。
- 任务恢复时会根据当前配置重新裁剪允许的工具集合，避免旧任务沿用已关闭的 `web_search` 权限。

### 股票列表缓存

A 股股票基础列表会被缓存到 `data/task_cache/_shared/stock_list.json`。

更新机制如下：

1. 后端启动时在 lifespan 中通过**后台守护线程**初始化股票列表，不阻塞后端就绪。当天共享缓存有效时只加载缓存，缓存缺失或过期时才触发远端拉取。
2. 远端拉取先尝试 AkShare 全市场接口（最多 2 次）；拉取成功会立即写入 `data/task_cache/_shared/stock_list.json`。
3. 如果 AkShare 拉取失败，会尝试 Baostock 兜底。Baostock 采用子进程隔离调用（避免 `bs.login()` 卡死主进程），子进程超时为 40 秒，最多 2 次。
4. 如果两个外部源都失败，则优先返回本地缓存；如果本地缓存也不存在，则返回空结果。
5. 缓存是共享缓存，不按任务单独隔离，因此适合做全局股票检索底座。
6. 进程内搜索缓存默认保留 1 小时，避免同一任务内重复读取整张股票表。
7. 后台初始化期间（列表尚未拉好）查询返回空列表，由运行期兜底逻辑承接；因此删除共享缓存后重启，建议等控制台无 AkShare/Baostock warning 再发起分析。

## 缓存机制

### 1. 股票行情缓存

- 实时行情缓存：5 秒
- 近一月 K 线缓存：1 小时
- 历史收盘价缓存：1 小时
- 股票搜索缓存：1 小时

这些缓存都存在于后端进程内，主要用于减少对雪球和 AkShare 的重复请求。

### 2. 任务级缓存

- `data/task_cache/{task_id}/` 目录用于保存任务相关的 AkShare 结果缓存。
- 包括实时行情、K 线、公司信息等缓存文件。
- 任务完成或主题删除后，相关缓存会被清理。

### 3. 个股洞察缓存

- “智能解盘”结果在前端缓存。
- 点击“返回”后可回到本地规则摘要，不会重复请求大模型。

### 4. `.env` 配置缓存

- 模型配置和网页搜索配置会同步写入 `.env`。
- Tavily API Key 不会回显明文，只保留是否已配置的状态。
- 关闭网页搜索开关时，分析流程即使读到 `TAVILY_API_KEY` 也不会启用 `web_search`。

## 技术栈

### 前端

| 技术 | 用途 |
| --- | --- |
| React 19 | 页面组件与状态驱动渲染 |
| TypeScript | 类型约束，提高代码可维护性 |
| Vite | 前端开发服务器与构建工具 |
| Zustand | 主题、行情、配置与外观设置状态管理 |
| React Router | 页面路由与主题详情路由 |
| Axios | API 请求封装 |
| 自绘 SVG 图表 | 蜡烛 / 均线 / MACD 等图表，不依赖第三方图表库 |
| Tailwind CSS v4 | 工具类样式 |
| oklch 设计 token | 主题/方向/强调色/场景背景的唯一视觉事实来源 |
| Headless UI | 外观设置等无样式可访问组件 |
| react-hot-toast | 全局轻量通知 |

### 后端

| 技术 | 用途 |
| --- | --- |
| FastAPI | API 服务框架 |
| Uvicorn | ASGI 服务运行器 |
| Pydantic | 请求和响应数据模型 |
| sse-starlette | SSE 流式事件返回 |
| OpenAI SDK | 兼容 OpenAI 协议的大模型调用 |
| AkShare | A 股日 K 与股票基础信息获取 |
| requests | 雪球、东方财富等 HTTP 请求 |
| 本地 JSON | 主题、配置、历史任务和缓存持久化 |

## 目录结构

```text
DaimsenGogo/
├── backend/                    # FastAPI 后端
│   ├── agent/                  # ReAct / Plan-and-Execute 分析逻辑
│   ├── models/                 # Pydantic 数据模型
│   ├── routers/                # API 路由
│   ├── services/               # 文件服务、行情服务、诊断服务、数据源适配
│   └── main.py                 # FastAPI 入口
├── frontend/                   # React 前端
│   ├── public/                 # favicon / 场景背景图等静态资源
│   └── src/
│       ├── api/                # API 请求封装
│       ├── components/
│       │   ├── charts/         # 自绘 SVG 图表（蜡烛 / 均线 / MACD）
│       │   ├── dashboard/      # 看板卡片、侧栏、个股洞察弹窗
│       │   ├── layout/         # 导航、品牌标志、场景背景、外观设置
│       │   ├── analysis/       # AI 分析输入与执行流
│       │   └── config/         # 模型配置表单与模型列表
│       ├── hooks/              # 行情轮询等 Hooks
│       ├── pages/              # 页面入口
│       ├── stores/             # Zustand 状态（含 uiSettingsStore 外观设置）
│       └── index.css           # 设计 token / 主题 / 场景背景（唯一视觉来源）
├── logo/                       # 定稿品牌标志 SVG 与使用说明
├── design_handoff_dashboard_redesign/  # UI 重构设计交接包（原型 + 像素标注）
├── scripts/                    # 启动脚本与测试脚本
│   ├── launcher.py             # 单窗口启动前后端
│   ├── start.bat               # Windows 一键启动脚本
│   ├── start.sh                # Unix 启动脚本
│   └── test_xq_quote.py        # 雪球接口临时测试脚本
├── data/                       # 本地数据目录，运行后生成或更新
│   ├── themes/                 # 供应链主题数据
│   ├── analysis_tasks/         # AI 分析历史任务
│   ├── task_cache/             # 行情、K线、股票列表缓存
│   └── config.json             # 模型配置兼容文件
├── .env.example                # 大模型配置示例
└── README.md
```

## 使用方式

### 1. 环境准备

后端依赖 Python 3.9+ 环境，前端依赖 Node.js 18+ 与 npm。

推荐使用项目自带的一键脚本：

- Windows：`scripts/start.bat`
- Unix / macOS / Linux：`bash scripts/start.sh`

脚本会自动：

1. 检查或创建 Python 环境
2. 安装后端依赖
3. 安装前端依赖
4. 启动统一入口 `scripts/launcher.py`

如果需要手动安装，也可以使用本地虚拟环境 `.venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

也可以使用 conda 环境（如沿用项目约定的 `env_reactAgent`）：

```bash
conda run -n env_reactAgent pip install -r backend/requirements.txt
```

安装前端依赖：

```bash
cd frontend
npm install
```

复制大模型配置示例：

```bash
cp .env.example .env
```

按需填写：

```bash
LLM_PROVIDER_NAME=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
WEB_SEARCH_ENABLED=false
TAVILY_API_KEY=
```

也可以在前端“模型配置”页填写并保存，后端会同步更新 `.env`。`.env` 中的 API Key 不应提交到 Git。

### 2. 一键启动

#### Windows

```bash
scripts/start.bat
```

#### Unix / macOS / Linux

```bash
bash scripts/start.sh
```

统一启动器会拉起：

- 后端：`http://localhost:8000`
- 前端：`http://localhost:5173`
- API 文档：`http://localhost:8000/docs`

### 3. 手动启动后端

```bash
# .venv（已激活）
python -m uvicorn backend.main:app --port 8000 --host 0.0.0.0
# 或 conda
conda run -n env_reactAgent python -m uvicorn backend.main:app --port 8000 --host 0.0.0.0
```

### 4. 手动启动前端

```bash
cd frontend
npm run dev
```

### 5. 前端构建

```bash
cd frontend
npm run build
```

## 基本操作流程

1. 打开前端页面 `http://localhost:5173`。
2. 进入“模型配置”页面，填写 API 地址、API Key 和模型名称，或直接维护 `.env`。
3. 如需网页搜索证据补强，在同页开启 `web_search` 并填写 Tavily API Key。
4. 进入“AI分析”页面，输入供应链主题。
5. 等待 AI 分析过程流式输出，按页面提示确认候选股票和最终结果。
6. 保存主题后进入“供应链看板”，查看主题分类、股票卡片、实时行情和近一个月 K 线。
7. 点击任意个股，打开“盘面洞察”，后端会实时拉取并计算该股诊断数据。
8. 如需大模型综合分析，点击右侧“智能解盘”，返回后可回到本地规则摘要。
9. 后续可在左侧主题列表中切换或删除主题。

## API 概览

| 模块 | 方法与路径 | 说明 |
| --- | --- | --- |
| AI 分析任务 | POST `/api/analysis-tasks/run` | 启动供应链分析任务，返回 SSE 事件流 |
| AI 分析任务 | POST `/api/analysis-tasks/{task_id}/continue` | 用户确认后继续执行任务 |
| AI 分析任务 | GET `/api/analysis-tasks/` | 查询历史分析任务 |
| AI 分析 | POST `/api/analysis/run` | 旧版直接流式分析入口 |
| 主题管理 | GET `/api/themes/` | 获取主题摘要列表 |
| 主题管理 | GET `/api/themes/{theme_id}` | 获取主题详情 |
| 主题管理 | POST `/api/themes/` | 创建主题 |
| 主题管理 | PUT `/api/themes/{theme_id}` | 更新主题 |
| 主题管理 | DELETE `/api/themes/{theme_id}` | 删除主题 |
| 行情数据 | GET `/api/stocks/quotes` | 批量获取实时行情 |
| 行情数据 | GET `/api/stocks/kline` | 获取近一个月日 K |
| 行情数据 | GET `/api/stocks/close-history` | 获取历史收盘价 |
| 个股诊断 | GET `/api/stocks/diagnosis` | 获取盘面洞察数据和本地规则摘要 |
| 个股诊断 | POST `/api/stocks/diagnosis/enhance` | 调用大模型生成智能解盘 |
| 股票检索 | GET `/api/stocks/search` | 从本地 A 股列表检索股票 |
| 模型配置 | `/api/config/*` | 读取和保存模型配置 |

## 性能优化设计

### 1. 行情与主题解耦

主题数据只保存 AI 生成的供应链结构，不直接保存实时行情。行情进入看板后按股票代码请求，避免主题切换时重复生成分析结果。

### 2. 指定股票行情获取

实时行情不再全量下载 A 股行情，而是只请求当前主题下的股票代码，降低外部接口压力和等待时间。

### 3. 并发控制

后端对外部行情请求设置并发上限：

- 实时行情并发：5
- K 线请求并发：3

这样可以避免大量 `asyncio.to_thread` 任务挤占线程池，影响模型配置、历史任务等轻量接口。

### 4. 多级缓存

- 实时行情缓存：5 秒
- 近一月 K 线缓存：1 小时
- 历史收盘价缓存：1 小时
- 股票搜索缓存：1 小时
- `stock_list.json` 共享缓存：作为 A 股基础列表底座，优先复用本地缓存

### 5. 失败降级

- 雪球实时行情失败时，回退 AkShare 实时行情；AkShare 实时行情失败时，再用 AkShare 历史日线生成非实时兜底报价。
- 雪球 K 线或历史收盘价失败时，回退 AkShare 腾讯日线和新浪日线。
- 若外部行情接口全部失败，后端返回失败原因，前端在盘面洞察中显示“接口取数异常”。
- AkShare 拉取股票列表失败时，使用 Baostock 兜底。
- `web_search` 未启用或未配置密钥时，分析流程自动跳过该工具。
- 个股洞察的“智能解盘”失败后，前端仍保留本地规则摘要。

## 运行与配置建议

- 首次运行建议直接使用 `scripts/start.bat` 或 `scripts/start.sh`。
- 如果需要更稳定的环境，建议固定使用 conda 环境 `env_reactAgent`。
- `.env` 中的密钥只适合本地使用，不要提交到版本库。
- 如果网页搜索太慢，可以在“模型配置”页关闭 `web_search`，分析流程会自动只使用本地工具链。

## 许可与使用说明

本项目依赖多个公开数据源和第三方接口，适合研究、演示和学习用途。请遵守对应数据源的使用规则与频率限制。
