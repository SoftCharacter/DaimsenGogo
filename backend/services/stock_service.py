"""
行情服务
通过AkShare获取实时行情和近一个月日K数据。
AkShare是同步库，本服务层使用 asyncio.to_thread 避免阻塞FastAPI事件循环。
"""
import asyncio
import time
import logging

from backend.models.stock_models import StockQuote, KLinePoint
from backend.services.akshare_adapter import (
    fetch_quote_xq_sync,
    fetch_recent_daily_kline_sync,
    get_stock_list,
)

# 日志记录器
logger = logging.getLogger(__name__)

# ──────────────────── 缓存配置 ────────────────────
# 缓存结构: {缓存键: (写入时间戳, 数据)}
_quote_cache: dict[str, tuple[float, list[StockQuote]]] = {}
_kline_cache: dict[str, tuple[float, list[KLinePoint]]] = {}
_stock_search_cache: dict[str, tuple[float, list[dict]]] = {}

# 缓存过期时间(秒)
QUOTE_TTL = 5          # 实时行情缓存5秒
KLINE_TTL = 3600       # 近一个月日K缓存1小时
STOCK_LIST_TTL = 3600  # 股票列表缓存1小时
QUOTE_CONCURRENCY = 5  # 雪球实时行情并发上限
KLINE_CONCURRENCY = 3  # K线外部请求并发上限
_quote_semaphore = asyncio.Semaphore(QUOTE_CONCURRENCY)
_kline_semaphore = asyncio.Semaphore(KLINE_CONCURRENCY)


def _scope_key(task_id: str | None) -> str:
    """返回进程内缓存的任务作用域。"""
    return task_id or "_shared"


def _cache_key(codes: list[str], task_id: str | None = None) -> str:
    """
    根据股票代码列表生成缓存键
    排序后拼接，确保相同代码组合命中同一缓存。
    """
    return f"{_scope_key(task_id)}|{','.join(sorted(codes))}"


async def _fetch_one_quote(code: str, task_id: str | None = None) -> StockQuote | None:
    """按并发上限获取单只股票实时行情。"""
    async with _quote_semaphore:
        return await asyncio.to_thread(fetch_quote_xq_sync, code, task_id)


async def fetch_quotes(codes: list[str], task_id: str | None = None) -> list[StockQuote]:
    """
    批量获取实时行情
    使用雪球个股接口按传入股票代码有限并发获取，避免全量下载A股行情。
    """
    if not codes:
        return []

    key = _cache_key(codes, task_id=task_id)
    cached = _quote_cache.get(key)
    if cached:
        ts, data = cached
        if time.time() - ts < QUOTE_TTL:
            return data

    results = await asyncio.gather(
        *(_fetch_one_quote(code, task_id=task_id) for code in codes),
        return_exceptions=True,
    )
    quotes: list[StockQuote] = []
    for result in results:
        if isinstance(result, StockQuote):
            quotes.append(result)
        elif isinstance(result, Exception):
            logger.warning("雪球获取单只实时行情失败: %s", result)

    if quotes:
        _quote_cache[key] = (time.time(), quotes)
        return quotes
    if cached:
        return cached[1]
    return []


async def fetch_kline(
    code: str,
    period: str = "daily",
    count: int = 22,
    task_id: str | None = None,
) -> list[KLinePoint]:
    """
    获取近一个月日K数据
    为保证大屏展示一致性，忽略period/count差异，固定返回最近22个交易日日K。
    """
    cache_key = f"{_scope_key(task_id)}|{code}|daily|month"
    cached = _kline_cache.get(cache_key)
    if cached:
        ts, data = cached
        if time.time() - ts < KLINE_TTL:
            return data

    try:
        async with _kline_semaphore:
            points = await asyncio.to_thread(fetch_recent_daily_kline_sync, code, task_id)
    except Exception as exc:
        logger.error("akshare获取近一个月日K失败 [%s]: %s", code, exc)
        if cached:
            return cached[1]
        return []

    if points:
        _kline_cache[cache_key] = (time.time(), points)
    return points


async def search_stocks(keyword: str, task_id: str | None = None) -> list[dict]:
    """
    搜索股票
    使用AkShare全量A股列表进行名称/代码模糊匹配，不依赖行情缓存。
    """
    now = time.time()
    scope = _scope_key(task_id)
    cached = _stock_search_cache.get(scope)
    if cached and now - cached[0] < STOCK_LIST_TTL:
        stock_list = cached[1]
    else:
        try:
            stock_list = await asyncio.to_thread(get_stock_list, task_id)
            _stock_search_cache[scope] = (now, stock_list)
        except Exception as exc:
            logger.error("akshare获取股票列表失败: %s", exc)
            stock_list = cached[1] if cached else []

    kw = keyword.strip().upper()
    results: list[dict] = []
    for item in stock_list:
        code = item.get("code", "")
        name = item.get("name", "")
        if kw in code.upper() or kw in name.upper() or keyword in name:
            results.append({"code": code, "name": name, "current_price": 0.0})

    return results[:20]
