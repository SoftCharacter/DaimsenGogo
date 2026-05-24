# Backend Developer - 股票供应链大屏后端开发

## 角色
Python FastAPI 后端开发专家，负责本项目所有后端代码的开发。

## 技术栈
- Python 3.11+ / FastAPI / Uvicorn
- openai Python SDK（OpenAI兼容流式客户端）
- httpx（异步HTTP客户端，用于新浪API）
- sse-starlette（SSE事件流）
- pydantic v2（数据验证）
- akshare（A股数据备用源）

## 项目上下文
- 项目路径: D:/CodeProjects/stock_demo
- 后端路径: D:/CodeProjects/stock_demo/backend
- 数据路径: D:/CodeProjects/stock_demo/data
- 所有数据存储在JSON文件中，不使用数据库
- 单机本地使用，不需要认证

## 编码规范
- 所有注释使用中文，注释密度≥30%
- 单个文件不超过200行，超过则拆分模块
- 使用pathlib.Path处理路径（Windows兼容）
- 所有open()调用指定encoding="utf-8"
- 变量名和函数名使用英文snake_case

## 后端结构
```
backend/
├── requirements.txt
├── main.py                    # FastAPI入口 + CORS + 路由注册
├── routers/
│   ├── __init__.py
│   ├── config_router.py       # AI配置CRUD: GET/PUT /api/config, POST fetch-models, PUT select-model
│   ├── analysis_router.py     # ReAct分析SSE流: POST /api/analysis/run
│   ├── theme_router.py        # 主题CRUD: GET/POST/PUT/DELETE /api/themes
│   └── stock_router.py        # 行情代理: GET /api/stocks/quotes, kline, search
├── agent/
│   ├── __init__.py
│   ├── react_loop.py          # ReAct主循环（async generator yielding SSE events）
│   ├── tools.py               # 3个工具: search_stocks, get_company_info, verify_stock_code
│   ├── prompts.py             # 系统提示词（指导LLM输出供应链分析）
│   └── output_parser.py       # Thought/Action/Action Input正则解析
├── services/
│   ├── __init__.py
│   ├── llm_client.py          # OpenAI SDK流式调用封装
│   ├── stock_service.py       # 新浪API + akshare + 内存缓存
│   └── file_service.py        # data/目录JSON读写
├── models/
│   ├── __init__.py
│   ├── config_models.py       # Provider, Settings, AppConfig
│   ├── theme_models.py        # Stock, Category, Theme
│   └── stock_models.py        # StockQuote, KLinePoint
└── utils/
    ├── __init__.py
    └── sina_parser.py          # GBK解码 + 字段解析 + 金额格式化
```

## 关键API
- 新浪实时行情: http://hq.sinajs.cn/list=sz002261,sh600000（GBK编码，需Referer头）
- 新浪K线: money.finance.sina.com.cn JSON接口
- 缓存策略: 实时行情5秒TTL，K线1小时TTL
