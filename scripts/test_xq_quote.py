"""
临时测试脚本：验证雪球单股实时行情接口的原始返回。
运行方式：conda run -n env_reactAgent python scripts/test_xq_quote.py
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import akshare as ak
import requests

from backend.services.akshare_adapter import _safe_float, extract_numeric_code, format_stock_code

SYMBOL = "SZ002460"
QUOTE_URL = "https://stock.xueqiu.com/v5/stock/quote.json"


def print_raw_response() -> dict:
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    }
    session.get(f"https://xueqiu.com/S/{SYMBOL}", headers=headers, timeout=10)
    resp = session.get(
        QUOTE_URL,
        params={"symbol": SYMBOL, "extend": "detail"},
        headers=headers,
        timeout=10,
    )
    print("原始 HTTP 状态码:", resp.status_code)
    print("原始响应前 1000 字符:")
    print(resp.text[:1000])
    try:
        return resp.json()
    except ValueError:
        return {}


def parse_item_value(data: dict) -> None:
    quote = data.get("data", {}).get("quote")
    if not quote:
        print("\n响应中没有 data.quote，无法解析行情。")
        return

    print("\n原始 quote 字段:")
    print(json.dumps(quote, ensure_ascii=False, indent=2, default=str))

    parsed = {
        "code": format_stock_code(extract_numeric_code(str(quote.get("symbol") or SYMBOL))),
        "name": str(quote.get("name") or ""),
        "current_price": _safe_float(quote.get("current")),
        "prev_close": _safe_float(quote.get("last_close")),
        "change": _safe_float(quote.get("chg")),
        "change_percent": _safe_float(quote.get("percent")),
        "open_price": _safe_float(quote.get("open")),
        "high": _safe_float(quote.get("high")),
        "low": _safe_float(quote.get("low")),
        "amount": _safe_float(quote.get("amount")),
    }
    print("\n按原始 quote 解析结果:")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


def main() -> None:
    data = print_raw_response()
    parse_item_value(data)

    print("\nAkShare 封装调用结果:")
    try:
        df = ak.stock_individual_spot_xq(symbol=SYMBOL)
        print(df.to_string())
    except Exception as exc:
        print(repr(exc))


if __name__ == "__main__":
    main()
