# 逐组件像素标注 · PIXEL SPEC
> 配合 `README.md` 使用。所有数值取自原型源码（`components.jsx` / `screens.jsx` / `screens2.jsx` / `charts.jsx` / `styles.css`）。颜色见 README「Design Tokens」；此处给出**尺寸 / 字重 / 间距 / 圆角 / 状态**的精确值。单位 px，除非标注。约定 **涨=红(`--up`) 跌=绿(`--down`)**。

## 全局
- 缓动统一 `--ease: cubic-bezier(0.22,0.61,0.36,1)`。
- 圆角：Aurora `--r=16 / --r-sm=10`；Terminal `--r=4 / --r-sm=3`；胶囊 999。
- 入场：`fadeIn` from{opacity:0; translateY(8)} 0.45–0.5s；列表错峰 index×35ms。
- 等宽数字：所有价格/百分比/代码/时间用 `--font-mono` + `tabular-nums`。
- 滚动条：宽 10，thumb `--border-strong` 圆角 99，3px 透明内边距。

---

## 顶部导航 Nav（高 60）
- 容器：`height 60`，`padding 0 22`，下边框 1px `--border`，`backdrop-filter: blur(14)`，背景 `color-mix(bg 70%, transparent)`，`z-index 20`。flex `space-between`，三段最小宽各 240。
- **品牌区**（gap 11）：
  - Logo：内联 SVG 24×24 —— 外层 45° 圆角方块(透明度0.18 强调色) + 内层描边方块(stroke `--accent-bright` 2px) + 中心圆点 r2.6。
  - 字标：`Space Grotesk` 17/700，字距 -0.01em，`Daimsen` 常规 + `Gogo` 用 `--accent-bright`。
  - 副标：10.5px，`--text-faint`，字距 0.32em，上间距 1。
- **中段 MarketStatus**（gap 14）：休市点 7×7 圆，`--down` 底 + 4px `--down-soft` 光环 + `pulse 2s` 脉冲；「休市」12.5/600；分隔点 透明度0.3；时钟 `13.5px 等宽` 字距 0.02em，秒数透明度 0.5，每秒更新。
- **右段 Tab 胶囊组**：容器 `--surface-2` 底 + 1px `--border`，`padding 4`，圆角 999，min-width 240，右对齐。每个 tab：13.5/600，`padding 8/16`，圆角 999；**选中**=白字 + `--accent` 底 + `0 6px 18px -8px --accent` 投影；未选 `--text-dim` 透明底。过渡 0.2s。

---

## 供应链看板 Dashboard

### Sidebar（宽 260 固定）
- 容器：右边框 1px，背景 `color-mix(surface 40%, transparent)`，纵向 flex 满高。
- 头部：`padding 18/18/12`，「主题列表」12/700 字距 0.18em 大写 `--text-faint`；右侧计数徽标 11px 等宽 `--surface-2` 底 `padding 2/8` 圆角 99。
- 列表：`padding 0 12`，gap 8，纵向滚动。
- **主题卡**（`.card`）：`padding 13/14`，gap 6。
  - 行1：圆点 6×6（选中 `--accent-bright`，否则 `--text-faint`）+ 名称 13.5/600。
  - 描述：11.5px，`--text-faint`，line-height 1.5，2 行省略（`-webkit-line-clamp:2`）。
  - 行3：「N 支」10.5 等宽 + 「· 更新时间」10.5。
  - **选中态**：底 `--accent-soft`，边 `--accent-line`，名称用 `--text`。
- 底部按钮「+ 新建分析」：`padding 12` 满宽，圆角 `--r-sm`，13.5/600 白字，背景 `linear-gradient(135deg, --accent-bright, --accent)`，投影 `0 10px 26px -12px --accent`；按下 `scale(0.98)`。

### 主区（padding 24/28/40，纵向滚动）
- **头部行**（flex space-between，gap 32，下间距 20）：
  - 左块 max-width 760：H1 主题名 **26/700** 字距 -0.01em；右侧「N 支成分股」徽标 11/600 `--accent-bright` 字、`--accent-soft` 底、1px `--accent-line` 边、`padding 4/10` 圆角 99；下方描述 **13.5px** line-height 1.7 `--text-dim`，`text-wrap: pretty`。
  - 右块「板块概览」`.panel` 宽 **340**，`padding 16/18`，gap 14：
    - 行1：「板块概览」11.5/700 字距 0.16em + 右「均 ±X%」13/700 上色。
    - 广度条：高 **8**，圆角 99，三段 = 上涨`--up` / 平盘`--text-faint` / 下跌`--down`，宽度按占比。
    - 行3：三组统计 数值 **20/700** 上色 + 标签 11px `--text-faint`；最右「领涨」块左侧 1px 分隔 + padding-left 16。
- **筛选 chip 行**（flex wrap，gap 8，下间距 22）：每个 12.5/600，`padding 7/13`，圆角 999，1px 边；内嵌计数徽标 10.5 等宽 `padding 1/6` 圆角 99。**选中**=白字 + `--accent` 底 + `--accent-line` 边，徽标底 `rgba(255,255,255,0.18)`；未选 `--surface` 底 + `--text-dim`。过渡 0.2s。
- **卡片网格**：`grid; repeat(auto-fill, minmax(var(--card-min),1fr)); gap 16`；`--card-min`=290/330/390。

### 个股卡片 StockCard（`.card`，可点击）
- 结构：纵向 flex，整卡 button，`overflow hidden`。
- 头部块 `padding 14/16/8`，gap 10：
  - 行1：名称 **15.5/600** `--text`；右上代码 11px 等宽 `--text-faint`（上间距 3）。
  - 行2（baseline 对齐，gap 10）：价格 **26/600** 等宽 行高1 按涨跌上色；涨跌药丸 = `--up/down-soft` 底 + 同色 12.5/700 等宽 + ▲/▼(10px)，`padding 3/8` 圆角 `--r-sm`，gap 3。
- K 线图：`padding 0 6`，`CandleChart` 高 **132**（见图表）。
- 底部条：上边框 1px，`padding 9/16/13`，上间距 4，space-between：左「● 环节」11px `--text-faint`（圆点 5×5 `--accent-bright`）+ 右「盘面洞察 →」11/600 `--accent-bright` 透明度0.9。
- **hover**：Aurora = 边框 `--accent-line` + 阴影 `0 0 0 1px accent-line, 0 24px 60px -30px accent` + 顶部 1px 渐变高光线淡入；Terminal = 边框 `--accent` + 背景染 `color-mix(surface 88%, accent 12%)`。过渡 0.25s。

---

## 图表 charts.jsx（全部自绘 SVG，viewBox 拉伸 `preserveAspectRatio=none`，线性图除外）

### CandleChart（卡片蜡烛，viewBox 600×H，默认 H=132/150）
- padX 10，padTop/Bot 10。按 `candles` 计算 hi/lo（含上下影线）映射。
- 步距 = 内宽 / 根数；蜡烛体宽 = max(3, 步距×0.62)。
- 影线：1.4px；实体：rect 圆角 0.5，最小高 1.5。
- 颜色：`c>=o` 用 `--up`(红涨)，否则 `--down`(绿跌)。
- 参考线：首根开盘价处水平 1px 虚线 `3 5`，`--text-faint` 透明度0.5。

### MALineChart（均线，viewBox 900×320）
- padL4 padR8 padT18 padB26；y 轴留 4% 余量。
- 网格 3 条（lo / 中 / hi）1px `--grid`，左上角价标 13px 等宽 `--text-faint`。
- 收盘价线 1.4px `--price-line` 透明度0.85；MA5/20/120/240 各 1.6px，色 = `--ma5`(橙)/`--ma20`(蓝)/`--ma120`(紫)/`--ma240`(绿)。

### MACDChart（viewBox 900×200）
- 零轴居中 1px `--grid`；柱宽 = 内宽/根数×0.6（min 0.8）；柱色 红涨绿跌 透明度0.85。
- DIF 线 1.5px `--ma5`；DEA 线 1.5px `--ma20`。

### Sparkline（小折线，默认 120×34）：1.6px，圆角连接，按 up 上色。

---

## AI 分析 AIAnalysis（居中 max-width 1080，padding 顶40）
- Hero（居中）：小标 11.5/700 字距 0.22em `--accent-bright`；H1 **32/700** 字距 -0.02em（含 `--accent-bright` 高亮词，可换行）；副文 14px `--text-dim`，上间距 8。
- 输入条 `.panel`：`padding 10`，max-width 760 居中，上间距 26，flex gap 10：✦ 前缀(18px `--text-faint`，左 padding10) + input(15px，透明无边框，padding 10/0) + 按钮「开始分析」14/700 白字 渐变底 `padding 12/24` 圆角 `--r-sm` 投影 `0 10px 24px -12px accent`。
- 推荐标签：上间距 16，gap 9 居中，「试试：」12.5 `--text-faint`；chip = `.card` `--surface` 底 12.5 `--text-dim` `padding 7/13`。
- 历史任务：上间距 46。标题「历史任务」13/700 字距 0.16em + 右计数 11.5 等宽。网格 `minmax(340,1fr) gap 14`。
  - 任务卡 `.card` `padding 16/18`：标题 15/600 + 「● 已完成」10.5/700 `--down` 字 `--down-soft` 底 `padding 3/9` 圆角 99；中段 11.5 `--text-faint`「N 环节 · 日期」(margin 12/0/14)；按钮组 gap 8 =「继续」12.5/600 白字 `--accent` 底 `padding 8/18` + 「删除」`.card` 透明底 `--text-dim` `padding 8/16`。

---

## 模型配置 ModelConfig（居中 max-width 980）
- 头部：小标「SETTINGS」11.5/700 字距 0.22em；H1「模型配置」26/700；副文 13.5 `--text-dim`。下间距 24。
- 双栏 `grid 1fr 1fr; gap 18; align-items:start`。
- **左 供应商配置** `.panel` `padding 22`：标题行 = 8×8 `--accent-bright` 圆点 + 「供应商配置」15/700（下间距 18）。
  - Field（下间距 15）：label 11.5/600 `--text-faint`（下间距 7 字距0.04em）+ input 满宽 1px `--border` `--surface-2` 底 圆角 `--r-sm` `padding 11/13` 13.5px；focus 边框 `--accent-line`。URL/Key 用等宽。
  - 按钮组 gap 10（上间距 20）：「保存配置」13.5/700 白字 渐变底 `padding 10/22` + 「获取模型列表」`.card` 透明底 `--accent-bright` 字 `--accent-line` 边 `padding 10/20`。
- **右 可用模型** `.panel` `padding 22`：标题行 + 右「N 个」11.5 等宽。列表 gap 9：
  - 模型项 `.card` `padding 13/15` space-between：左 = 单选圈 16×16(2px 边，选中 `--accent-bright` + 内点 7×7) + 模型名 13.5/600 等宽 + 标签徽标 10.5 `--surface-3` 底 `padding 2/8` 圆角99；右 = 上下文长度 10.5 等宽 + 选中「当前使用」徽标 10.5/700 白字 `--accent` 底 `padding 3/9`。**选中项**底 `--accent-soft` 边 `--accent-line`。

---

## 个股洞察弹窗 InsightModal
- 遮罩：`position:fixed; inset:0; z-index:40`，背景 `color-mix(bg 55%, rgba(0,0,0,0.6))` + `blur(6)`，`padding 28`，居中；点遮罩关闭；`fadeIn 0.25s`。
- 面板 `.panel`：`min(1240px,96vw) × max-height 92vh`，纵向 flex，`overflow hidden`，`modalIn 0.32s`（from translateY(18) scale(0.985)）。
- **头部**（`padding 18/24`，下边框 1px）：baseline 行 = 股票名 20/700 + 「盘面洞察」12.5 `--text-dim` + 代码 12 等宽 `--text-faint` + 价格 16/700 上色（百分比 12.5）；右 = 生成时间 11 等宽 `--text-faint` + 「关闭 ✕」`.card` 13/600 `--text-dim` `padding 8/16`。
- **Body**：`grid 1.6fr 1fr`，满高，`overflow hidden`。
  - 左「图表区」：纵向滚动，`padding 20/22`，gap 16，右 1px 分隔。两个 **ChartBlock**(`.card` `--surface-2` 底 `padding 14/16`)：标题 13.5/700 + 子标 11 `--text-faint`；右侧图例 = 12×2.5 色条 + 11px `--text-dim` 标签；图区高 300 / 196。
  - 右「结构解读」：纵向滚动 `padding 20/22`。标题行 = 「结构解读」15/700 + 「✦ 智能解盘」12.5/700 白字 渐变底 `padding 7/15`。「大事提醒」卡：`--accent-soft` 底 + `--accent-line` 边 圆角 `--r-sm` `padding 12/14`，小标 11/700 `--accent-bright` + 正文 12.5 `--text-dim` line-height1.6。「综合解读」列表 gap 14：每项 = 序号块 24×24 圆角 `--r-sm` `--surface-3` 底 12/700 `--accent-bright` + 标题 13/700 + 正文 12.5 `--text-dim` line-height1.65。

---

## 动态场景背景（精确动效参数见 styles.css）
**深色 cosmos**：流星 5（meteorFly，时长 7–14s，仅 0–26% 飞行其余隐藏=偶发）/ 星点 72（twinkle 2.2–6s）/ 地球辉光（earthBreathe 7s，opacity .55↔1 scale 1↔1.07，位 50%×29%）/ 城市灯 14（cityFlicker 1.6–4.2s，地球右下簇）/ 冰面反光（glowPulse 5.5s，50%×80%）+ 斜扫光（iceSweep 9s）/ 图片 cosmosDrift 38s scale 1.04↔1.08。开启时 `body.cosmos-on` 把 surface 改半透明深色 + `blur(13)`，标题加深色描边。

**浅色 day**：图片 dayDrift 54s scale1.03↔1.075 / 天光 skyBreathe 8.5s（50%×23% 暖光）/ 薄云 4（cloudDrift 33–66s 横穿，blur7）/ 行星 50%×30% 直径 52vh：云带 bandFlow 30s（soft-light，±16%）+ 边缘金光 rimGlow 7s / 沙纹扫光 sandSweep 13s / 风沙微粒 26（sandFloat 6–14s，贴地飘移）。开启时 `body.day-on` 把 surface 改 `rgba(255,255,255,~.68)` + `blur(14)` + 卡片投影 + 标题白色柔光描边。
两图构图一致：巨大天体在上方≈50%×28–30%，地平线在下，吉祥物左右下角；动效层用百分比定位以对齐卡片。
