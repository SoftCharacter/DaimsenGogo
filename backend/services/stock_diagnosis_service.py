"""
个股诊断服务
点击股票后按需拉取历史行情、股东人数、财报和公司大事，并生成诊断结果。
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta

from backend.models.diagnosis_models import (
    ChipDistributionResponse,
    MacdPoint,
    MovingAveragePoint,
    NetProfitPoint,
    ShareholderPoint,
    StockDiagnosisResponse,
    StockEventPoint,
)
from backend.services.akshare_adapter import (
    extract_numeric_code,
    fetch_close_history_sync,
    fetch_finance_indicator_xq_sync,
    fetch_shareholders_xq_sync,
    fetch_stock_events_xq_sync,
    format_stock_code,
)
from backend.services.chip_distribution_service import build_chip_distribution_sync
from backend.services.file_service import load_config
from backend.services.llm_client import chat_complete, create_client

logger = logging.getLogger(__name__)

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ONE_YEAR_TRADING_DAYS = 250
MACD_WARMUP_DAYS = 500
STOCK_DIAGNOSIS_PROMPT = """
你是一名专业但表达易懂的 A 股股票诊断分析师。你的任务是根据后端传入的股票数据，对股票进行结构化诊断分析，并以 Markdown 格式返回给前端展示。
你的输出应当专业、克制、清晰、有解释力，让普通股民能看懂，但不能显得像营销荐股话术。

====================
一、输入数据说明
====================

你会收到后端传入的 JSON 对象，数据可能包括但不限于：

1. 股票基本信息
- 股票名称
- 股票代码
- 当前价格
- 涨跌幅
- 分析日期
- 数据更新时间

2. 股东人数变化
- 最近若干期股东人数
- 股东人数增减方向
- 增减幅度
- 户均持股变化
- 后端计算出的趋势结论

3. 筹码分布
- 筹码集中度
- 平均成本
- 主要筹码区间
- 获利盘比例
- 上方套牢盘情况
- 下方支撑筹码情况
- 后端计算出的筹码分布结论

4. 技术指标
- 当前价格
- 支撑位
- 压力位
- MACD 指标
- DIF
- DEA
- MACD 柱
- 金叉 / 死叉情况
- MACD 背离情况
- 后端计算出的技术信号

5. 大事提醒
只关注以下类别：
- 风险提示：违规处罚、诉讼仲裁
- 股权变动：限售解禁、股票回购、股东增减持、高管及关联方增减持、股权质押、解除质押
- 重大事项：对外担保、资本运作

其他类型的大事提醒全部忽略，不要分析，不要提及。

====================
二、核心分析原则
====================

1. 只能基于传入数据分析
不得编造未提供的数据，不得假设不存在的信息，不得用常识补全具体数值。

2. 数据缺失时跳过对应模块
如果某个模块没有有效数据，直接跳过该模块，不要写“暂无数据”，不要强行分析。

3. 后端计算结果优先
后端已经计算出的趋势、金叉死叉、支撑压力、筹码集中度、背离情况等，视为主要判断依据。
你可以结合原始证据数据解释这些结论，但不要推翻明确的后端计算结果。

4. 只做分析，不给具体买卖建议
不得输出以下或类似表达：
- 建议买入
- 建议卖出
- 可以加仓
- 可以减仓
- 适合低吸
- 不妨追高
- 止损位
- 目标价
- 持有建议
- 建仓建议

可以使用以下表达：
- 需要关注
- 需要观察
- 需要警惕
- 仍需验证
- 短期情绪可能受到影响
- 对股价形成压力
- 对市场预期形成支撑
- 不宜仅凭单一指标判断

5. 不使用评级标签
不要使用“偏积极 / 中性偏强 / 中性 / 中性偏弱 / 偏谨慎”等标签。
全部使用自然语言描述。

6. 风格要求
主体采用“专业研报 + 普通股民能看懂”的混合风格。
表达要清晰、有人话、有逻辑，但不要夸张，不要煽动，不要制造确定性。

7. 尾部结论允许轻微活人感
最后的“结论”部分可以带一点调侃、阴阳怪气、活人感，但必须克制，不能粗俗，不能人身攻击，不能劝诱交易。
结论中必须包含“投资需谨慎”。
可以使用类似表达：
- 少入场，多观望
- 别急着当股神
- 市场不缺机会，缺的是不冲动的手

====================
三、大事提醒分析规则
====================

1. 只分析指定类型事件
只分析：
- 风险提示：违规处罚、诉讼仲裁
- 股权变动：限售解禁、股票回购、股东增减持、高管及关联方增减持、股权质押、解除质押
- 重大事项：对外担保、资本运作

2. 排序规则
大事提醒必须按照：
第一优先级：先风险，后机会
第二优先级：同类事项按时间最近优先

3. 风险类优先展示
如果同时存在风险事件和机会事件，必须先分析风险事件。
不要因为存在股票回购等偏正面事项，就忽略限售解禁、诉讼仲裁、质押等风险。

4. 事件影响表达
不要绝对化。
不要说“必然上涨”“必然下跌”。
应使用：
- 可能影响短期情绪
- 可能对资金偏好造成扰动
- 可能增加股价波动
- 可能对市场预期形成支撑
- 后续仍需结合实际进展观察

====================
四、输出格式要求
====================

1. 必须使用 Markdown。
2. 只使用二级标题“##”作为模块标题。
3. 每个模块控制在 1-2 段自然语言，不要在模块内强行拆成“结论 / 依据 / 解读”。
4. 全文长度控制在 800-1200 个中文字符左右。
5. 必须使用 1 个总览表。
6. 如果存在有效的大事提醒数据，再使用第 2 个事件表；如果没有有效大事提醒，则不要强行生成第二个表格。
7. 全文最多3个表格。
8. 不要使用代码块。
9. 不要输出 JSON。
10. 不要输出分析过程。
11. 不要向用户解释你遵守了哪些规则。
12. 不要出现“根据你提供的数据”这种机械表达，可自然写成“从当前数据看”。

====================
五、推荐输出结构
====================

请按以下顺序输出。没有有效数据的模块直接跳过。

## 个股信号总览

必须包含一个 Markdown 表格，字段建议为：
| 观察项 | 当前表现 |
|---|---|
| 股东人数 | ... |
| 筹码分布 | ... |
| 技术状态 | ... |
| 大事提醒 | ... |

表格内容要简洁，不要写长段落。

## 筹码动向

分析股东人数是增加、减少、连续变化还是波动变化。
如果股东人数下降，可以解释为散户数量可能减少、筹码可能趋于集中、浮筹压力可能减轻。
如果股东人数上升，可以解释为筹码可能趋于分散、短期抛压或分歧可能增加。
不要绝对说“主力一定控盘”。

## 筹码结构洞察

分析筹码是否集中、主要成本区在哪里、获利盘和套牢盘对股价的影响。
如果筹码集中度提升，可说明筹码结构改善。
如果上方套牢盘较重，应提示突破压力。
如果下方筹码支撑明显，可说明回落时可能存在承接关注。

## 盘面状态

基于当前价格、支撑位、压力位、筹码和技术信号，描述当前股票所处的整体状态。
这里不要使用“吸筹阶段 / 洗盘阶段 / 拉升阶段 / 出货阶段”等固定标签，除非输入数据明确给出。
重点描述“当前更接近压力区还是支撑区”“技术信号是否需要进一步确认”。

## 关键攻防位

解释当前价格与支撑位、压力位之间的关系。
支撑位可以理解为下方可能出现资金承接的位置。
压力位可以理解为上方可能出现套牢盘或获利盘兑现的位置。
不要把支撑位和压力位写成确定性的买卖点。

## 指标动能信号灯

分析 DIF 与 DEA 的金叉、死叉或纠缠状态。
金叉可以解释为短线动能修复。
死叉可以解释为短线动能转弱。
如果 DIF 和 DEA 贴近纠缠，应说明方向尚不清晰，仍需后续确认。

分析MACD是否存在顶背离、底背离或暂无明显背离。
如果有顶背离，应提示动能与价格走势不匹配，需警惕冲高后的波动。
如果有底背离，应说明下行动能可能减弱，但仍需价格和成交量确认。
如果没有背离，不要强行解读。

## 事件扫描

仅在存在有效大事提醒数据时输出。
必须先写风险，再写机会。
同类事件按时间最近优先。
如果事件较多，可以用一个 Markdown 表格展示。

表格建议格式：
| 类型 | 事项 | 可能影响 |
|---|---|---|
| 风险 | ... | ... |
| 机会 | ... | ... |

## 综合结论

用 1-2 段话总结全篇。
必须包含：
- 当前主要看点
- 当前主要风险
- “投资需谨慎”
- 轻微活人感或调侃风格

可以带一点阴阳怪气，但不要过度。
示例语气：
“这票不是完全没看点，但也别一看金叉就热血上头。市场最爱教育冲动的人，投资需谨慎，少入场多观望，别急着当股神。”

====================
六、禁止事项
====================

严禁：
1. 编造不存在的数据。
2. 给出明确买卖建议。
3. 给出目标价。
4. 使用“必涨”“必跌”“稳赚”“抄底”“起飞”等煽动性词语。
5. 将技术指标解释成确定性结论。
6. 忽略重大风险事件。
7. 分析被过滤范围之外的大事提醒。
8. 输出超过3个表格。
9. 输出和股票诊断无关的内容。
10. 在没有数据支撑时强行判断主力、庄家、控盘。
""".strip()
VALUABLE_EVENT_KEYWORDS = {
    "风险提示": (
        "违规处罚",
        "行政处罚",
        "监管处罚",
        "立案调查",
        "监管函",
        "问询函",
        "警示函",
        "诉讼仲裁",
        "诉讼",
        "仲裁",
    ),
    "股权变动": (
        "限售解禁",
        "解禁",
        "股票回购",
        "回购",
        "股东增持",
        "股东减持",
        "高管增持",
        "高管减持",
        "关联方增持",
        "关联方减持",
        "增持",
        "减持",
        "股权质押",
        "解除质押",
        "质押",
    ),
    "重大事项": (
        "对外担保",
        "担保",
        "资本运作",
        "增发提示",
        "定增",
        "非公开增发",
        "资产重组",
        "重大资产",
        "并购",
        "收购",
        "投资",
    ),
}


def _date_from_ms(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")


def _value_pair_value(raw) -> float:
    if isinstance(raw, list) and raw:
        raw = raw[0]
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _value_pair_percent(raw) -> float | None:
    if raw is None:
        return None
    try:
        return round(_value_pair_value(raw), 4)
    except (TypeError, ValueError):
        return None


def _calculate_macd(points: list[dict]) -> list[MacdPoint]:
    if not points:
        return []

    fast_alpha = 2 / (MACD_FAST + 1)
    slow_alpha = 2 / (MACD_SLOW + 1)
    signal_alpha = 2 / (MACD_SIGNAL + 1)

    ema_fast = float(points[0]["close"])
    ema_slow = float(points[0]["close"])
    dea = 0.0
    result: list[MacdPoint] = []

    for index, point in enumerate(points):
        close = float(point["close"])
        if index == 0:
            ema_fast = close
            ema_slow = close
        else:
            ema_fast = fast_alpha * close + (1 - fast_alpha) * ema_fast
            ema_slow = slow_alpha * close + (1 - slow_alpha) * ema_slow

        dif = ema_fast - ema_slow
        dea = dif if index == 0 else signal_alpha * dif + (1 - signal_alpha) * dea
        macd = 2 * (dif - dea)

        result.append(MacdPoint(
            date=str(point["date"]),
            timestamp=int(point["timestamp"]),
            close=round(close, 4),
            dif=round(dif, 6),
            dea=round(dea, 6),
            macd=round(macd, 6),
        ))

    return result[-ONE_YEAR_TRADING_DAYS:]


def _moving_average(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        result.append(round(total / window, 4) if index >= window - 1 else None)
    return result


def _calculate_moving_averages(points: list[dict]) -> list[MovingAveragePoint]:
    if not points:
        return []
    closes = [float(item["close"]) for item in points]
    ma5 = _moving_average(closes, 5)
    ma20 = _moving_average(closes, 20)
    ma120 = _moving_average(closes, 120)
    ma240 = _moving_average(closes, 240)
    result = [
        MovingAveragePoint(
            date=str(point["date"]),
            timestamp=int(point["timestamp"]),
            close=round(float(point["close"]), 4),
            ma5=ma5[index],
            ma20=ma20[index],
            ma120=ma120[index],
            ma240=ma240[index],
        )
        for index, point in enumerate(points)
    ]
    return result[-ONE_YEAR_TRADING_DAYS:]


def _normalize_shareholders(items: list[dict]) -> list[ShareholderPoint]:
    cutoff = datetime.now() - timedelta(days=365 * 3 + 10)
    points: list[ShareholderPoint] = []
    for item in items:
        timestamp = int(item.get("timestamp") or 0)
        if not timestamp:
            continue
        item_date = datetime.fromtimestamp(timestamp / 1000)
        if item_date < cutoff:
            continue
        points.append(ShareholderPoint(
            date=_date_from_ms(timestamp),
            timestamp=timestamp,
            ashare_holder=int(item.get("ashare_holder") or 0),
            change_percent=_optional_float(item.get("chg")),
            price=_optional_float(item.get("price")),
            per_amount=_optional_float(item.get("per_amount")),
            top_holder_ratio=_optional_float(item.get("top_holder_ratio")),
        ))
    return sorted(points, key=lambda item: item.timestamp)


def _normalize_net_profit(items: list[dict]) -> list[NetProfitPoint]:
    points: list[NetProfitPoint] = []
    for item in items[:5]:
        timestamp = int(item.get("report_date") or 0)
        if not timestamp:
            continue
        points.append(NetProfitPoint(
            report_name=str(item.get("report_name") or ""),
            report_date=_date_from_ms(timestamp),
            timestamp=timestamp,
            net_profit_atsopc=round(_value_pair_value(item.get("net_profit_atsopc")), 2),
            yoy_percent=_value_pair_percent(item.get("net_profit_atsopc_yoy")),
        ))
    return sorted(points, key=lambda item: item.timestamp)


def _classify_valuable_event(item: dict) -> str | None:
    text = f"{item.get('title') or ''} {item.get('message') or ''}"
    for category, keywords in VALUABLE_EVENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return None


def _normalize_events(items: list[dict]) -> list[StockEventPoint]:
    cutoff = datetime.now() - timedelta(days=365 * 5 + 10)
    events: list[StockEventPoint] = []
    for item in items:
        timestamp = int(item.get("timestamp") or 0)
        if not timestamp:
            continue
        item_date = datetime.fromtimestamp(timestamp / 1000)
        if item_date < cutoff:
            continue
        category = _classify_valuable_event(item)
        if not category:
            continue
        tags = item.get("tags") or []
        sentiment = None
        if tags and isinstance(tags, list):
            sentiment = str(tags[0].get("description") or "") or None
        events.append(StockEventPoint(
            date=_date_from_ms(timestamp),
            timestamp=timestamp,
            category=category,
            title=str(item.get("title") or ""),
            message=str(item.get("message") or ""),
            subtype=item.get("subtype"),
            sentiment=sentiment,
        ))
    return sorted(events, key=lambda item: item.timestamp, reverse=True)[:80]


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_event_summary(events: list[StockEventPoint]) -> str:
    if not events:
        return "近五年暂未取得风险提示、股权变动、重大事项类大事提醒。"
    title_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for event in events:
        title_counts[event.title] = title_counts.get(event.title, 0) + 1
        if event.category:
            category_counts[event.category] = category_counts.get(event.category, 0) + 1
    categories = "、".join(f"{category} {count}条" for category, count in category_counts.items())
    top_titles = "、".join(f"{title} {count}次" for title, count in list(title_counts.items())[:5])
    latest = events[0]
    latest_message = latest.message.rstrip("。.!！?？")
    risk_event = next((event for event in events if _event_impact(event)[0] == "风险"), None)
    risk_text = ""
    if risk_event:
        risk_text = (
            f"最近风险事件为 {risk_event.date} 的“{risk_event.title}”："
            f"{_compact_event_message(risk_event)}"
        )
    return (
        f"近五年关键大事提醒 {len(events)} 条，覆盖 {categories}，主要类型包括 {top_titles}。"
        f"最新事件为 {latest.date} 的“{latest.title}”：{latest_message}"
        f"{'。' + risk_text if risk_text else ''}"
    )


def _normalize_report_labels(report: str) -> str:
    replacements = {
        "大事提醒摘要": "大事提醒",
        "综合诊断": "综合解读",
        "## “糖”和“刀”都在这了": "## 事件扫描",
        "## 糖和刀都在这了": "## 事件扫描",
        "“糖”和“刀”都在这了": "事件扫描",
        "糖和刀都在这了": "事件扫描",
        "已取得近五年": "近五年",
        "最新风险/机会事件": "最近风险事件",
    }
    normalized = report
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def _fallback_diagnosis(
    name: str,
    code: str,
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    event_summary: str,
    chip_distribution: ChipDistributionResponse | None = None,
) -> str:
    latest_macd = macd[-1] if macd else None
    latest_holder = shareholders[-1] if shareholders else None
    first_holder = shareholders[0] if shareholders else None
    latest_profit = net_profit[-1] if net_profit else None
    holder_text = "股东人数数据不足。"
    if latest_holder and first_holder:
        diff = latest_holder.ashare_holder - first_holder.ashare_holder
        holder_text = f"股东人数从 {first_holder.date} 的 {first_holder.ashare_holder:,} 户变化到 {latest_holder.date} 的 {latest_holder.ashare_holder:,} 户，变化 {diff:,} 户。"

    macd_text = "MACD数据不足。"
    if latest_macd:
        macd_text = f"最新 {latest_macd.date} 收盘价 {latest_macd.close:.2f}，DIF {latest_macd.dif:.4f}，DEA {latest_macd.dea:.4f}，MACD柱 {latest_macd.macd:.4f}。"

    profit_text = "近五年归母净利润数据不足。"
    if latest_profit:
        yoy = "暂无同比" if latest_profit.yoy_percent is None else f"同比 {latest_profit.yoy_percent:.2f}%"
        profit_text = f"最近年报 {latest_profit.report_name} 归母净利润 {latest_profit.net_profit_atsopc / 1e8:.2f} 亿元，{yoy}。"

    chip_text = "筹码分布数据不足。"
    if chip_distribution and chip_distribution.latest:
        chip = chip_distribution.latest
        support = "暂无" if chip.support_price is None else f"{chip.support_price:.2f}"
        pressure = "暂无" if chip.pressure_price is None else f"{chip.pressure_price:.2f}"
        chip_text = (
            f"最新 {chip.date} 平均成本 {chip.avg_cost:.2f}，盈利比例 {chip.benefit_ratio * 100:.2f}%，"
            f"支撑位 {support}，压力位 {pressure}，{chip.interpretation}。"
        )

    return _normalize_report_labels(
        f"{name or code} 盘面洞察已完成，以下为纯数据本地规则摘要：\n\n"
        f"1. 技术面：\n{macd_text}\n\n"
        f"2. 筹码分布：\n{chip_text}\n\n"
        f"3. 股东结构：\n{holder_text}\n\n"
        f"4. 盈利趋势：\n{profit_text}\n\n"
        f"5. 大事提醒：\n{event_summary}"
    )


def _last_macd_cross(macd: list[MacdPoint]) -> dict | None:
    for index in range(len(macd) - 1, 0, -1):
        previous = macd[index - 1]
        current = macd[index]
        if previous.dif <= previous.dea and current.dif > current.dea:
            return {
                "date": current.date,
                "type": "金叉",
                "dif": current.dif,
                "dea": current.dea,
                "days_since": len(macd) - 1 - index,
            }
        if previous.dif >= previous.dea and current.dif < current.dea:
            return {
                "date": current.date,
                "type": "死叉",
                "dif": current.dif,
                "dea": current.dea,
                "days_since": len(macd) - 1 - index,
            }
    return None


def _find_swings(macd: list[MacdPoint], key: str, mode: str, window: int = 2) -> list[MacdPoint]:
    points: list[MacdPoint] = []
    for index in range(window, len(macd) - window):
        value = getattr(macd[index], key)
        neighbors = [
            getattr(macd[item_index], key)
            for item_index in range(index - window, index + window + 1)
            if item_index != index
        ]
        if mode == "high" and all(value >= item for item in neighbors):
            points.append(macd[index])
        if mode == "low" and all(value <= item for item in neighbors):
            points.append(macd[index])
    return points


def _macd_divergence(macd: list[MacdPoint]) -> dict:
    recent = macd[-60:]
    bearish = False
    bullish = False
    summary = "近60个交易日未识别到明确MACD顶背离或底背离。"
    swing_highs = _find_swings(recent, "close", "high")
    swing_lows = _find_swings(recent, "close", "low")
    if len(swing_highs) >= 2:
        previous, current = swing_highs[-2], swing_highs[-1]
        if current.close > previous.close and current.dif < previous.dif:
            bearish = True
            summary = f"{current.date} 价格高点高于 {previous.date}，但DIF未同步创新高，存在疑似顶背离。"
    if len(swing_lows) >= 2:
        previous, current = swing_lows[-2], swing_lows[-1]
        if current.close < previous.close and current.dif > previous.dif:
            bullish = True
            summary = f"{current.date} 价格低点低于 {previous.date}，但DIF未同步创新低，存在疑似底背离。"
    return {"bearish": bearish, "bullish": bullish, "summary": summary}


def _shareholder_payload(shareholders: list[ShareholderPoint]) -> dict | None:
    if len(shareholders) < 2:
        return None
    first = shareholders[0]
    latest = shareholders[-1]
    change = latest.ashare_holder - first.ashare_holder
    change_percent = change / first.ashare_holder * 100 if first.ashare_holder else 0
    recent = shareholders[-4:]
    recent_changes = [
        recent[index].ashare_holder - recent[index - 1].ashare_holder
        for index in range(1, len(recent))
    ]
    if all(item < 0 for item in recent_changes):
        trend = "连续下降"
        conclusion = "近期股东人数连续下降，散户数量可能减少，筹码可能趋于集中。"
    elif all(item > 0 for item in recent_changes):
        trend = "连续上升"
        conclusion = "近期股东人数连续上升，筹码可能趋于分散，短期分歧可能增加。"
    elif change < 0:
        trend = "区间下降"
        conclusion = "区间内股东人数下降，浮筹压力可能有所减轻。"
    elif change > 0:
        trend = "区间上升"
        conclusion = "区间内股东人数上升，筹码分散度可能提升。"
    else:
        trend = "基本持平"
        conclusion = "区间内股东人数变化不大，筹码结构暂未出现明显方向。"
    return {
        "period_start": first.date,
        "period_end": latest.date,
        "start_holder_count": first.ashare_holder,
        "latest_holder_count": latest.ashare_holder,
        "change_count": change,
        "change_percent": round(change_percent, 2),
        "trend": trend,
        "conclusion": conclusion,
        "recent_points": [item.model_dump() for item in shareholders[-8:]],
    }


def _chip_payload(chip_distribution: ChipDistributionResponse | None) -> dict | None:
    if not chip_distribution or not chip_distribution.latest:
        return None
    latest = chip_distribution.latest
    return {
        "source": chip_distribution.source,
        "params": chip_distribution.params,
        "date": latest.date,
        "close": latest.close,
        "avg_cost": latest.avg_cost,
        "benefit_ratio_percent": round(latest.benefit_ratio * 100, 2),
        "main_cost_range_70": [latest.cost_70_low, latest.cost_70_high],
        "main_cost_range_90": [latest.cost_90_low, latest.cost_90_high],
        "concentration_70": latest.cost_70_concentration,
        "concentration_90": latest.cost_90_concentration,
        "support_price": latest.support_price,
        "pressure_price": latest.pressure_price,
        "relative_price_trend": latest.relative_price_trend,
        "concentration_trend": latest.concentration_trend,
        "conclusion": latest.interpretation,
        "recent_snapshots": [item.model_dump() for item in chip_distribution.snapshots[-10:]],
    }


def _technical_payload(macd: list[MacdPoint], chip_distribution: ChipDistributionResponse | None) -> dict | None:
    if not macd:
        return None
    latest = macd[-1]
    recent60 = macd[-60:]
    low60 = min(item.close for item in recent60)
    high60 = max(item.close for item in recent60)
    chip_latest = chip_distribution.latest if chip_distribution and chip_distribution.latest else None
    support = chip_latest.support_price if chip_latest and chip_latest.support_price else low60
    pressure = chip_latest.pressure_price if chip_latest and chip_latest.pressure_price else high60
    cross = _last_macd_cross(macd)
    divergence = _macd_divergence(macd)
    if latest.dif > latest.dea and latest.macd > 0:
        signal = "DIF位于DEA上方，MACD柱为正，短线动能处在修复或扩张状态。"
    elif latest.dif < latest.dea and latest.macd < 0:
        signal = "DIF位于DEA下方，MACD柱为负，短线动能偏弱。"
    else:
        signal = "DIF与DEA方向尚未完全统一，动能信号仍需确认。"
    box_position = (latest.close - low60) / (high60 - low60) if high60 != low60 else 0.5
    if box_position >= 0.8:
        box_text = "当前价格接近近60日波动区间上沿。"
    elif box_position <= 0.2:
        box_text = "当前价格接近近60日波动区间下沿。"
    else:
        box_text = "当前价格位于近60日波动区间中部。"
    return {
        "date": latest.date,
        "current_price": latest.close,
        "support_price": round(support, 2) if support is not None else None,
        "pressure_price": round(pressure, 2) if pressure is not None else None,
        "dif": latest.dif,
        "dea": latest.dea,
        "macd": latest.macd,
        "last_cross": cross,
        "divergence": divergence,
        "box": {
            "low_60d": round(low60, 2),
            "high_60d": round(high60, 2),
            "position_ratio": round(box_position, 4),
            "conclusion": box_text,
        },
        "conclusion": f"{signal}{box_text}",
        "recent_macd": [item.model_dump() for item in macd[-20:]],
    }


def _event_impact(event: StockEventPoint) -> tuple[str, str]:
    text = f"{event.title} {event.message}"
    if event.category == "风险提示":
        return "风险", "可能影响短期情绪或增加股价波动，后续仍需结合实际进展观察。"
    if any(keyword in text for keyword in ("回购", "增持", "解除质押")):
        return "机会", "可能对市场预期形成支撑，但仍需观察实际执行进度。"
    if any(keyword in text for keyword in ("限售解禁", "解禁", "减持", "质押", "对外担保", "担保")):
        return "风险", "可能对资金偏好造成扰动，或形成阶段性筹码供给压力。"
    return "机会", "可能影响市场预期，仍需结合事项落地进展观察。"


def _compact_event_message(event: StockEventPoint) -> str:
    text = " ".join(event.message.replace("\n", " ").split()).strip("。.!！?？")
    if not text:
        return event.category or "风险事项"
    fragments = [item.strip() for item in re.split(r"[，,；;。.!！?？]", text) if item.strip()]
    compact = "，".join(fragments[:2]) if fragments else text
    return compact if len(compact) <= 32 else f"{compact[:32]}..."


def _events_payload(events: list[StockEventPoint]) -> list[dict]:
    prepared: list[dict] = []
    for event in events:
        impact_type, possible_impact = _event_impact(event)
        prepared.append({
            "date": event.date,
            "timestamp": event.timestamp,
            "category": event.category,
            "impact_type": impact_type,
            "title": event.title,
            "message": event.message,
            "possible_impact": possible_impact,
        })
    priority = {"风险": 0, "机会": 1}
    return sorted(prepared, key=lambda item: (priority.get(item["impact_type"], 2), -int(item["timestamp"])))[:12]


def _standardized_llm_payload(
    name: str,
    code: str,
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    events: list[StockEventPoint],
    chip_distribution: ChipDistributionResponse | None,
) -> dict:
    latest_macd = macd[-1] if macd else None
    event_data = _events_payload(events)
    return {
        "stock": {
            "name": name or code,
            "code": code,
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "data_updated_at": latest_macd.date if latest_macd else "",
            "current_price": latest_macd.close if latest_macd else None,
        },
        "shareholders": _shareholder_payload(shareholders),
        "chip_distribution": _chip_payload(chip_distribution),
        "technical": _technical_payload(macd, chip_distribution),
        "events": event_data,
        "finance": {
            "recent_annual_net_profit": net_profit[-1].model_dump() if net_profit else None,
            "annual_points": [item.model_dump() for item in net_profit],
        } if net_profit else None,
        "output_notes": {
            "events_are_filtered": True,
            "event_sort_rule": "风险优先，同类按时间最近优先",
            "data_policy": "字段为None或空数组表示无有效数据，输出时跳过对应模块。",
        },
    }


def _compact_for_llm(
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    events: list[StockEventPoint],
    event_summary: str,
    chip_distribution: ChipDistributionResponse | None,
) -> dict:
    return {
        "macd_latest_60": [item.model_dump() for item in macd[-60:]],
        "chip_distribution": None if not chip_distribution else {
            "latest": chip_distribution.latest.model_dump() if chip_distribution.latest else None,
            "snapshots_latest_20": [item.model_dump() for item in chip_distribution.snapshots[-20:]],
            "params": chip_distribution.params,
        },
        "shareholders_3y": [item.model_dump() for item in shareholders],
        "net_profit_5y": [item.model_dump() for item in net_profit],
        "events_latest_30": [item.model_dump() for item in events[:30]],
        "event_summary": event_summary,
    }


async def _try_llm_summaries(
    name: str,
    code: str,
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    events: list[StockEventPoint],
    chip_distribution: ChipDistributionResponse | None,
) -> tuple[str, str, str]:
    event_summary = _fallback_event_summary(events)
    diagnosis_report = _fallback_diagnosis(
        name,
        code,
        macd,
        shareholders,
        net_profit,
        event_summary,
        chip_distribution,
    )

    config = load_config()
    model = config.selected_model or (config.available_models[0] if config.available_models else "")
    if not (config.provider.api_key and config.provider.base_url and model):
        return event_summary, diagnosis_report, "missing_config"

    client = create_client(config)
    payload = _standardized_llm_payload(
        name,
        code,
        macd,
        shareholders,
        net_profit,
        events,
        chip_distribution,
    )
    try:
        diagnosis_report = await chat_complete(
            client,
            model,
            [
                {
                    "role": "system",
                    "content": STOCK_DIAGNOSIS_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下标准化诊断数据生成股票诊断 Markdown 报告。"
                        "这些数据已经由后端清洗和计算，请优先使用其中的 conclusion、support_price、pressure_price、"
                        "last_cross、divergence、impact_type 与 possible_impact 字段。\n"
                        f"{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=config.settings.temperature,
            max_tokens=config.settings.max_tokens,
        )
        return event_summary, _normalize_report_labels(diagnosis_report), "ok"
    except Exception as exc:
        logger.warning("个股诊断LLM调用失败 [%s]: %s", code, exc)
        return event_summary, diagnosis_report, "error"


async def build_stock_diagnosis(code: str, name: str = "", include_llm: bool = False) -> StockDiagnosisResponse:
    """按需构建个股诊断结果。"""
    formatted_code = format_stock_code(extract_numeric_code(code))
    timings: dict[str, float] = {}
    data_errors: dict[str, str] = {}

    async def timed(label: str, func, *args, default=None):
        start = time.perf_counter()
        try:
            result = await asyncio.to_thread(func, *args)
            timings[label] = round((time.perf_counter() - start) * 1000, 2)
            return result
        except Exception as exc:
            timings[label] = round((time.perf_counter() - start) * 1000, 2)
            data_errors[label] = str(exc)[:300]
            logger.warning("个股诊断数据源失败 [%s][%s]: %s", formatted_code, label, exc)
            return [] if default is None else default

    close_task = timed("close_history", fetch_close_history_sync, formatted_code, MACD_WARMUP_DAYS)
    holders_task = timed("shareholders", fetch_shareholders_xq_sync, formatted_code, 20)
    finance_task = timed("finance_indicator_annual", fetch_finance_indicator_xq_sync, formatted_code, "Q4", 5)
    events_task = timed("events", fetch_stock_events_xq_sync, formatted_code, 200)
    chip_task = timed("chip_distribution", build_chip_distribution_sync, formatted_code)

    close_points, holder_items, finance_items, event_items, chip_distribution_result = await asyncio.gather(
        close_task,
        holders_task,
        finance_task,
        events_task,
        chip_task,
    )

    macd = _calculate_macd(close_points)
    moving_averages = _calculate_moving_averages(close_points)
    shareholders = _normalize_shareholders(holder_items)
    net_profit = _normalize_net_profit(finance_items)
    events = _normalize_events(event_items)
    chip_distribution = chip_distribution_result if isinstance(chip_distribution_result, ChipDistributionResponse) else None

    if include_llm:
        llm_start = time.perf_counter()
        event_summary, diagnosis_report, llm_status = await _try_llm_summaries(
            name,
            formatted_code,
            macd,
            shareholders,
            net_profit,
            events,
            chip_distribution,
        )
        timings["llm"] = round((time.perf_counter() - llm_start) * 1000, 2)
    else:
        event_summary = _fallback_event_summary(events)
        diagnosis_report = _fallback_diagnosis(
            name,
            formatted_code,
            macd,
            shareholders,
            net_profit,
            event_summary,
            chip_distribution,
        )
        llm_status = "not_requested"

    return StockDiagnosisResponse(
        code=formatted_code,
        name=name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source="xueqiu_akshare",
        timings_ms=timings,
        moving_averages=moving_averages,
        macd=macd,
        shareholders=shareholders,
        net_profit=net_profit,
        events=events,
        chip_distribution=chip_distribution,
        event_summary=event_summary,
        diagnosis_report=diagnosis_report,
        llm_status=llm_status,
        data_errors=data_errors,
    )


async def build_enhanced_stock_diagnosis(code: str, name: str = "") -> StockDiagnosisResponse:
    """构建带大模型强化报告的个股诊断结果。"""
    return await build_stock_diagnosis(code, name=name, include_llm=True)
