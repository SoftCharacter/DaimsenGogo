"""
行情数据模型
定义股票实时行情和K线数据结构
"""
from pydantic import BaseModel


class StockQuote(BaseModel):
    """股票实时行情"""
    code: str                    # 股票代码 "SZ:002261"
    name: str = ""               # 股票名称
    current_price: float = 0.0   # 当前价格
    prev_close: float = 0.0      # 昨收价
    open_price: float = 0.0      # 开盘价
    high: float = 0.0            # 最高价
    low: float = 0.0             # 最低价
    change: float = 0.0          # 涨跌额
    change_percent: float = 0.0  # 涨跌幅（百分比）
    volume: float = 0.0          # 成交额（元）
    volume_display: str = ""     # 成交额展示文本，如 "218亿"
    timestamp: str = ""          # 数据时间戳


class KLinePoint(BaseModel):
    """K线数据点"""
    date: str          # 日期 "2026-04-25"
    open: float        # 开盘价
    high: float        # 最高价
    low: float         # 最低价
    close: float       # 收盘价
    volume: float      # 成交量
