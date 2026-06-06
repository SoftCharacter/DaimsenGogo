"""
K线数据获取器
保留原模块入口以兼容旧调用，但底层统一改用AkShare。
当前项目只需要近一个月日K，固定返回最近22个交易日数据。
"""
import asyncio

from backend.models.stock_models import KLinePoint
from backend.services.akshare_adapter import fetch_recent_daily_kline_sync

# 兼容旧代码的周期映射常量；当前服务层不再依赖该值
PERIOD_MAP = {
    "daily": 240,
}


async def fetch_kline_akshare(
    code: str,
    count: int = 22,
) -> list[KLinePoint]:
    """
    使用AkShare获取近一个月日K
    count参数仅为兼容旧调用保留，实际固定返回最近22个交易日。
    """
    return await asyncio.to_thread(fetch_recent_daily_kline_sync, code)


async def fetch_kline_sina(
    code: str,
    scale: int,
    count: int,
) -> list[KLinePoint]:
    """
    兼容旧函数名的包装方法
    不再调用新浪接口，统一转向AkShare近一个月日K。
    """
    return await fetch_kline_akshare(code, count)
