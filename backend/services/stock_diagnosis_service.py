"""
个股诊断服务
点击股票后按需拉取历史行情、股东人数、财报和公司大事，并生成诊断结果。
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

from backend.models.diagnosis_models import (
    MacdPoint,
    NetProfitPoint,
    ShareholderPoint,
    StockDiagnosisResponse,
    StockEventPoint,
)
from backend.services.akshare_adapter import (
    extract_numeric_code,
    fetch_close_history_xq_sync,
    fetch_finance_indicator_xq_sync,
    fetch_shareholders_xq_sync,
    fetch_stock_events_xq_sync,
    format_stock_code,
)
from backend.services.file_service import load_config
from backend.services.llm_client import chat_complete, create_client

logger = logging.getLogger(__name__)

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ONE_YEAR_TRADING_DAYS = 250
MACD_WARMUP_DAYS = 500


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
        tags = item.get("tags") or []
        sentiment = None
        if tags and isinstance(tags, list):
            sentiment = str(tags[0].get("description") or "") or None
        events.append(StockEventPoint(
            date=_date_from_ms(timestamp),
            timestamp=timestamp,
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
        return "近五年暂未取得结构化大事提醒。"
    title_counts: dict[str, int] = {}
    for event in events:
        title_counts[event.title] = title_counts.get(event.title, 0) + 1
    top_titles = "、".join(f"{title} {count}次" for title, count in list(title_counts.items())[:5])
    latest = events[0]
    return f"已取得近五年大事提醒 {len(events)} 条，主要类型包括 {top_titles}。最新事件为 {latest.date} 的“{latest.title}”：{latest.message}"


def _fallback_diagnosis(
    name: str,
    code: str,
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    event_summary: str,
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

    return (
        f"{name or code} 个股诊断已完成。当前未取得大模型诊断，以下为本地规则摘要：\n\n"
        f"1. 技术面：{macd_text}\n"
        f"2. 股东结构：{holder_text}\n"
        f"3. 盈利趋势：{profit_text}\n"
        f"4. 大事提醒：{event_summary}\n\n"
        "后续配置大模型 API 后，右侧报告会替换为更完整的综合诊断。"
    )


def _compact_for_llm(
    macd: list[MacdPoint],
    shareholders: list[ShareholderPoint],
    net_profit: list[NetProfitPoint],
    events: list[StockEventPoint],
    event_summary: str,
) -> dict:
    return {
        "macd_latest_60": [item.model_dump() for item in macd[-60:]],
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
) -> tuple[str, str, str]:
    event_summary = _fallback_event_summary(events)
    diagnosis_report = _fallback_diagnosis(name, code, macd, shareholders, net_profit, event_summary)

    config = load_config()
    model = config.selected_model or (config.available_models[0] if config.available_models else "")
    if not (config.provider.api_key and config.provider.base_url and model):
        return event_summary, diagnosis_report, "missing_config"

    client = create_client(config)
    payload = _compact_for_llm(macd, shareholders, net_profit, events, event_summary)
    try:
        event_summary = await chat_complete(
            client,
            model,
            [
                {"role": "system", "content": "你是A股上市公司事件分析助手，只基于输入数据总结，不做虚构。"},
                {
                    "role": "user",
                    "content": (
                        f"请总结{name or code}近五年公司大事提醒，按利好、利空、中性分类，指出需要继续核验的事项。\n"
                        f"{json.dumps([item.model_dump() for item in events[:60]], ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=config.settings.temperature,
            max_tokens=min(config.settings.max_tokens, 1600),
        )
        payload["event_summary"] = event_summary
        diagnosis_report = await chat_complete(
            client,
            model,
            [
                {
                    "role": "system",
                    "content": (
                        "你是谨慎的A股个股诊断分析师。输出要有结论、依据、风险和后续跟踪指标，不构成投资建议。"
                        "技术面必须主要结合DIF、DEA、MACD柱判断趋势、箱体震荡、突破或背离状态。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请基于以下数据生成{name or code}({code})个股诊断报告，重点评估长期是否值得进入观察/买入候选池。\n"
                        "技术面请结合最近60个交易日DIF/DEA/MACD变化，判断是否仍在箱体、是否有放量突破或短线过热风险。\n"
                        f"{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=config.settings.temperature,
            max_tokens=config.settings.max_tokens,
        )
        return event_summary, diagnosis_report, "ok"
    except Exception as exc:
        logger.warning("个股诊断LLM调用失败 [%s]: %s", code, exc)
        return event_summary, diagnosis_report, "error"


async def build_stock_diagnosis(code: str, name: str = "") -> StockDiagnosisResponse:
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

    close_task = timed("close_history", fetch_close_history_xq_sync, formatted_code, MACD_WARMUP_DAYS)
    holders_task = timed("shareholders", fetch_shareholders_xq_sync, formatted_code)
    finance_task = timed("finance_indicator_annual", fetch_finance_indicator_xq_sync, formatted_code, "Q4", 5)
    events_task = timed("events", fetch_stock_events_xq_sync, formatted_code, 200)

    close_points, holder_items, finance_items, event_items = await asyncio.gather(
        close_task,
        holders_task,
        finance_task,
        events_task,
    )

    macd = _calculate_macd(close_points)
    shareholders = _normalize_shareholders(holder_items)
    net_profit = _normalize_net_profit(finance_items)
    events = _normalize_events(event_items)

    llm_start = time.perf_counter()
    event_summary, diagnosis_report, llm_status = await _try_llm_summaries(
        name,
        formatted_code,
        macd,
        shareholders,
        net_profit,
        events,
    )
    timings["llm"] = round((time.perf_counter() - llm_start) * 1000, 2)

    return StockDiagnosisResponse(
        code=formatted_code,
        name=name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        timings_ms=timings,
        macd=macd,
        shareholders=shareholders,
        net_profit=net_profit,
        events=events,
        event_summary=event_summary,
        diagnosis_report=diagnosis_report,
        llm_status=llm_status,
        data_errors=data_errors,
    )
