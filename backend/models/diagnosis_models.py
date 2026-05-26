"""
个股诊断数据模型
"""
from pydantic import BaseModel


class MacdPoint(BaseModel):
    """MACD日线计算结果"""
    date: str
    timestamp: int
    close: float
    dif: float
    dea: float
    macd: float


class ShareholderPoint(BaseModel):
    """股东人数变化点"""
    date: str
    timestamp: int
    ashare_holder: int
    change_percent: float | None = None
    price: float | None = None
    per_amount: float | None = None
    top_holder_ratio: float | None = None


class NetProfitPoint(BaseModel):
    """年度归母净利润点"""
    report_name: str
    report_date: str
    timestamp: int
    net_profit_atsopc: float
    yoy_percent: float | None = None


class StockEventPoint(BaseModel):
    """公司大事提醒"""
    date: str
    timestamp: int
    title: str
    message: str
    subtype: int | None = None
    sentiment: str | None = None


class StockDiagnosisResponse(BaseModel):
    """个股诊断接口响应"""
    code: str
    name: str = ""
    generated_at: str
    source: str = "xueqiu"
    timings_ms: dict[str, float]
    macd: list[MacdPoint]
    shareholders: list[ShareholderPoint]
    net_profit: list[NetProfitPoint]
    events: list[StockEventPoint]
    event_summary: str
    diagnosis_report: str
    llm_status: str
