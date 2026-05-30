# Handoff: DaimsenGogo 供应链股票大屏 · 前端重构

## Overview
这是对「DaimsenGogo 供应链股票大屏」前端的整体视觉重构，覆盖 4 个界面：
1. **供应链看板**（主界面）— 左侧主题列表 + 顶部产业链环节筛选 + 个股 K 线卡片网格 + 板块概览。
2. **AI 分析** — 居中 hero 输入框 + 推荐标签 + 历史任务卡片。
3. **模型配置** — 供应商配置表单 + 可用模型列表（单选）。
4. **个股洞察**（弹窗）— 日线均线图（MA5/20/120/240）+ MACD 指标 + 结构解读面板。

重构提供两个可切换的**设计方向**、**深/浅两套主题**、**5 个强调色**、**卡片密度**，以及**深色星空 / 浅色沙丘**两张动态场景背景。约定：**涨=红、跌=绿**（中国习惯）。

---

## About the Design Files（重要）
本包内的 HTML / JSX / CSS 文件是**设计参考原型**（用浏览器内 React + Babel 跑的 mock），用于展示**最终视觉与交互意图**，**不是**要直接照搬进生产环境的代码。

你的任务是：**在本地 DaimsenGogo 项目现有的技术栈里，把这些设计 1:1 复刻出来**，复用项目已有的组件库、路由、状态管理、构建方式与代码规范。
- 原型用的是「单文件 + 多个 babel 脚本挂 window」的临时写法，**生产环境请改成正规模块化**（ES module / 真正的组件文件 / 预编译，不要用浏览器内 Babel）。
- 数据是本地 mock（`data.js`），生产环境请接入真实接口。
- TradingView 水印已去除，图表全部是自绘 SVG（见 Fidelity）。

## Fidelity
**高保真（hifi）**。颜色、字号、间距、圆角、动效都是最终值，请像素级复刻。下方「Design Tokens」给出全部精确数值；各界面布局见「Screens」。

---

## Tech / 架构约定
- **字体**：标题/品牌/数字用 `Space Grotesk`；数字与代码用等宽 `JetBrains Mono`（开 `font-variant-numeric: tabular-nums`）；中文用系统字体栈 `PingFang SC / Microsoft YaHei`。
- **主题机制**：在根元素 `<html>` 上设 `data-theme="dark|light"` 与 `data-dir="aurora|terminal"`，强调色通过 CSS 变量 `--accent-h`(色相) / `--accent-c`(彩度) 注入，全部色板由 `oklch()` 派生。`styles.css` 是单一事实来源。
- **场景背景**：用 `<body>` class 切换 `cosmos-on`（深色星空）/ `day-on`（浅色沙丘）。这两个 class 会把卡片/面板的 `--surface` 改成半透明并加 `backdrop-filter` 毛玻璃。
- **涨跌色**：`--up`(红) / `--down`(绿)，及其 soft 版本。**不要**用绿涨红跌。
- 原型里的「Tweaks 面板」（`tweaks-panel.jsx`）是 Claude 设计环境专用的调参工具，**生产环境不需要移植**——它对应的只是「方向 / 主题 / 强调色 / 密度 / 背景」这几个可配置项，你按产品需要保留其中一部分作为用户设置即可。

---

## Screens / Views

### 1. 顶部导航（全局）
- **布局**：高 60px，flex 三段式 —— 左：品牌（菱形 logo + `DaimsenGogo` 字标 + 副标「供应链股票大屏」）；中：实时时钟 + 休市状态点（绿点带脉冲）；右：胶囊分段控件 3 个 tab（供应链看板 / AI 分析 / 模型配置），选中 tab 填充强调色 + 轻投影。
- 背景：`color-mix(bg 70%, transparent)` + `backdrop-filter: blur(14px)`，底部 1px 边框。

### 2. 供应链看板
- **整体**：导航下方 flex 行 —— 左 Sidebar(260px 固定) + 右主区(flex-1, 纵向滚动, padding 24/28px)。
- **Sidebar**：标题「主题列表」+ 计数徽标；主题卡片列表（选中卡用 `--accent-soft` 底 + `--accent-line` 边 + 左侧圆点亮色，标题/2 行描述省略/「N 支 · 更新时间」）；底部「+ 新建分析」按钮（强调色渐变填充）。
- **主区头部**：H1 主题名(26px/700) + 「N 支成分股」徽标；下方 2 行描述(13.5px, `--text-dim`)。右侧并排「板块概览」面板(340px)：标题 + 「均 +X%」；涨跌广度条(红/灰/绿三段比例)；下排 上涨/平盘/下跌 计数(20px/700 上色) + 领涨股。
- **筛选标签**：flex wrap，胶囊 chip，每个带成分股计数小徽标；选中填充强调色。
- **卡片网格**：`grid, repeat(auto-fill, minmax(var(--card-min), 1fr)), gap 16px`（`--card-min`=290/330/390 对应紧凑/标准/宽松）。
- **个股卡片**（可点击 → 打开个股洞察）：
  - 头部：股票名(15.5px/600) + 右上代码(11px 等宽 faint，如 `SH:601958`)。
  - 价格行：价格(26px/600 等宽，按涨跌上色) + 涨跌药丸(`--up/down-soft` 底 + 同色字 + ▲/▼ 箭头)。
  - K 线迷你图：自绘 SVG 蜡烛图(高 132px)，含首日开盘价虚线参考线；涨蜡烛 `--up`(红)、跌蜡烛 `--down`(绿)。
  - 底部：1px 上边框，左「● 环节名」右「盘面洞察 →」(强调色)。
  - hover：Aurora 方向有强调色描边 + 辉光 + 顶部渐变高光线；Terminal 方向有强调色边框 + 轻微染色。

### 3. AI 分析
- 居中 max-width 1080，padding 顶 40px。
- Hero：小标签「AI 供应链分析」(强调色 0.22em 字距) + H1(32px/700, 含强调色高亮词) + 副文案。
- 输入条：`.panel` 容器，✦ 前缀 + 占位输入框 + 「开始分析」按钮(强调色渐变)。max-width 760 居中。
- 推荐标签：「试试：」+ 若干 chip（点击填入输入框）。
- 历史任务：标题「历史任务」+ 计数；卡片网格(minmax 340)，每卡：任务名 + 「● 已完成」绿色徽标 + 「N 环节 · 日期」+ 「继续」(强调色)/「删除」按钮。

### 4. 模型配置
- 居中 max-width 980，双栏 grid(1fr 1fr, gap 18)。
- 左「供应商配置」`.panel`：圆点+标题；字段 供应商名称 / Base URL(等宽) / API Key(password, 占位「已保存，留空则不修改」)；按钮「保存配置」(渐变)/「获取模型列表」(描边)。
- 右「可用模型」`.panel`：标题 + 「N 个」；模型列表项 = 单选圆点 + 等宽模型名 + 标签徽标 + 右侧上下文长度 + 选中项「当前使用」徽标。选中项 `--accent-soft` 底。

### 5. 个股洞察（弹窗 Modal）
- 全屏遮罩(`bg` 55% + `blur(6px)`)，点遮罩关闭；`modalIn` 入场动画；面板 `min(1240px,96vw) × max 92vh`。
- 头部：股票名(20px/700) + 「盘面洞察」+ 代码 + 价格(按涨跌上色) ··· 右侧 生成时间 + 「关闭 ✕」。
- Body 双栏 grid(1.6fr 1fr)，左侧 1px 分隔：
  - 左「图表区」(纵向滚动)：两个 ChartBlock —— ①「日线均线」自绘 SVG 折线(收盘价 + MA5/20/120/240，各有图例与颜色) + 3 条网格线带价标；②「指标看板」MACD 自绘 SVG(DIF/DEA 折线 + 红涨绿跌柱)。
  - 右「结构解读」：标题 + 「✦ 智能解盘」按钮；「大事提醒」强调色卡片；「综合解读」编号列表(技术面/筹码分布/股东结构/盈利趋势/大事提醒)。

---

## Interactions & Behavior
- 路由：顶部 3 tab 切换 dashboard / analysis / config（原型用本地 state，生产用项目路由）。
- 点个股卡片 → 打开个股洞察弹窗；点遮罩或「关闭」→ 关闭。
- 筛选标签点击 → 过滤当前主题成分股。
- Sidebar 主题点击 → 切换看板数据。
- 卡片入场：`fadeIn` 0.45–0.5s，网格卡片按 index×35ms 错峰。
- 实时时钟每秒更新（独立组件，不触发全局重渲染）。
- 动效缓动统一 `cubic-bezier(0.22,0.61,0.36,1)`。

## State Management（原型用到的状态）
- `route`: 'dashboard'|'analysis'|'config'
- `activeTheme`: 当前主题索引
- `insight`: 当前打开洞察的股票对象 | null
- 配置项（建议做成用户设置/持久化）：`dir`、`theme`、`accent`、`cardMin`、`cosmos`(场景背景开关)
- 数据获取：成分股列表、K 线、个股洞察（均线/MACD/结构解读）、模型列表、历史任务——全部替换 `data.js` 的 mock。

---

## Design Tokens（精确值，见 styles.css）
**主题/方向**：`data-theme=dark|light`，`data-dir=aurora|terminal`。圆角：aurora `--r:16px / --r-sm:10px`；terminal `--r:4px / --r-sm:3px`；胶囊 999px。

**强调色**（`--accent-h` 色相 / `--accent-c` 彩度，oklch 派生）：
- 靛蓝 h278 c0.17（默认）· 科技蓝 h232 c0.15 · 青碧 h196 c0.13 · 琥珀 h70 c0.15 · 品红 h350 c0.16
- `--accent = oklch(0.64 c h)`；`--accent-bright = oklch(0.72 c h)`；soft = 同色 /0.14；line = 同色 /0.4。

**深色 tokens**（节选）：`--bg oklch(0.16 0.018 268)`、`--surface oklch(0.205 0.02 268)`、`--text oklch(0.96 0.006 268)`、`--text-dim 0.74`、`--text-faint 0.56`、`--up oklch(0.68 0.2 24)`(红涨)、`--down oklch(0.76 0.16 158)`(绿跌)。均线色 ma5 橙/ma20 蓝/ma120 紫/ma240 绿。

**浅色 tokens**（节选）：`--bg oklch(0.97 0.006 268)`、`--surface #fff`、`--text oklch(0.24 0.02 268)`、`--up oklch(0.56 0.21 26)`、`--down oklch(0.56 0.14 158)`。

**场景毛玻璃**：`body.cosmos-on` 把 surface 改 `rgba(15,21,44,~0.6)` + `backdrop-filter: blur(13px)`；`body.day-on` 改 `rgba(255,255,255,~0.68)` + `blur(14px)` + 卡片投影 + 标题白色柔光描边。

**字体**：`--font-sans: "Space Grotesk", "PingFang SC", ...`；`--font-mono: "JetBrains Mono", ...`；`--font-cjk: "PingFang SC", "Microsoft YaHei", ...`。最小字号：1920 大屏 ≥24px 视场景，常规 UI 文本 11–15.5px（数据密集型）。

---

## 动态场景背景（两套，按主题切换）
- **深色 = 星空地球冰原**（`cosmos.jsx` + `assets/cosmos.png`）：动效层 = 流星划过(5) / 星点闪烁(72) / 地球辉光呼吸 / 地球暗面城市灯闪烁(14) / 冰面中央反光 + 斜向扫光 / 整体极缓慢推近。
- **浅色 = 白昼行星沙丘**（`dayscene.jsx` + `assets/day.png`）：动效层 = 天光辉光呼吸 / 薄云横向飘移(4 层) / 行星云带流动 + 金色边缘光晕 / 沙纹扫光 / 风沙微粒(26) / 整体缓慢推近。
- 关键：两张图构图一致（巨大天体在上方约 50%×28–30%，地平线在下方，吉祥物在左右下角），动效层用百分比定位，与卡片布局对齐。生产环境建议把动效层做成可复用的背景组件，并提供「关闭场景背景」选项（低端设备/可读性优先时）。
- 这两张背景图是**用户自备素材**（见 Assets），版权与替换由产品方决定。

## Assets
- `assets/cosmos.png`（1672×941）— 深色夜空地球冰原背景，用户上传。
- `assets/day.png`（1916×821）— 浅色白昼行星沙丘背景，用户上传。
- Logo 为内联 SVG（菱形 + 内框 + 中心圆点），见 `components.jsx` 的 `Logo`，可直接复用或替换为正式品牌资产。
- 图标极少，未使用第三方图标库；箭头/圆点等为字符或简单 SVG。

## Files（本包内）
- `PIXEL_SPEC.md` — **逐组件像素标注**（尺寸/字重/间距/圆角/状态的精确值）。
> 视觉参考：直接在浏览器里打开 `DaimsenGogo 重构.html` 跑起来（活原型，右下「Tweaks」可切换方向/主题/场景，比静态图更准）。本地用 Claude Code 时建议让它也打开此文件实时比对；需要静态图自行截屏即可。
- `DaimsenGogo 重构.html` — 入口（脚本加载顺序、App 路由、Tweaks 配置、主题/场景应用逻辑）。
- `styles.css` — **全部设计 token、主题、方向、动效 keyframes、场景背景与毛玻璃**（最重要的参考）。
- `data.js` — mock 数据 + K线/均线/MACD 生成函数（替换为真实接口）。
- `charts.jsx` — 自绘 SVG 图表：`CandleChart`(蜡烛) / `Sparkline` / `MALineChart`(均线) / `MACDChart`。
- `components.jsx` — `Logo` / `MarketStatus`(时钟) / `Nav` / `Sidebar` / `StockCard`。
- `screens.jsx` — `Dashboard`(含板块概览) / `AIAnalysis`。
- `screens2.jsx` — `ModelConfig` / `InsightModal`(个股洞察) / 表单字段。
- `cosmos.jsx` / `dayscene.jsx` — 两套动态场景背景层。
- `tweaks-panel.jsx` — 设计环境调参工具（生产不必移植）。

---

## 给本地 Claude Code 的建议提示词（可直接粘贴）
> 我在 `design_handoff_dashboard_redesign/` 放了一份 UI 重构设计交接包（HTML/JSX/CSS 原型 + 说明）。请先读 `design_handoff_dashboard_redesign/README.md`，再读 `styles.css`（设计 token 的唯一来源）和各 `*.jsx`。然后在**我现有的 DaimsenGogo 项目技术栈**里，按高保真把这 4 个界面（供应链看板 / AI 分析 / 模型配置 / 个股洞察弹窗）复刻出来：
> - 复用项目已有的路由、状态管理、组件库与构建工具；**不要**把浏览器内 Babel 单文件原型直接搬进来，要改成项目规范的模块化组件。
> - 严格沿用 README 里的设计 token、布局与「涨=红 跌=绿」约定；颜色用 oklch + CSS 变量，主题用 `data-theme`/`data-dir` 机制。
> - 图表沿用自绘 SVG 方案（或接入项目已用的图表库，但视觉对齐 README）。
> - 数据接我项目真实接口，替换 `data.js` 的 mock。
> - 先给我一个实施计划和文件改动清单，确认后再动手；逐界面提交，方便我 review。
