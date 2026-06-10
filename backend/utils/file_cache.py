"""带轻量元信息的 JSON 文件缓存工具。"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """返回 UTC ISO 时间，方便跨环境排查缓存写入时间。"""
    return datetime.now(timezone.utc).isoformat()


def _is_wrapped_cache(data: Any) -> bool:
    """判断缓存是否已经使用元信息包裹格式。"""
    return isinstance(data, dict) and "payload" in data and "created_at" in data


def read_json_cache(path: Path | None, default: Any, *, label: str = "cache") -> Any:
    """读取 JSON 缓存；兼容旧裸 payload 格式。"""
    if path is None:
        logger.debug("缓存跳过 [%s]: 未提供路径", label)
        return default
    try:
        if not path.exists():
            logger.debug("缓存未命中 [%s]: %s", label, path)
            return default
        data = json.loads(path.read_text(encoding="utf-8"))
        if _is_wrapped_cache(data):
            logger.debug(
                "缓存命中 [%s]: %s source=%s ttl=%s created_at=%s",
                label,
                path,
                data.get("source", ""),
                data.get("ttl", ""),
                data.get("created_at", ""),
            )
            return data.get("payload", default)
        logger.debug("缓存命中旧格式 [%s]: %s", label, path)
        return data
    except Exception as exc:
        logger.debug("缓存读取失败 [%s]: %s (%s)", label, path, exc)
        return default


def write_json_cache(path: Path | None, payload: Any, *, source: str, ttl: int | None = None, label: str = "cache") -> None:
    """写入带元信息的 JSON 缓存；失败时不影响主流程。"""
    if path is None:
        logger.debug("缓存写入跳过 [%s]: 未提供路径", label)
        return
    data = {
        "created_at": _now_iso(),
        "source": source,
        "ttl": ttl,
        "payload": payload,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("缓存写入 [%s]: %s source=%s ttl=%s", label, path, source, ttl)
    except Exception as exc:
        logger.debug("缓存写入失败 [%s]: %s (%s)", label, path, exc)
