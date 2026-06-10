"""
雪球数据源 client。
只负责雪球接口请求、cookie 预热和原始 JSON 响应校验。
"""
import logging

import requests

logger = logging.getLogger(__name__)

XQ_QUOTE_URL = "https://stock.xueqiu.com/v5/stock/quote.json"
XQ_KLINE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
XQ_FINANCE_INDICATOR_URL = "https://stock.xueqiu.com/v5/stock/finance/cn/indicator.json"
XQ_HOLDERS_URL = "https://stock.xueqiu.com/v5/stock/f10/cn/holders.json"
XQ_EVENT_URL = "https://stock.xueqiu.com/v5/stock/screener/event/list.json"
XQ_COMPANY_URL = "https://stock.xueqiu.com/v5/stock/f10/cn/company.json"
XQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
}


def warm_cookie(session: requests.Session, headers: dict[str, str], symbol: str) -> None:
    """通过雪球行情页预热 xq_a_token，失败或缺失时继续原请求流程。"""
    try:
        session.get("https://xueqiu.com/hq", headers=headers, timeout=10)
    except Exception as exc:
        logger.debug("雪球 hq 预热失败，继续原请求流程 [%s]: %s", symbol, exc)
    if not session.cookies.get("xq_a_token"):
        logger.debug("雪球 hq 预热未获取 xq_a_token，继续原请求流程 [%s]", symbol)


def token_cookies(session: requests.Session) -> dict[str, str] | None:
    """仅在已解析到 xq_a_token 时为后续雪球接口显式追加 Cookie。"""
    token = session.cookies.get("xq_a_token")
    return {"xq_a_token": token} if token else None


def fetch_quote(symbol: str) -> dict:
    """请求雪球原始行情接口，返回 data.quote 字段。"""
    session = requests.Session()
    warm_cookie(session, XQ_HEADERS, symbol)
    resp = session.get(
        XQ_QUOTE_URL,
        params={"symbol": symbol, "extend": "detail"},
        headers=XQ_HEADERS,
        cookies=token_cookies(session),
        timeout=10,
    )
    payload = resp.json()
    quote = payload.get("data", {}).get("quote")
    if not quote:
        logger.warning("雪球原始响应缺少data.quote [%s]: %s", symbol, str(payload)[:500])
        return {}
    return quote


def fetch_json(symbol: str, url: str, params: dict, timeout: int = 20) -> dict:
    """请求雪球 JSON 接口，自动预热 cookie 并校验 error_code。"""
    session = requests.Session()
    headers = {**XQ_HEADERS, "Referer": f"https://xueqiu.com/S/{symbol}"}
    warm_cookie(session, headers, symbol)
    resp = session.get(url, params=params, headers=headers, cookies=token_cookies(session), timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("error_code", 0) not in (0, None):
        raise RuntimeError(f"雪球接口返回错误: {str(payload)[:300]}")
    return payload
