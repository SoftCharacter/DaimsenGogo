"""
Agent工具集
提供供应链分析所需的三个同步工具函数：
- search_stocks: 按关键词搜索A股股票
- get_company_info: 获取上市公司详情
- verify_stock_code: 批量验证股票代码有效性

所有工具返回JSON字符串，因为akshare是同步库，
在ReAct循环中通过 asyncio.to_thread 异步调用。
"""
import json
import logging
import re
from typing import Any

from backend.agent.company_info import fetch_company_info
from backend.services.akshare_adapter import get_stock_list

# 日志记录器
logger = logging.getLogger(__name__)

# 搜索结果最大返回条数，避免返回过多数据
_MAX_SEARCH_RESULTS = 20


def _is_valid_stock_list(stock_list: Any) -> bool:
    """判断股票列表缓存是否可用于搜索和校验。"""
    return (
        isinstance(stock_list, list)
        and len(stock_list) > 0
        and all(isinstance(item, dict) and item.get("code") and item.get("name") for item in stock_list)
    )


def _tool_error(message: str, **extra) -> str:
    """构造统一的工具错误JSON，便于LLM识别并换策略。"""
    return json.dumps({"error": message, **extra}, ensure_ascii=False)


def _load_stock_list(task_id: str | None = None) -> list[dict]:
    """
    加载A股股票列表缓存
    缓存存在且有效则读取任务目录，否则通过akshare远程获取并缓存到任务目录。
    返回: [{"code": "SZ:002261", "name": "拓维信息"}, ...]
    """
    try:
        stock_list = get_stock_list(task_id=task_id)
    except Exception as e:
        logger.error("获取A股列表失败: %s", e)
        return []
    return stock_list if _is_valid_stock_list(stock_list) else []


def _format_stock_code(raw_code: str) -> str:
    """
    纯数字代码转带交易所前缀格式
    规则: 6开头→SH, 0/3开头→SZ, 4/8开头→BJ
    """
    if raw_code.startswith("6"):
        return f"SH:{raw_code}"
    if raw_code.startswith(("0", "3")):
        return f"SZ:{raw_code}"
    if raw_code.startswith(("4", "8")):
        return f"BJ:{raw_code}"
    return f"SZ:{raw_code}"


def _normalize_stock_code(raw_code: str) -> str:
    """兼容LLM常见股票代码写法，并归一化为交易所前缀格式。"""
    cleaned = raw_code.strip().strip('"').strip("'").strip().upper().replace("：", ":")
    market_match = re.search(r"\b(SH|SZ|BJ)\s*:?\s*(\d{6})\b", cleaned)
    if market_match:
        return f"{market_match.group(1)}:{market_match.group(2)}"

    digit_match = re.search(r"\d{6}", cleaned)
    if digit_match:
        return _format_stock_code(digit_match.group())
    return cleaned


def _split_stock_codes(codes: str) -> list[str]:
    """从逗号、空格、换行或JSON样式文本中提取股票代码片段。"""
    matches = re.findall(r"(?:SH|SZ|BJ)?\s*[:：]?\s*\d{6}", codes, flags=re.IGNORECASE)
    if matches:
        return [item.strip() for item in matches]
    return [item.strip() for item in re.split(r"[,，、;；\s]+", codes) if item.strip()]


def search_stocks(keyword: str, task_id: str | None = None) -> str:
    """
    按关键词搜索A股股票
    在本地缓存中模糊匹配名称和代码，返回JSON字符串，最多20条。
    """
    keyword_lower = keyword.strip().lower()
    if not keyword_lower:
        return _tool_error("搜索关键词不能为空", keyword=keyword, count=0, results=[])

    stock_list = _load_stock_list(task_id=task_id)
    if not _is_valid_stock_list(stock_list):
        return _tool_error(
            "股票列表为空或获取失败，无法搜索",
            fatal=True,
            retryable=False,
            keyword=keyword,
            count=0,
            results=[],
        )

    matched = [
        s for s in stock_list
        if keyword_lower in str(s.get("name", "")).lower()
        or keyword_lower in str(s.get("code", "")).lower()
    ]

    result = matched[:_MAX_SEARCH_RESULTS]
    return json.dumps(
        {"keyword": keyword, "count": len(matched), "results": result},
        ensure_ascii=False,
    )


def get_company_info(code: str, task_id: str | None = None) -> str:
    """
    获取上市公司基本信息（主营业务、行业等）
    自动清理LLM输出的各种非标准格式（带引号、多代码、非标准前缀等）。
    """
    pure_code = code.strip().strip('"').strip("'").strip()
    if "," in pure_code:
        pure_code = pure_code.split(",")[0].strip()
    if ":" in pure_code:
        pure_code = pure_code.split(":")[1]
    digit_match = re.search(r"\d{6}", pure_code)
    if digit_match:
        pure_code = digit_match.group()

    try:
        info = fetch_company_info(pure_code, task_id=task_id)
        return json.dumps(
            {"code": pure_code, "info": info},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.warning("获取公司信息失败 [%s]: %s", pure_code, e)
        return json.dumps(
            {"code": pure_code, "error": f"获取失败: {e}"},
            ensure_ascii=False,
        )


def verify_stock_code(codes: str, task_id: str | None = None) -> str:
    """
    批量验证股票代码是否存在于A股市场
    参数支持逗号、空格、换行分隔，也兼容纯数字代码和无冒号市场前缀。
    """
    stock_list = _load_stock_list(task_id=task_id)
    if not _is_valid_stock_list(stock_list):
        return _tool_error(
            "股票列表为空或获取失败，无法验证代码",
            fatal=True,
            retryable=False,
            total=0,
            results=[],
        )

    code_map = {s["code"]: s["name"] for s in stock_list}
    code_list = _split_stock_codes(codes)
    results = []

    for code_item in code_list:
        normalized = _normalize_stock_code(code_item)
        if normalized in code_map:
            results.append({
                "input": code_item,
                "code": normalized,
                "valid": True,
                "name": code_map[normalized],
            })
        else:
            results.append({
                "input": code_item,
                "code": normalized,
                "valid": False,
                "name": None,
            })

    return json.dumps(
        {"total": len(results), "results": results},
        ensure_ascii=False,
    )
