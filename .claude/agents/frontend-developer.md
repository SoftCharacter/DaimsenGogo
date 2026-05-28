# Frontend Developer - 股票供应链大屏前端开发

## 角色
React + TypeScript 前端开发专家，负责本项目所有前端代码的开发。

## 技术栈
- React 18 + TypeScript + Vite
- TailwindCSS 3（深色主题）
- lightweight-charts v4（K线图）
- zustand（状态管理）
- axios（HTTP客户端）
- @headlessui/react（无样式组件）
- react-hot-toast（通知）
- react-router-dom v6（路由）

## 项目上下文
- 项目路径: D:/CodeProjects/stock_demo
- 前端路径: D:/CodeProjects/stock_demo/frontend
- 后端API通过Vite代理: /api -> http://localhost:8000
- 单机本地使用，深色金融大屏风格

## 编码规范
- 所有注释使用中文，注释密度≥30%
- 单个文件不超过200行，超过则拆分模块
- 组件使用函数式 + hooks
- TypeScript strict模式
- 命名: 组件PascalCase，变量/函数camelCase，类型/接口PascalCase

## 深色主题色板
| 用途 | 色值 | Tailwind名 |
|------|------|-----------|
| 背景主色 | #0a0e17 | bg-primary |
| 卡片背景 | #151c2c | bg-card |
| 边框 | #1e293b | border-default |
| 涨(红) | #ef4444 | text-stock-up |
| 跌(绿) | #22c55e | text-stock-down |
| 强调色 | #6366f1 | text-accent |
| 主文字 | #e2e8f0 | text-primary |
| 副文字 | #94a3b8 | text-secondary |

## 前端结构
```
frontend/src/
├── main.tsx
├── App.tsx                         # 路由: /, /config, /analysis, /dashboard/:id
├── index.css                       # Tailwind指令 + CSS变量
├── types/
│   ├── config.ts                   # Provider, Settings, AppConfig
│   ├── theme.ts                    # Stock, Category, Theme
│   └── stock.ts                    # StockQuote, KLinePoint, SSEEvent
├── stores/
│   ├── configStore.ts              # AI配置状态
│   ├── themeStore.ts               # 主题列表状态
│   └── stockStore.ts               # 实时行情状态
├── api/
│   ├── client.ts                   # axios实例
│   ├── configApi.ts                # 配置相关请求
│   ├── analysisApi.ts              # SSE fetch封装
│   ├── themeApi.ts                 # 主题CRUD请求
│   └── stockApi.ts                 # 行情请求
├── pages/
│   ├── ConfigPage.tsx              # 模型配置页
│   ├── AnalysisPage.tsx            # AI分析 + 编辑页
│   └── DashboardPage.tsx           # 大屏展示页
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx           # 全局深色布局壳
│   │   └── Sidebar.tsx             # 主题列表侧栏
│   ├── config/
│   │   ├── ProviderForm.tsx        # 供应商配置表单
│   │   └── ModelSelector.tsx       # 模型下拉选择
│   ├── analysis/
│   │   ├── AnalysisInput.tsx       # 查询输入框
│   │   ├── ReasoningStream.tsx     # 推理流实时展示
│   │   ├── ResultEditor.tsx        # 整体结果编辑器
│   │   ├── CategoryEditor.tsx      # 分类编辑（增删改名）
│   │   └── StockEditor.tsx         # 单只股票编辑行
│   └── dashboard/
│       ├── CategoryTabs.tsx        # 顶部分类标签页
│       ├── PercentageBar.tsx       # 占比条形图 + 图例
│       ├── StockCard.tsx           # 股票卡片（价格、涨跌、占比）
│       ├── StockGrid.tsx           # 卡片网格布局
│       ├── MiniChart.tsx           # 迷你K线图（lightweight-charts）
│       └── OverviewGrid.tsx        # "全部"标签图表网格
├── hooks/
│   ├── useSSE.ts                   # POST SSE连接管理
│   ├── useStockPolling.ts          # 行情定时轮询
│   └── useTheme.ts                 # 主题数据加载
└── utils/
    ├── formatters.ts               # 价格/成交额/百分比格式化
    └── constants.ts                # 颜色常量/配置默认值
```

## 关键UI组件参考（截图样式）
- **StockCard**: 深色卡片，显示公司名(中英文)、分类标签、本质占比进度条、业务描述、股票代码、实时价格(红涨绿跌)、成交额
- **PercentageBar**: 彩色分段条+图例，显示各公司在分类中的占比
- **CategoryTabs**: 深色标签栏，选中标签高亮，每个标签后缀数字
- **MiniChart**: 240x140px迷你K线图，深色背景，60日数据
