"""
筹码分布计算服务。
使用东方财富日K与换手率作为输入，在本地按CYQ逻辑估算持仓成本分布。
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from backend.models.diagnosis_models import (
    ChipDistributionResponse,
    ChipDistributionSnapshot,
    ChipHistogramBin,
)
from backend.services.akshare_adapter import extract_numeric_code, format_stock_code

CYQ_WINDOW_DAYS = 120
CYQ_BINS = 150
CYQ_WARMUP_COUNT = 210
CYQ_SNAPSHOT_COUNT = 90
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
XUEQIU_KLINE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
XUEQIU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    ),
}


def _market_code(code: str) -> str:
    formatted = format_stock_code(extract_numeric_code(code))
    market, pure_code = formatted.split(":", 1)
    return f"{1 if market == 'SH' else 0}.{pure_code}"


def _curl_json(url: str, params: dict[str, str | int]) -> dict:
    cmd = [
        "curl",
        "-sS",
        "-L",
        "--http1.1",
        "-A",
        "Mozilla/5.0",
        "--connect-timeout",
        "15",
        "--max-time",
        "30",
        f"{url}?{urlencode(params)}",
    ]
    last_error = ""
    for attempt in range(3):
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return json.loads(completed.stdout)
        last_error = completed.stderr.strip() or completed.stdout.strip() or f"curl exit {completed.returncode}"
        time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(last_error)


def _fetch_eastmoney_daily_kline(code: str, count: int = CYQ_WARMUP_COUNT) -> list[dict]:
    payload = _curl_json(
        EASTMONEY_KLINE_URL,
        {
            "secid": _market_code(code),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "0",
            "end": datetime.now().strftime("%Y%m%d"),
            "lmt": str(count),
        },
    )
    klines = ((payload.get("data") or {}).get("klines")) or []
    rows: list[dict] = []
    for item in klines:
        parts = item.split(",")
        if len(parts) < 11:
            continue
        timestamp = int(datetime.strptime(parts[0], "%Y-%m-%d").timestamp() * 1000)
        rows.append({
            "date": parts[0],
            "timestamp": timestamp,
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": float(parts[5]),
            "amount": float(parts[6]),
            "turnover_rate": float(parts[10]),
        })
    if not rows:
        raise RuntimeError(f"东方财富K线响应为空: {str(payload)[:300]}")
    return rows


def _xueqiu_symbol(code: str) -> str:
    formatted = format_stock_code(extract_numeric_code(code))
    market, pure_code = formatted.split(":", 1)
    return f"{market}{pure_code}"


def _fetch_xueqiu_daily_kline(code: str, count: int = CYQ_WARMUP_COUNT) -> list[dict]:
    symbol = _xueqiu_symbol(code)
    session = requests.Session()
    session.trust_env = False
    headers = {**XUEQIU_HEADERS, "Referer": f"https://xueqiu.com/S/{symbol}"}
    session.get(f"https://xueqiu.com/S/{symbol}", headers=headers, timeout=10)
    resp = session.get(
        XUEQIU_KLINE_URL,
        params={
            "symbol": symbol,
            "begin": int(time.time() * 1000),
            "period": "day",
            "type": "before",
            "count": -abs(count),
            "indicator": "kline",
        },
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or {}
    columns = data.get("column") or []
    items = data.get("item") or []
    rows: list[dict] = []
    for item in items:
        row = dict(zip(columns, item))
        timestamp = int(row["timestamp"])
        rows.append({
            "date": datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d"),
            "timestamp": timestamp,
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]),
            "turnover_rate": float(row.get("turnoverrate") or 0),
        })
    if not rows:
        raise RuntimeError(f"雪球K线响应为空: {str(payload)[:300]}")
    return rows


def _fetch_chip_kline(code: str) -> tuple[list[dict], str]:
    try:
        return _fetch_eastmoney_daily_kline(code, CYQ_WARMUP_COUNT), "eastmoney_kline_local_cyq"
    except Exception:
        return _fetch_xueqiu_daily_kline(code, CYQ_WARMUP_COUNT), "xueqiu_kline_local_cyq"


def _cost_by_chip(xdata: list[float], min_price: float, accuracy: float, chip: float) -> float:
    total_seen = 0.0
    for price_index, value in enumerate(xdata):
        if total_seen + value > chip:
            return min_price + price_index * accuracy
        total_seen += value
    return min_price + (len(xdata) - 1) * accuracy


def _percent_chips(
    xdata: list[float],
    min_price: float,
    accuracy: float,
    total_chips: float,
    percent: float,
) -> tuple[float, float, float]:
    low_cost = _cost_by_chip(xdata, min_price, accuracy, total_chips * ((1 - percent) / 2))
    high_cost = _cost_by_chip(xdata, min_price, accuracy, total_chips * ((1 + percent) / 2))
    concentration = 0 if low_cost + high_cost == 0 else (high_cost - low_cost) / (low_cost + high_cost)
    return low_cost, high_cost, concentration


def _find_peak(histogram: list[ChipHistogramBin], close: float, side: str) -> float | None:
    if side == "support":
        candidates = [item for item in histogram if item.price <= close]
    else:
        candidates = [item for item in histogram if item.price >= close]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.percent).price


def _trend_text(current: float, previous: float, higher_word: str, lower_word: str, flat_word: str) -> str:
    if previous == 0:
        return flat_word
    change = (current - previous) / abs(previous)
    if change > 0.015:
        return higher_word
    if change < -0.015:
        return lower_word
    return flat_word


def _build_interpretation(
    close: float,
    previous_close: float,
    concentration: float,
    previous_concentration: float,
) -> tuple[str, str, str]:
    price_trend = _trend_text(close, previous_close, "相对价位变高", "相对价位变低", "相对价位持平")
    concentration_trend = _trend_text(
        previous_concentration,
        concentration,
        "筹码密集程度变高",
        "筹码密集程度变低",
        "筹码密集程度持平",
    )
    return price_trend, concentration_trend, f"近期{price_trend}，{concentration_trend}"


def _calculate_snapshot(index: int, rows: list[dict], previous_summary: ChipDistributionSnapshot | None) -> tuple[ChipDistributionSnapshot, list[ChipHistogramBin]]:
    start = max(0, index - CYQ_WINDOW_DAYS + 1)
    kdata = rows[start:index + 1]
    max_price = max(row["high"] for row in kdata)
    min_price = min(row["low"] for row in kdata)
    accuracy = max(0.01, (max_price - min_price) / (CYQ_BINS - 1))
    xdata = [0.0] * CYQ_BINS

    for row in kdata:
        open_price = row["open"]
        close = row["close"]
        high = row["high"]
        low = row["low"]
        avg = (open_price + close + high + low) / 4
        turnover = min(1, (row.get("turnover_rate") or 0) / 100)
        high_index = math.floor((high - min_price) / accuracy)
        low_index = math.ceil((low - min_price) / accuracy)
        g_factor = CYQ_BINS - 1 if high == low else 2 / (high - low)
        g_index = max(0, min(CYQ_BINS - 1, math.floor((avg - min_price) / accuracy)))
        xdata = [value * (1 - turnover) for value in xdata]

        if high == low:
            xdata[g_index] += g_factor * turnover / 2
            continue

        for price_index in range(max(0, low_index), min(CYQ_BINS - 1, high_index) + 1):
            current_price = min_price + accuracy * price_index
            if current_price <= avg:
                if abs(avg - low) < 1e-8:
                    xdata[price_index] += g_factor * turnover
                else:
                    xdata[price_index] += (current_price - low) / (avg - low) * g_factor * turnover
            elif abs(high - avg) < 1e-8:
                xdata[price_index] += g_factor * turnover
            else:
                xdata[price_index] += (high - current_price) / (high - avg) * g_factor * turnover

    current = rows[index]
    total_chips = sum(xdata)
    benefit = sum(
        value
        for price_index, value in enumerate(xdata)
        if current["close"] >= min_price + price_index * accuracy
    )
    low90, high90, con90 = _percent_chips(xdata, min_price, accuracy, total_chips, 0.9)
    low70, high70, con70 = _percent_chips(xdata, min_price, accuracy, total_chips, 0.7)
    avg_cost = _cost_by_chip(xdata, min_price, accuracy, total_chips * 0.5)
    histogram = [
        ChipHistogramBin(
            price=round(min_price + price_index * accuracy, 2),
            percent=round((value / total_chips * 100) if total_chips else 0, 6),
            profitable=(min_price + price_index * accuracy) <= current["close"],
        )
        for price_index, value in enumerate(xdata)
        if value > 0
    ]
    support_price = _find_peak(histogram, current["close"], "support")
    pressure_price = _find_peak(histogram, current["close"], "pressure")

    previous_close = previous_summary.close if previous_summary else current["close"]
    previous_concentration = previous_summary.cost_70_concentration if previous_summary else con70
    price_trend, concentration_trend, interpretation = _build_interpretation(
        current["close"],
        previous_close,
        con70,
        previous_concentration,
    )
    snapshot = ChipDistributionSnapshot(
        date=current["date"],
        timestamp=current["timestamp"],
        close=round(current["close"], 2),
        benefit_ratio=round((benefit / total_chips) if total_chips else 0, 6),
        avg_cost=round(avg_cost, 2),
        cost_90_low=round(low90, 2),
        cost_90_high=round(high90, 2),
        cost_90_concentration=round(con90, 6),
        cost_70_low=round(low70, 2),
        cost_70_high=round(high70, 2),
        cost_70_concentration=round(con70, 6),
        support_price=round(support_price, 2) if support_price is not None else None,
        pressure_price=round(pressure_price, 2) if pressure_price is not None else None,
        relative_price_trend=price_trend,
        concentration_trend=concentration_trend,
        interpretation=interpretation,
    )
    return snapshot, histogram


def build_chip_distribution_sync(code: str) -> ChipDistributionResponse:
    """生成最近90个交易日的CYQ筹码分布。"""
    rows, source = _fetch_chip_kline(code)
    snapshots: list[ChipDistributionSnapshot] = []
    histograms: dict[str, list[ChipHistogramBin]] = {}
    start_index = max(0, len(rows) - CYQ_SNAPSHOT_COUNT)
    previous_summary: ChipDistributionSnapshot | None = None

    for index in range(start_index, len(rows)):
        snapshot, histogram = _calculate_snapshot(index, rows, previous_summary)
        snapshots.append(snapshot)
        histograms[snapshot.date] = histogram
        previous_summary = snapshot

    latest = snapshots[-1] if snapshots else None
    return ChipDistributionResponse(
        source=source,
        params={
            "window": CYQ_WINDOW_DAYS,
            "bins": CYQ_BINS,
            "warmup_count": CYQ_WARMUP_COUNT,
            "snapshot_count": CYQ_SNAPSHOT_COUNT,
        },
        snapshots=snapshots,
        latest=latest,
        histogram=histograms.get(latest.date, []) if latest else [],
        histograms=histograms,
    )
