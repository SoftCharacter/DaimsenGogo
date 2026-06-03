"""
AkShare数据源适配层
统一封装项目中使用的股票列表、实时行情、日K线和公司信息查询，
避免业务层直接依赖新浪财经或东方财富接口字段。
"""
from datetime import datetime
import contextlib
import io
import json
import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from backend.models.stock_models import StockQuote, KLinePoint

logger = logging.getLogger(__name__)

# 近一个月按A股交易日约等于22个交易日
_MONTH_TRADING_DAYS = 22
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_TASK_CACHE_DIR = _DATA_DIR / "task_cache"
_SHARED_TASK_ID = "_shared"
_XQ_QUOTE_URL = "https://stock.xueqiu.com/v5/stock/quote.json"
_XQ_KLINE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
_XQ_FINANCE_INDICATOR_URL = "https://stock.xueqiu.com/v5/stock/finance/cn/indicator.json"
_XQ_HOLDERS_URL = "https://stock.xueqiu.com/v5/stock/f10/cn/holders.json"
_XQ_EVENT_URL = "https://stock.xueqiu.com/v5/stock/screener/event/list.json"
_XQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
}


def _warm_xq_cookie(session: requests.Session, headers: dict[str, str], symbol: str) -> None:
    """通过雪球行情页预热 xq_a_token，失败或缺失时继续原请求流程。"""
    try:
        session.get("https://xueqiu.com/hq", headers=headers, timeout=10)
    except Exception as exc:
        logger.debug("雪球 hq 预热失败，继续原请求流程 [%s]: %s", symbol, exc)
    if not session.cookies.get("xq_a_token"):
        logger.debug("雪球 hq 预热未获取 xq_a_token，继续原请求流程 [%s]", symbol)


def _xq_token_cookies(session: requests.Session) -> dict[str, str] | None:
    """仅在已解析到 xq_a_token 时为后续雪球接口显式追加 Cookie。"""
    token = session.cookies.get("xq_a_token")
    return {"xq_a_token": token} if token else None


_STOCK_LIST_REMOTE_ATTEMPTS = 2
# Baostock 子进程整体超时（秒）。子进程需冷启动全新解释器并重新 import baostock
# （连带 pandas/numpy），叠加 login 与 query_stock_basic 遍历全量股票的网络耗时，
# warm 查询虽 <10s，但冷启动+网络抖动易顶破 15s。初始化已改后台线程不阻塞启动，
# 故放宽到 40s 给足余量，避免误判超时。
_BAOSTOCK_SUBPROCESS_TIMEOUT_SECONDS = 40
_stock_list_memory_cache: list[dict] = []
_stock_list_initialized = False
_stock_list_lock = threading.Lock()
_AKSHARE_SPOT_CACHE_TTL = 60
_akshare_spot_cache: tuple[float, list[dict]] | None = None
_akshare_spot_lock = threading.Lock()
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _run_without_proxy(func):
    """临时清除代理环境变量，避免本机代理影响AkShare请求"""
    old_values = {key: os.environ.get(key) for key in _PROXY_ENV_KEYS}
    try:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        return func()
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_quietly(func):
    """屏蔽第三方数据源的进度条输出，保留业务日志可读性。"""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func()


def _safe_task_id(task_id: str | None) -> str:
    """清理任务ID，确保缓存目录不会发生路径穿越。"""
    if not task_id:
        return _SHARED_TASK_ID
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())
    return cleaned[:80] or _SHARED_TASK_ID


def _task_cache_dir(task_id: str | None) -> Path:
    """返回任务级缓存目录。"""
    return _TASK_CACHE_DIR / _safe_task_id(task_id)


def _stock_list_cache_path(task_id: str | None = None) -> Path:
    """返回共享股票列表缓存路径。"""
    return _task_cache_dir(_SHARED_TASK_ID) / "stock_list.json"


def _task_data_cache_path(task_id: str | None, filename: str) -> Path | None:
    """返回任务级股票数据缓存路径；无任务ID时不落到共享目录。"""
    if not task_id:
        return None
    return _task_cache_dir(task_id) / filename


def _quote_cache_path(task_id: str | None) -> Path | None:
    """返回任务级实时行情缓存路径。"""
    return _task_data_cache_path(task_id, "akshare_quotes_cache.json")


def _kline_cache_path(task_id: str | None) -> Path | None:
    """返回任务级K线缓存路径。"""
    return _task_data_cache_path(task_id, "akshare_kline_cache.json")


def _company_cache_path(task_id: str | None) -> Path | None:
    """返回任务级公司信息缓存路径。"""
    return _task_data_cache_path(task_id, "akshare_company_cache.json")


def _read_json_cache(path: Path | None, default):
    """读取本地JSON缓存，失败时返回默认值"""
    if path is None:
        return default
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_json_cache(path: Path | None, data) -> None:
    """写入本地JSON缓存，失败时不影响主流程"""
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _is_valid_stock_list(stock_list) -> bool:
    """判断股票列表是否可作为校验和搜索的有效数据源。"""
    return (
        isinstance(stock_list, list)
        and len(stock_list) > 0
        and all(isinstance(item, dict) and item.get("code") and item.get("name") for item in stock_list)
    )


def _write_stock_list_cache(stock_list: list[dict], task_id: str | None = None) -> None:
    """只缓存有效股票列表，避免空列表覆盖可用缓存。"""
    if _is_valid_stock_list(stock_list):
        _write_json_cache(_stock_list_cache_path(), stock_list)


def _is_stock_list_cache_fresh(path: Path) -> bool:
    """判断股票列表缓存文件是否为当天生成。"""
    try:
        if not path.exists():
            return False
        modified_date = datetime.fromtimestamp(path.stat().st_mtime).date()
        return modified_date == datetime.now().date()
    except OSError:
        return False


def format_stock_code(raw_code: str) -> str:
    """
    将纯数字股票代码转换为项目统一格式
    规则: 6开头为沪市，0/3开头为深市，4/8开头为北交所。
    """
    code = str(raw_code).zfill(6)
    if code.startswith("6"):
        return f"SH:{code}"
    if code.startswith(("0", "3")):
        return f"SZ:{code}"
    if code.startswith(("4", "8")):
        return f"BJ:{code}"
    return f"SZ:{code}"


def extract_numeric_code(code: str) -> str:
    """
    从统一代码或混合文本中提取6位数字代码
    示例: SH:601138 -> 601138, SZ002261 -> 002261。
    """
    import re

    match = re.search(r"\d{6}", code)
    return match.group() if match else code.strip()


def _safe_float(value) -> float:
    """安全转换浮点数，空值或异常值统一返回0"""
    try:
        if value in (None, "", "-"):
            return 0.0
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_volume(volume: float) -> str:
    """将成交额格式化为中文单位，供前端股票卡片展示"""
    if volume >= 1e8:
        return f"{volume / 1e8:.2f}亿"
    if volume >= 1e4:
        return f"{volume / 1e4:.2f}万"
    return f"{volume:.2f}"


def _to_tx_symbol(num: str) -> str:
    """转换为AkShare腾讯日线接口需要的市场前缀格式"""
    code = format_stock_code(num)
    market, pure_code = code.split(":", 1)
    return f"{market.lower()}{pure_code}"


def _to_xq_symbol(code: str) -> str:
    """转换为雪球个股行情接口需要的市场前缀格式。"""
    formatted = format_stock_code(extract_numeric_code(code))
    market, pure_code = formatted.split(":", 1)
    return f"{market}{pure_code}"


def _company_name_from_info(info: dict) -> str:
    """从AkShare公司信息字典中提取股票简称"""
    return str(
        info.get("股票简称")
        or info.get("股票名称")
        or info.get("简称")
        or ""
    )


def _stock_list_from_akshare() -> list[dict]:
    """通过AkShare获取股票列表，带有限重试和退避。"""
    import akshare as ak

    for attempt in range(_STOCK_LIST_REMOTE_ATTEMPTS):
        try:
            df = _run_without_proxy(lambda: _run_quietly(ak.stock_zh_a_spot_em))
            result: list[dict] = []
            for _, row in df.iterrows():
                code = str(row.get("代码", "")).zfill(6)
                name = str(row.get("名称", ""))
                if code and name:
                    result.append({"code": format_stock_code(code), "name": name})
            if _is_valid_stock_list(result):
                return result
            logger.warning("AkShare股票列表为空或结构无效，第%d次", attempt + 1)
        except Exception as exc:
            logger.warning("AkShare股票列表获取失败，第%d次: %s", attempt + 1, exc)
        time.sleep((2 ** attempt) + random.uniform(0, 1.5))
    return []


def _stock_list_from_baostock_once() -> list[dict]:
    """通过Baostock子进程获取一次股票列表，避免login卡死阻塞主进程。"""
    script = r'''
import json
import sys
try:
    import baostock as bs
except Exception:
    print("[]")
    sys.exit(0)

lg = bs.login()
if lg.error_code != "0":
    bs.logout()
    print("[]")
    sys.exit(0)

rs = bs.query_stock_basic()
items = []
while rs.error_code == "0" and rs.next():
    row = rs.get_row_data()
    if len(row) < 6:
        continue
    bs_code = row[0]
    name = row[1]
    stock_type = row[4]
    status = row[5]
    if stock_type != "1" or status != "1" or not name or "." not in bs_code:
        continue
    market, num = bs_code.split(".", 1)
    if market == "sh":
        code = f"SH:{num}"
    elif market == "sz":
        code = f"SZ:{num}"
    elif market == "bj":
        code = f"BJ:{num}"
    else:
        continue
    items.append({"code": code, "name": name})
bs.logout()
print(json.dumps(items, ensure_ascii=False))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_BAOSTOCK_SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"子进程退出码 {completed.returncode}")

    stdout = completed.stdout.strip()
    json_start = stdout.rfind("[")
    try:
        stock_list = json.loads(stdout[json_start:] if json_start >= 0 else "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("返回无法解析") from exc
    if not _is_valid_stock_list(stock_list):
        raise ValueError("股票列表为空或结构无效")
    return stock_list


def _stock_list_from_baostock() -> list[dict]:
    """通过Baostock获取股票列表，带有限重试和退避。"""
    for attempt in range(_STOCK_LIST_REMOTE_ATTEMPTS):
        try:
            return _stock_list_from_baostock_once()
        except subprocess.TimeoutExpired:
            logger.warning("Baostock股票列表获取超时，第%d次", attempt + 1)
        except ValueError as exc:
            message = str(exc)
            if message == "返回无法解析":
                logger.warning("Baostock股票列表返回无法解析，第%d次", attempt + 1)
            else:
                logger.warning("Baostock股票列表为空或结构无效，第%d次", attempt + 1)
        except Exception as exc:
            logger.warning("Baostock股票列表获取失败，第%d次: %s", attempt + 1, exc)
        time.sleep((2 ** attempt) + random.uniform(0, 1.5))
    return []


def _load_stock_list_cache() -> list[dict]:
    """读取共享股票列表缓存，缓存无效时返回空列表。"""
    cached = _read_json_cache(_stock_list_cache_path(), [])
    return cached if _is_valid_stock_list(cached) else []


def initialize_stock_list_cache(task_id: str | None = None) -> None:
    """后端启动时初始化股票列表；仅当天缓存无效时才远程刷新。"""
    global _stock_list_initialized, _stock_list_memory_cache
    cache_path = _stock_list_cache_path(task_id)
    with _stock_list_lock:
        cached = _load_stock_list_cache()
        if _is_valid_stock_list(cached):
            _stock_list_memory_cache = cached
        if _is_valid_stock_list(cached) and _is_stock_list_cache_fresh(cache_path):
            _stock_list_initialized = True
            return

        stock_list = _stock_list_from_akshare()
        if not _is_valid_stock_list(stock_list):
            stock_list = _stock_list_from_baostock()
        if _is_valid_stock_list(stock_list):
            _write_stock_list_cache(stock_list, task_id=task_id)
            _stock_list_memory_cache = stock_list
        elif _is_valid_stock_list(cached):
            _stock_list_memory_cache = cached
        else:
            _stock_list_memory_cache = []
        _stock_list_initialized = True


def get_stock_list(task_id: str | None = None) -> list[dict]:
    """
    获取A股股票列表
    返回项目统一结构: [{"code": "SH:601138", "name": "工业富联"}]。
    """
    with _stock_list_lock:
        if _is_valid_stock_list(_stock_list_memory_cache):
            return list(_stock_list_memory_cache)
        cached = _load_stock_list_cache()
        if _is_valid_stock_list(cached):
            return cached
        return []


def _fetch_xq_quote(symbol: str) -> dict:
    """直接请求雪球原始行情接口，返回 data.quote 字段。"""
    def request_quote() -> dict:
        session = requests.Session()
        _warm_xq_cookie(session, _XQ_HEADERS, symbol)
        resp = session.get(
            _XQ_QUOTE_URL,
            params={"symbol": symbol, "extend": "detail"},
            headers=_XQ_HEADERS,
            cookies=_xq_token_cookies(session),
            timeout=10,
        )
        payload = resp.json()
        quote = payload.get("data", {}).get("quote")
        if not quote:
            logger.warning("雪球原始响应缺少data.quote [%s]: %s", symbol, str(payload)[:500])
            return {}
        return quote

    return _run_without_proxy(request_quote)


def _fetch_xq_json_sync(symbol: str, url: str, params: dict, timeout: int = 20) -> dict:
    """请求雪球JSON接口，自动预热cookie。"""
    def request_json() -> dict:
        session = requests.Session()
        headers = {**_XQ_HEADERS, "Referer": f"https://xueqiu.com/S/{symbol}"}
        _warm_xq_cookie(session, headers, symbol)
        resp = session.get(url, params=params, headers=headers, cookies=_xq_token_cookies(session), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    payload = _run_without_proxy(request_json)
    if isinstance(payload, dict) and payload.get("error_code", 0) not in (0, None):
        raise RuntimeError(f"雪球接口返回错误: {str(payload)[:300]}")
    return payload


def fetch_close_history_xq_sync(code: str, count: int = 250) -> list[dict]:
    """
    使用雪球原生日K接口获取历史收盘价。

    count 按交易日数量理解；1年A股交易日近似为250个交易日。
    """
    symbol = _to_xq_symbol(code)

    def request_kline() -> dict:
        session = requests.Session()
        headers = {**_XQ_HEADERS, "Referer": f"https://xueqiu.com/S/{symbol}"}
        _warm_xq_cookie(session, headers, symbol)
        resp = session.get(
            _XQ_KLINE_URL,
            params={
                "symbol": symbol,
                "begin": int(time.time() * 1000),
                "period": "day",
                "type": "before",
                "count": -abs(int(count)),
                "indicator": "kline",
            },
            headers=headers,
            cookies=_xq_token_cookies(session),
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    payload = _run_without_proxy(request_kline)
    data = payload.get("data") or {}
    columns = data.get("column") or []
    items = data.get("item") or []
    if not columns or not items:
        raise RuntimeError(f"雪球K线响应为空: {str(payload)[:300]}")
    try:
        timestamp_index = columns.index("timestamp")
        close_index = columns.index("close")
    except ValueError as exc:
        raise RuntimeError(f"雪球K线响应缺少必要字段: {columns}") from exc

    points: list[dict] = []
    for item in items:
        timestamp = int(item[timestamp_index])
        close = _safe_float(item[close_index])
        points.append({
            "date": datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d"),
            "timestamp": timestamp,
            "close": close,
        })
    return points


def _close_history_from_df(df, count: int) -> list[dict]:
    """从AkShare日线DataFrame提取诊断所需的收盘价序列。"""
    points: list[dict] = []
    if df is None or getattr(df, "empty", True):
        return points

    for _, row in df.tail(max(1, int(count))).iterrows():
        date_value = row.get("date", row.get("日期"))
        close = _safe_float(row.get("close", row.get("收盘")))
        if not date_value or not close:
            continue
        date_text = str(date_value)[:10]
        try:
            timestamp = int(datetime.strptime(date_text, "%Y-%m-%d").timestamp() * 1000)
        except ValueError:
            timestamp = 0
        points.append({
            "date": date_text,
            "timestamp": timestamp,
            "close": close,
        })
    return points


def _fetch_close_history_akshare_tx_sync(code: str, count: int = 250) -> list[dict]:
    """使用AkShare腾讯历史行情接口获取日线收盘价。"""
    import akshare as ak

    num = extract_numeric_code(code)
    df = _run_without_proxy(
        lambda: _run_quietly(lambda: ak.stock_zh_a_hist_tx(symbol=_to_tx_symbol(num), adjust="qfq"))
    )
    points = _close_history_from_df(df, count)
    if not points:
        raise RuntimeError("AkShare stock_zh_a_hist_tx 响应为空")
    return points


def _fetch_close_history_akshare_sina_sync(code: str, count: int = 250) -> list[dict]:
    """使用AkShare新浪历史行情接口获取日线收盘价。"""
    import akshare as ak

    num = extract_numeric_code(code)
    df = _run_without_proxy(
        lambda: _run_quietly(lambda: ak.stock_zh_a_daily(symbol=_to_tx_symbol(num), adjust="qfq"))
    )
    points = _close_history_from_df(df, count)
    if not points:
        raise RuntimeError("AkShare stock_zh_a_daily 响应为空")
    return points


def _fetch_daily_kline_df_akshare_tx(code: str):
    """使用AkShare腾讯历史行情接口获取日K DataFrame。"""
    import akshare as ak

    num = extract_numeric_code(code)
    return _run_without_proxy(
        lambda: _run_quietly(lambda: ak.stock_zh_a_hist_tx(symbol=_to_tx_symbol(num), adjust="qfq"))
    )


def _fetch_daily_kline_df_akshare_sina(code: str):
    """使用AkShare新浪历史行情接口获取日K DataFrame。"""
    import akshare as ak

    num = extract_numeric_code(code)
    return _run_without_proxy(
        lambda: _run_quietly(lambda: ak.stock_zh_a_daily(symbol=_to_tx_symbol(num), adjust="qfq"))
    )


def fetch_close_history_sync(code: str, count: int = 250) -> list[dict]:
    """优先使用雪球收盘价序列，失败时回退到AkShare历史行情。"""
    formatted_code = format_stock_code(extract_numeric_code(code))
    errors: list[str] = []
    try:
        return fetch_close_history_xq_sync(formatted_code, count=count)
    except Exception as exc:
        errors.append(f"雪球: {exc}")
        logger.warning("雪球收盘价获取失败，使用AkShare腾讯日线兜底 [%s]: %s", formatted_code, exc)

    try:
        return _fetch_close_history_akshare_tx_sync(formatted_code, count=count)
    except Exception as exc:
        errors.append(f"AkShare stock_zh_a_hist_tx: {exc}")
        logger.warning("AkShare腾讯日线获取失败，使用AkShare新浪日线兜底 [%s]: %s", formatted_code, exc)

    try:
        return _fetch_close_history_akshare_sina_sync(formatted_code, count=count)
    except Exception as exc:
        errors.append(f"AkShare stock_zh_a_daily: {exc}")

    raise RuntimeError(f"雪球与AkShare历史收盘价均获取失败，请检查接口。{' | '.join(errors)}")


def _spot_rows_from_sina() -> list[dict]:
    """使用AkShare新浪实时行情接口获取A股现价列表。"""
    import akshare as ak

    df = _run_without_proxy(lambda: _run_quietly(ak.stock_zh_a_spot))
    rows: list[dict] = []
    for _, row in df.iterrows():
        formatted_code = format_stock_code(extract_numeric_code(str(row.get("代码", ""))))
        current = _safe_float(row.get("最新价"))
        if not formatted_code or not current:
            continue
        prev_close = _safe_float(row.get("昨收"))
        change = _safe_float(row.get("涨跌额"))
        change_percent = _safe_float(row.get("涨跌幅"))
        if not change and current and prev_close:
            change = current - prev_close
        if not change_percent and change and prev_close:
            change_percent = change / prev_close * 100
        rows.append({
            "code": formatted_code,
            "name": str(row.get("名称") or ""),
            "current_price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "open_price": round(_safe_float(row.get("今开")), 2),
            "high": round(_safe_float(row.get("最高")), 2),
            "low": round(_safe_float(row.get("最低")), 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "volume": _safe_float(row.get("成交额")),
            "volume_display": format_volume(_safe_float(row.get("成交额"))),
            "timestamp": str(row.get("时间戳") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        })
    if not rows:
        raise RuntimeError("AkShare stock_zh_a_spot 响应为空")
    return rows


def _spot_rows_from_eastmoney() -> list[dict]:
    """使用AkShare东方财富实时行情接口获取A股现价列表。"""
    import akshare as ak

    df = _run_without_proxy(lambda: _run_quietly(ak.stock_zh_a_spot_em))
    rows: list[dict] = []
    for _, row in df.iterrows():
        formatted_code = format_stock_code(extract_numeric_code(str(row.get("代码", ""))))
        current = _safe_float(row.get("最新价"))
        if not formatted_code or not current:
            continue
        prev_close = _safe_float(row.get("昨收"))
        change = _safe_float(row.get("涨跌额"))
        change_percent = _safe_float(row.get("涨跌幅"))
        if not change and current and prev_close:
            change = current - prev_close
        if not change_percent and change and prev_close:
            change_percent = change / prev_close * 100
        amount = _safe_float(row.get("成交额"))
        rows.append({
            "code": formatted_code,
            "name": str(row.get("名称") or ""),
            "current_price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "open_price": round(_safe_float(row.get("今开")), 2),
            "high": round(_safe_float(row.get("最高")), 2),
            "low": round(_safe_float(row.get("最低")), 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "volume": amount,
            "volume_display": format_volume(amount),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    if not rows:
        raise RuntimeError("AkShare stock_zh_a_spot_em 响应为空")
    return rows


def _fetch_akshare_spot_rows() -> list[dict]:
    """获取AkShare实时行情，短暂缓存避免批量报价时重复拉全量列表。"""
    global _akshare_spot_cache
    now = time.time()
    if _akshare_spot_cache and now - _akshare_spot_cache[0] < _AKSHARE_SPOT_CACHE_TTL:
        return _akshare_spot_cache[1]

    with _akshare_spot_lock:
        now = time.time()
        if _akshare_spot_cache and now - _akshare_spot_cache[0] < _AKSHARE_SPOT_CACHE_TTL:
            return _akshare_spot_cache[1]

        errors: list[str] = []
        for label, fetcher in (
            ("AkShare stock_zh_a_spot", _spot_rows_from_sina),
            ("AkShare stock_zh_a_spot_em", _spot_rows_from_eastmoney),
        ):
            try:
                rows = fetcher()
                _akshare_spot_cache = (time.time(), rows)
                return rows
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                logger.warning("%s 获取实时行情失败: %s", label, exc)

    raise RuntimeError(f"AkShare实时行情接口均获取失败，请检查接口。{' | '.join(errors)}")


def fetch_quote_akshare_sync(code: str, task_id: str | None = None) -> StockQuote | None:
    """使用AkShare实时行情接口获取指定股票现价，作为雪球失败后的接口兜底。"""
    formatted_code = format_stock_code(extract_numeric_code(code))
    try:
        rows = _fetch_akshare_spot_rows()
        for row in rows:
            if row.get("code") == formatted_code:
                quote = StockQuote(**row)
                cached_quotes = _read_json_cache(_quote_cache_path(task_id), {})
                cached_quotes[formatted_code] = quote.model_dump()
                _write_json_cache(_quote_cache_path(task_id), cached_quotes)
                return quote
    except Exception as exc:
        logger.warning("AkShare实时行情获取失败，使用AkShare历史日线兜底 [%s]: %s", formatted_code, exc)

    return _fetch_quote_from_akshare_daily_sync(formatted_code, task_id=task_id)


def _fetch_quote_from_akshare_daily_sync(code: str, task_id: str | None = None) -> StockQuote | None:
    """使用AkShare历史日线最近两根K线生成非实时行情兜底。"""
    formatted_code = format_stock_code(extract_numeric_code(code))
    errors: list[str] = []
    df = None
    for label, fetcher in (
        ("AkShare stock_zh_a_hist_tx", _fetch_daily_kline_df_akshare_tx),
        ("AkShare stock_zh_a_daily", _fetch_daily_kline_df_akshare_sina),
    ):
        try:
            df = fetcher(formatted_code)
            if df is not None and not getattr(df, "empty", True):
                break
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            logger.warning("%s 获取历史行情失败 [%s]: %s", label, formatted_code, exc)
            df = None

    if df is None or getattr(df, "empty", True):
        raise RuntimeError(f"AkShare历史日线接口均获取失败，请检查接口。{' | '.join(errors)}")

    rows = df.tail(2)
    latest = rows.iloc[-1]
    prev = rows.iloc[-2] if len(rows) >= 2 else latest
    current = _safe_float(latest.get("close", latest.get("收盘")))
    prev_close = _safe_float(prev.get("close", prev.get("收盘"))) or current
    change = current - prev_close
    change_percent = change / prev_close * 100 if prev_close else 0.0
    volume = _safe_float(latest.get("amount", latest.get("成交额", latest.get("volume", latest.get("成交量")))))
    cached_stock_list = _read_json_cache(_stock_list_cache_path(), [])
    stock_map = {
        item.get("code"): item.get("name", "")
        for item in cached_stock_list
        if isinstance(item, dict) and item.get("code")
    }
    quote = StockQuote(
        code=formatted_code,
        name=stock_map.get(formatted_code, ""),
        current_price=round(current, 2),
        prev_close=round(prev_close, 2),
        open_price=round(_safe_float(latest.get("open", latest.get("开盘"))), 2),
        high=round(_safe_float(latest.get("high", latest.get("最高"))), 2),
        low=round(_safe_float(latest.get("low", latest.get("最低"))), 2),
        change=round(change, 2),
        change_percent=round(change_percent, 2),
        volume=volume,
        volume_display=format_volume(volume),
        timestamp=str(latest.get("date", latest.get("日期", datetime.now().strftime("%Y-%m-%d")))),
    )
    cached_quotes = _read_json_cache(_quote_cache_path(task_id), {})
    cached_quotes[formatted_code] = quote.model_dump()
    _write_json_cache(_quote_cache_path(task_id), cached_quotes)
    return quote


def fetch_shareholders_xq_sync(code: str, count: int = 20) -> list[dict]:
    """获取雪球F10股东人数变化。"""
    symbol = _to_xq_symbol(code)
    payload = _fetch_xq_json_sync(symbol, _XQ_HOLDERS_URL, {"symbol": symbol, "count": count})
    return payload.get("data", {}).get("items") or []


def fetch_finance_indicator_xq_sync(code: str, report_type: str = "Q4", count: int = 5) -> list[dict]:
    """获取雪球财务主要指标，report_type=Q4为年报，all为全部报告期。"""
    symbol = _to_xq_symbol(code)
    payload = _fetch_xq_json_sync(
        symbol,
        _XQ_FINANCE_INDICATOR_URL,
        {
            "symbol": symbol,
            "type": report_type,
            "is_detail": "true",
            "count": count,
        },
    )
    return payload.get("data", {}).get("list") or []


def fetch_stock_events_xq_sync(code: str, size: int = 200) -> list[dict]:
    """获取雪球公司大事提醒。"""
    symbol = _to_xq_symbol(code)
    payload = _fetch_xq_json_sync(
        symbol,
        _XQ_EVENT_URL,
        {
            "symbol": symbol,
            "page": 1,
            "size": size,
        },
    )
    return payload.get("data", {}).get("items") or []


def fetch_quote_xq_sync(code: str, task_id: str | None = None) -> StockQuote | None:
    """
    使用雪球个股行情接口获取指定股票实时行情，失败后使用AkShare实时行情兜底。
    """
    formatted_code = format_stock_code(extract_numeric_code(code))
    try:
        quote_data = _fetch_xq_quote(_to_xq_symbol(formatted_code))
    except Exception as exc:
        logger.warning("雪球实时行情请求失败，使用AkShare兜底 [%s]: %s", formatted_code, exc)
        return fetch_quote_akshare_sync(formatted_code, task_id=task_id)
    if not quote_data:
        logger.warning("雪球实时行情为空，使用AkShare兜底 [%s]", formatted_code)
        return fetch_quote_akshare_sync(formatted_code, task_id=task_id)

    current = _safe_float(quote_data.get("current"))
    prev_close = _safe_float(quote_data.get("last_close"))
    change = _safe_float(quote_data.get("chg"))
    change_percent = _safe_float(quote_data.get("percent"))
    amount = _safe_float(quote_data.get("amount"))
    pure_code = extract_numeric_code(str(quote_data.get("symbol") or quote_data.get("code") or formatted_code))
    formatted_code = format_stock_code(pure_code)

    if not current:
        logger.warning("雪球实时行情缺少现价 [%s]: %s", formatted_code, quote_data)
        return fetch_quote_akshare_sync(formatted_code, task_id=task_id)

    if not change and current and prev_close:
        change = current - prev_close
    if not change_percent and change and prev_close:
        change_percent = change / prev_close * 100

    quote = StockQuote(
        code=formatted_code,
        name=str(quote_data.get("name") or ""),
        current_price=round(current, 2),
        prev_close=round(prev_close, 2),
        open_price=round(_safe_float(quote_data.get("open")), 2),
        high=round(_safe_float(quote_data.get("high")), 2),
        low=round(_safe_float(quote_data.get("low")), 2),
        change=round(change, 2),
        change_percent=round(change_percent, 2),
        volume=amount,
        volume_display=format_volume(amount),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    if not quote.name:
        cached_info = _read_json_cache(_company_cache_path(task_id), {})
        quote.name = _company_name_from_info(cached_info.get(formatted_code) or cached_info.get(pure_code) or {})

    cached_quotes = _read_json_cache(_quote_cache_path(task_id), {})
    cached_quotes[formatted_code] = quote.model_dump()
    _write_json_cache(_quote_cache_path(task_id), cached_quotes)
    return quote


def fetch_quotes_sync(codes: list[str], task_id: str | None = None) -> list[StockQuote]:
    """
    按传入股票代码逐只获取雪球实时行情。
    """
    quotes: list[StockQuote] = []
    for code in codes:
        quote = fetch_quote_xq_sync(code, task_id=task_id)
        if quote:
            quotes.append(quote)
    return quotes

def fetch_recent_daily_kline_xq_sync(code: str, count: int = _MONTH_TRADING_DAYS) -> list[KLinePoint]:
    """使用雪球原生日K接口获取最近交易日K线。"""
    symbol = _to_xq_symbol(code)
    payload = _fetch_xq_json_sync(
        symbol,
        _XQ_KLINE_URL,
        {
            "symbol": symbol,
            "begin": int(time.time() * 1000),
            "period": "day",
            "type": "before",
            "count": -abs(int(count)),
            "indicator": "kline",
        },
    )
    data = payload.get("data") or {}
    columns = data.get("column") or []
    items = data.get("item") or []
    if not columns or not items:
        raise RuntimeError(f"雪球K线响应为空: {str(payload)[:300]}")

    points: list[KLinePoint] = []
    for item in items:
        row = dict(zip(columns, item))
        timestamp = int(row["timestamp"])
        points.append(KLinePoint(
            date=datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d"),
            open=_safe_float(row.get("open")),
            high=_safe_float(row.get("high")),
            low=_safe_float(row.get("low")),
            close=_safe_float(row.get("close")),
            volume=_safe_float(row.get("volume")),
        ))
    return points


def fetch_recent_daily_kline_sync(code: str, task_id: str | None = None) -> list[KLinePoint]:
    """
    优先使用雪球获取近一个月日K，失败时使用AkShare腾讯日线兜底。
    固定返回最近22个交易日的日线数据。
    """
    import akshare as ak

    num = extract_numeric_code(code)
    formatted_code = format_stock_code(num)
    try:
        points = fetch_recent_daily_kline_xq_sync(formatted_code, _MONTH_TRADING_DAYS)
        cached_klines = _read_json_cache(_kline_cache_path(task_id), {})
        cached_klines[formatted_code] = [point.model_dump() for point in points]
        _write_json_cache(_kline_cache_path(task_id), cached_klines)
        return points
    except Exception as exc:
        logger.warning("雪球日K获取失败，使用AkShare兜底 [%s]: %s", formatted_code, exc)

    try:
        df = _run_without_proxy(
            lambda: _run_quietly(lambda: ak.stock_zh_a_hist_tx(symbol=_to_tx_symbol(num), adjust="qfq"))
        )
    except Exception:
        cached_klines = _read_json_cache(_kline_cache_path(task_id), {})
        return [KLinePoint(**item) for item in cached_klines.get(formatted_code, [])]

    df = df.tail(_MONTH_TRADING_DAYS)

    points: list[KLinePoint] = []
    for _, row in df.iterrows():
        points.append(KLinePoint(
            date=str(row.get("date", row.get("日期", ""))),
            open=_safe_float(row.get("open", row.get("开盘"))),
            high=_safe_float(row.get("high", row.get("最高"))),
            low=_safe_float(row.get("low", row.get("最低"))),
            close=_safe_float(row.get("close", row.get("收盘"))),
            volume=_safe_float(row.get("amount", row.get("成交量"))),
        ))
    cached_klines = _read_json_cache(_kline_cache_path(task_id), {})
    cached_klines[formatted_code] = [point.model_dump() for point in points]
    _write_json_cache(_kline_cache_path(task_id), cached_klines)
    return points


def fetch_company_info_sync(pure_code: str, task_id: str | None = None) -> dict:
    """
    使用akshare获取上市公司基础信息
    返回普通dict，字段名保持中文，便于LLM理解工具结果。
    """
    import akshare as ak

    num = extract_numeric_code(pure_code)
    try:
        df = _run_without_proxy(lambda: _run_quietly(lambda: ak.stock_individual_info_em(symbol=num)))
    except Exception:
        cached_companies = _read_json_cache(_company_cache_path(task_id), {})
        cached = cached_companies.get(format_stock_code(num)) or cached_companies.get(num)
        if cached:
            return cached
        stock_map = {item["code"]: item["name"] for item in get_stock_list(task_id=task_id)}
        return {
            "数据源": "akshare-cache-fallback",
            "股票代码": num,
            "股票简称": stock_map.get(format_stock_code(num), ""),
        }

    info = {"数据源": "akshare", "股票代码": num}

    for _, row in df.iterrows():
        key = str(row.get("item", ""))
        value = str(row.get("value", ""))
        if key:
            info[key] = value

    if "股票简称" not in info:
        stock_map = {item["code"]: item["name"] for item in get_stock_list(task_id=task_id)}
        info["股票简称"] = stock_map.get(format_stock_code(num), "")

    company_cache = _company_cache_path(task_id)
    cached_companies = _read_json_cache(company_cache, {})
    cached_companies[format_stock_code(num)] = info
    cached_companies[num] = info
    _write_json_cache(company_cache, cached_companies)
    return info
