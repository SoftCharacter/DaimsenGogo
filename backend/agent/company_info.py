"""
公司信息查询工具模块
通过AkShare获取上市公司基础信息，供ReAct Agent工具调用。
"""
import logging
import time

from backend.services.akshare_adapter import fetch_company_info_sync

logger = logging.getLogger(__name__)

# 公司信息查询最多尝试3次，避免Agent工具调用长期阻塞SSE
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5


def fetch_company_info(pure_code: str, task_id: str | None = None) -> dict:
    """
    获取上市公司信息
    使用AkShare同步接口；失败时短暂重试，最终把异常交给外层tools.py序列化。
    """
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fetch_company_info_sync(pure_code, task_id=task_id)
        except Exception as exc:
            last_err = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "akshare公司信息第%d次失败 [%s]: %s, %.1f秒后重试",
                    attempt, pure_code, exc, _RETRY_DELAY,
                )
                time.sleep(_RETRY_DELAY)

    logger.warning("akshare公司信息失败 [%s]: %s", pure_code, last_err)
    raise RuntimeError(f"akshare公司信息获取失败: {last_err}")
