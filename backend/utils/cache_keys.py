"""缓存作用域、文件名和 key 命名规则。"""
import hashlib
import re
from pathlib import Path

SHARED_SCOPE = "_shared"
STOCK_LIST_FILENAME = "stock_list.json"
AKSHARE_QUOTES_FILENAME = "akshare_quotes_cache.json"
AKSHARE_KLINE_FILENAME = "akshare_kline_cache.json"
AKSHARE_COMPANY_FILENAME = "akshare_company_cache.json"
AKSHARE_COMPANY_BUSINESS_FILENAME = "akshare_company_business_cache.json"
WEB_SEARCH_FILENAME_PREFIX = "web_search"


def cache_scope(task_id: str | None) -> str:
    """返回进程内缓存作用域，缺省使用共享作用域。"""
    return task_id or SHARED_SCOPE


def safe_task_scope(task_id: str | None) -> str:
    """清理任务 ID，确保文件缓存目录不会越界。"""
    if not task_id:
        return SHARED_SCOPE
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())
    return cleaned[:80] or SHARED_SCOPE


def optional_safe_task_scope(task_id: str | None) -> str | None:
    """清理可选任务 ID，无任务时返回 None。"""
    if not task_id:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())[:80]
    return cleaned or None


def quote_cache_key(codes: list[str], task_id: str | None = None) -> str:
    """生成批量实时行情进程内缓存 key。"""
    return f"{cache_scope(task_id)}|{','.join(sorted(codes))}"


def kline_cache_key(code: str, task_id: str | None = None) -> str:
    """生成固定近一个月日 K 进程内缓存 key。"""
    return f"{cache_scope(task_id)}|{code}|daily|month"


def close_history_cache_key(code: str, count: int) -> str:
    """生成历史收盘价进程内缓存 key。"""
    return f"{code}|day|close|{count}"


def task_cache_dir(root: Path, task_id: str | None) -> Path:
    """生成任务级文件缓存目录。"""
    return root / safe_task_scope(task_id)


def task_data_cache_path(root: Path, task_id: str | None, filename: str) -> Path | None:
    """生成任务级文件缓存路径；无任务 ID 时不落盘。"""
    if not task_id:
        return None
    return task_cache_dir(root, task_id) / filename


def stock_list_cache_path(root: Path) -> Path:
    """生成共享股票列表缓存路径。"""
    return task_cache_dir(root, SHARED_SCOPE) / STOCK_LIST_FILENAME


def web_search_cache_filename(cache_key: str) -> str:
    """生成网页搜索缓存文件名。"""
    query_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
    return f"{WEB_SEARCH_FILENAME_PREFIX}_{query_hash}.json"
