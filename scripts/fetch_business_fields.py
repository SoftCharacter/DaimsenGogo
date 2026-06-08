#!/usr/bin/env python3
"""
Fetch business-field samples for DG analysis data-source evaluation.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "business_field_samples"

STOCKS = [
    {"name": "贵研铂业", "code": "600459", "xq_symbol": "SH600459", "em_symbol": "SH600459"},
    {"name": "宝钛股份", "code": "600456", "xq_symbol": "SH600456", "em_symbol": "SH600456"},
    {"name": "京东方A", "code": "000725", "xq_symbol": "SZ000725", "em_symbol": "SZ000725"},
    {"name": "德赛电池", "code": "000049", "xq_symbol": "SZ000049", "em_symbol": "SZ000049"},
    {"name": "征和工业", "code": "003033", "xq_symbol": "SZ003033", "em_symbol": "SZ003033"},
    {"name": "今飞凯达", "code": "002863", "xq_symbol": "SZ002863", "em_symbol": "SZ002863"},
]

XUEQIU_COMPANY_URL = "https://stock.xueqiu.com/v5/stock/f10/cn/company.json"
EASTMONEY_COMPANY_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax"
EASTMONEY_BUSINESS_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax"


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def rows_from_df(df) -> list[dict[str, Any]]:
    return clean_json(df.where(df.notna(), None).to_dict(orient="records"))


def request_json(session: requests.Session, url: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        response = session.get(url, params=params, timeout=15)
        try:
            payload = response.json()
        except Exception:
            payload = {"raw_text": response.text[:1000]}
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "url": response.url,
            "payload": clean_json(payload),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "params": params,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_xueqiu() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://xueqiu.com/",
    })
    try:
        session.get("https://xueqiu.com/", timeout=10)
    except Exception:
        pass

    records = []
    for stock in STOCKS:
        result = request_json(session, XUEQIU_COMPANY_URL, {"symbol": stock["xq_symbol"]})
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        data = payload.get("data") if isinstance(payload, dict) else None
        records.append({
            **stock,
            "endpoint": XUEQIU_COMPANY_URL,
            "business_fields": data if isinstance(data, dict) else {},
            "response": result,
        })
        time.sleep(0.2)
    return {
        "source": "xueqiu",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }


def fetch_eastmoney() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://emweb.securities.eastmoney.com/",
    })
    records = []
    for stock in STOCKS:
        company = request_json(session, EASTMONEY_COMPANY_URL, {"code": stock["em_symbol"]})
        business = request_json(session, EASTMONEY_BUSINESS_URL, {"code": stock["em_symbol"]})
        company_payload = company.get("payload") if isinstance(company.get("payload"), dict) else {}
        business_payload = business.get("payload") if isinstance(business.get("payload"), dict) else {}
        jbzl = company_payload.get("jbzl") if isinstance(company_payload, dict) else None
        zygcfx = business_payload.get("zygcfx") if isinstance(business_payload, dict) else None
        records.append({
            **stock,
            "endpoints": {
                "company_survey": EASTMONEY_COMPANY_URL,
                "business_analysis": EASTMONEY_BUSINESS_URL,
            },
            "business_fields": {
                "company_survey": jbzl if isinstance(jbzl, list) else [],
                "business_analysis": zygcfx if isinstance(zygcfx, list) else [],
            },
            "responses": {
                "company_survey": company,
                "business_analysis": business,
            },
        })
        time.sleep(0.2)
    return {
        "source": "eastmoney",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }


def akshare_call(fn_name: str, **kwargs) -> dict[str, Any]:
    try:
        import akshare as ak

        df = getattr(ak, fn_name)(**kwargs)
        return {
            "ok": True,
            "function": fn_name,
            "params": kwargs,
            "rows": rows_from_df(df),
        }
    except Exception as exc:
        return {
            "ok": False,
            "function": fn_name,
            "params": kwargs,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_akshare() -> dict[str, Any]:
    records = []
    for stock in STOCKS:
        calls = {
            "stock_zyjs_ths": akshare_call("stock_zyjs_ths", symbol=stock["code"]),
            "stock_profile_cninfo": akshare_call("stock_profile_cninfo", symbol=stock["code"]),
            "stock_zygc_em": akshare_call("stock_zygc_em", symbol=stock["em_symbol"]),
            "stock_individual_basic_info_xq": akshare_call("stock_individual_basic_info_xq", symbol=stock["xq_symbol"]),
        }
        records.append({
            **stock,
            "business_fields": calls,
        })
        time.sleep(0.2)
    return {
        "source": "akshare",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }


def write_payload(filename: str, payload: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / filename).write_text(
        json.dumps(clean_json(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    write_payload("xueqiu_business_fields.json", fetch_xueqiu())
    write_payload("eastmoney_business_fields.json", fetch_eastmoney())
    write_payload("akshare_business_fields.json", fetch_akshare())
    print(f"wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
