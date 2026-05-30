# DaimsenGogo Logo · 使用说明

定稿标志「方向 A · 精炼实心」——字母 **D** 与**鸟头**的双关标（竖脊=D 脊柱，圆=字碗，圆内白点=鸟眼，斜翼=喙/翅）。所有文件基于 512×512 网格绘制，矢量无损。

## 文件清单
| 文件 | 颜色 | 用途 |
|---|---|---|
| `daimsengogo-mark.svg` | `currentColor` | **代码首选**——内联进 HTML/JSX，自动继承 CSS `color`，一个文件适配所有主题 |
| `daimsengogo-mark-white.svg` | `#ffffff` | 深色背景 / 照片 / 反白 |
| `daimsengogo-mark-ink.svg` | `#0b0b14` | 浅色背景 / 印刷 / 黑白场景 |
| `daimsengogo-mark-deep.svg` | `#4b3bc4` 深紫 | **浅色主题**品牌色版 |
| `daimsengogo-mark-bright.svg` | `#a99bf8` 亮紫 | **深色主题**品牌色版 |
| `daimsengogo-icon.svg` | 紫渐变圆角砖 + 白标 | App 图标 / 头像 / 启动图 / favicon 大图 |

## 配色规则（重要）
**不要为深浅主题画两个不同的标**，而是同一造型换色调：
- 深色主题 → `--logo: #a99bf8`（亮紫）或纯白
- 浅色主题 → `--logo: #4b3bc4`（深紫）或墨色
- 品牌主色（产品强调色）= `#7b6bf0`

## 推荐用法
- **顶栏 / 界面内**：用 `daimsengogo-mark.svg`（currentColor），内联后用 CSS 控制颜色：
  ```html
  <span style="color: var(--brand-logo, #a99bf8)">
    <!-- 把 daimsengogo-mark.svg 的内容直接粘进来 -->
  </span>
  ```
  或作为 React 组件 `<Logo />`，让 `fill="currentColor"` 跟随父级 `color`。
- **favicon**：用 `daimsengogo-icon.svg` 直接作为 `<link rel="icon" type="image/svg+xml">`；如需 .ico/.png 多尺寸，从 icon.svg 导出 16/32/48/180(apple-touch)/512。
- **最小尺寸**：标志净高 ≥ 16px；小于 20px 时建议改用 `daimsengogo-icon.svg`（带底色砖，小尺寸更清晰）。
- **留白**：标志四周留出 ≥ 标志高度 25% 的安全区。

## 技术说明
- 单色版用 `<mask>`（镂空字碗）+ `<clipPath>`（裁切斜翼）实现，现代浏览器全支持。
- 若目标环境对 mask 支持差（个别原生/打印管线），需要**展平为单一 path** 的版本，可让 Claude 再导出。
- 内联多个 SVG 到同一页面时注意 `mask`/`clipPath` 的 **id 唯一性**（各文件已用不同后缀 `dg-k-*` / `dg-c-*`，但若复制粘贴多份同色版，请手动改 id 避免冲突）。

## 几何参数（便于复刻 / 微调）
- 竖脊 rect：x92 y100 w158 h312 rx6
- 字碗 circle：cx256 cy256 r156
- 字碗镂空 circle：cx288 cy256 r118
- 鸟眼 circle：cx248 cy210 r30
- 斜翼 path（裁切于镂空圆内）：`M170 342 L430 240 L444 396 L156 396 Z`
- App 图标：底 `rect rx116` + 渐变 `#a99bf8→#4b3bc4`(x1 0 y1 0 → x2 0.72 y2 1)，标志 `translate(96 96) scale(0.625)`（25% 留白）
