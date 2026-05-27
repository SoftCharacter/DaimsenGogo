"""
个股诊断数据模型
"""
from pydantic import BaseModel, Field


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
    category: str | None = None
    title: str
    message: str
    subtype: int | None = None
    sentiment: str | None = None


class ChipHistogramBin(BaseModel):
    """单个价格档位的筹码占比"""
    price: float
    percent: float
    profitable: bool


class ChipDistributionSnapshot(BaseModel):
    """单个交易日筹码分布摘要"""
    date: str
    timestamp: int
    close: float
    benefit_ratio: float
    avg_cost: float
    cost_90_low: float
    cost_90_high: float
    cost_90_concentration: float
    cost_70_low: float
    cost_70_high: float
    cost_70_concentration: float
    support_price: float | None = None
    pressure_price: float | None = None
    relative_price_trend: str = ""
    concentration_trend: str = ""
    interpretation: str = ""


class ChipDistributionResponse(BaseModel):
    """筹码分布计算结果"""
    source: str = "eastmoney_kline_local_cyq"
    params: dict[str, int]
    snapshots: list[ChipDistributionSnapshot]
    latest: ChipDistributionSnapshot | None = None
    histogram: list[ChipHistogramBin]
    histograms: dict[str, list[ChipHistogramBin]] = Field(default_factory=dict)


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
    chip_distribution: ChipDistributionResponse | None = None
    event_summary: str
    diagnosis_report: str
    llm_status: str
    data_errors: dict[str, str] = Field(default_factory=dict)
