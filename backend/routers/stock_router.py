"""
行情数据路由
提供实时行情、K线数据和股票搜索的HTTP接口
所有接口统一返回JSON格式，路由前缀在main.py中配置为 /api/stocks
"""
from fastapi import APIRouter, Query, HTTPException

from backend.services.stock_service import (
    fetch_quotes,
    fetch_kline,
    fetch_close_history,
    search_stocks,
)
from backend.services.stock_diagnosis_service import (
    build_enhanced_stock_diagnosis,
    build_stock_diagnosis,
)

# 创建路由器实例
router = APIRouter()


@router.get("/quotes")
async def get_quotes(
    codes: str = Query(
        ...,
        description="股票代码，逗号分隔，如 SZ:002261,SH:600000",
    ),
    task_id: str | None = Query(
        None,
        description="可选任务ID，不传则使用共享缓存",
    ),
):
    """
    批量获取实时行情
    请求示例: GET /api/stocks/quotes?codes=SZ:002261,SH:600000
    返回: 每只股票的最新行情数据列表
    """
    # 按逗号分割并过滤空字符串
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(
            status_code=400,
            detail="参数codes不能为空",
        )
    # 调用行情服务获取数据
    quotes = await fetch_quotes(code_list, task_id=task_id)
    return {"data": [q.model_dump() for q in quotes]}


@router.get("/kline")
async def get_kline(
    code: str = Query(
        ...,
        description="股票代码，如 SZ:002261",
    ),
    period: str = Query(
        "daily",
        description="K线周期: daily/60min/30min/15min/5min",
    ),
    count: int = Query(
        22,
        ge=1,
        le=500,
        description="数据条数，默认22个交易日（近一个月日K）",
    ),
    task_id: str | None = Query(
        None,
        description="可选任务ID，不传则使用共享缓存",
    ),
):
    """
    获取近一个月日K数据
    请求示例: GET /api/stocks/kline?code=SZ:002261&period=daily&count=22
    返回: 指定股票近一个月的日K数据点列表
    """
    # 调用行情服务获取K线
    points = await fetch_kline(code, period, count, task_id=task_id)
    return {"data": [p.model_dump() for p in points]}


@router.get("/close-history")
async def get_close_history(
    code: str = Query(
        ...,
        description="股票代码，如 SZ:000725 或 000725",
    ),
    count: int = Query(
        250,
        ge=1,
        le=500,
        description="交易日数量，默认250个交易日，近似1年",
    ),
):
    """
    获取历史收盘价。
    当前用于功能测试：为后续MACD/DIF/DEA本地计算准备收盘价序列。
    """
    formatted_code, points, elapsed_ms = await fetch_close_history(code, count=count)
    return {
        "code": formatted_code,
        "source": "xueqiu",
        "period": "day",
        "count": len(points),
        "elapsed_ms": elapsed_ms,
        "data": [point.model_dump() for point in points],
    }


@router.get("/diagnosis")
async def get_stock_diagnosis(
    code: str = Query(
        ...,
        description="股票代码，如 SZ:000725 或 000725",
    ),
    name: str = Query(
        "",
        description="股票名称，可选，用于诊断报告展示",
    ),
):
    """
    按需生成个股诊断。
    用户点击股票后才拉取历史行情、股东人数、财报和公司大事，先返回纯数据本地诊断。
    """
    try:
        diagnosis = await build_stock_diagnosis(code, name=name)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"生成个股诊断失败: {exc}",
        ) from exc
    return diagnosis.model_dump()


@router.post("/diagnosis/enhance")
async def enhance_stock_diagnosis(
    code: str = Query(
        ...,
        description="股票代码，如 SZ:000725 或 000725",
    ),
    name: str = Query(
        "",
        description="股票名称，可选，用于诊断报告展示",
    ),
):
    """
    按用户点击触发大模型强化诊断。
    """
    try:
        diagnosis = await build_enhanced_stock_diagnosis(code, name=name)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"生成强化诊断失败: {exc}",
        ) from exc
    return diagnosis.model_dump()


@router.get("/search")
async def search(
    q: str = Query(
        ...,
        min_length=1,
        description="搜索关键词，支持代码和名称",
    ),
    task_id: str | None = Query(
        None,
        description="可选任务ID，不传则使用共享缓存",
    ),
):
    """
    搜索股票
    请求示例: GET /api/stocks/search?q=拓维
    返回: 匹配的股票简要信息列表
    说明: 从已缓存的行情数据中进行模糊搜索
    """
    results = await search_stocks(q, task_id=task_id)
    return {"data": results}
