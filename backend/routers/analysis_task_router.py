"""
分析任务路由
提供历史任务列表、详情、删除、暂停以及继续执行接口。
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.models.analysis_task_models import AnalysisTask, AnalysisTaskStatus
from backend.services.analysis_task_runner import enqueue_task, watch_task_events
from backend.services.analysis_task_service import (
    create_task,
    delete_task,
    load_task,
    list_tasks,
    mark_task_paused,
    request_task_pause,
)
from backend.services.file_service import load_config

logger = logging.getLogger(__name__)
router = APIRouter()
_MAX_QUERY_LENGTH = 120
# 任务超过该时长无更新即视为「停滞」（孤儿）。活跃任务每次 LLM 调用后都会写断点
# 刷新 updated_at（单次调用最多 ~3 分钟），8 分钟阈值不会误判正在执行的任务。
_STALE_RUNNING_SECONDS = 8 * 60


def _is_stale_running(task: AnalysisTask) -> bool:
    """判断一个 running 任务是否已停滞（长时间无更新，疑似孤儿）。"""
    if task.status != AnalysisTaskStatus.RUNNING:
        return False
    try:
        updated = datetime.fromisoformat(task.updated_at)
    except (TypeError, ValueError):
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated).total_seconds() > _STALE_RUNNING_SECONDS


class CreateAnalysisTaskRequest(BaseModel):
    query: str


def _validate_run_config() -> None:
    config = load_config()
    if not config.provider.api_key:
        raise HTTPException(status_code=400, detail="请先在配置页面设置API密钥")
    if not config.selected_model:
        raise HTTPException(status_code=400, detail="请先在配置页面选择一个AI模型")
    if not config.provider.base_url:
        raise HTTPException(status_code=400, detail="请先在配置页面设置API地址")
    if not config.web_search.enabled or not config.web_search.tavily_api_key:
        raise HTTPException(status_code=400, detail="DG 分析必须先配置并启用 web_search 的 Tavily API Key")


@router.get("/")
def get_analysis_tasks():
    return list_tasks()


@router.get("/{task_id}")
def get_analysis_task(task_id: str):
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return task


@router.delete("/{task_id}")
def remove_analysis_task(task_id: str):
    deleted = delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return {"status": "ok"}


@router.get("/{task_id}/events")
async def watch_analysis_task_events(task_id: str, start_seq: int = Query(0, ge=0)):
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return EventSourceResponse(watch_task_events(task_id, start_seq=start_seq))


@router.post("/run")
async def run_analysis_task(body: CreateAnalysisTaskRequest):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="分析查询不能为空")
    if len(query) > _MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail=f"分析查询不能超过{_MAX_QUERY_LENGTH}个字符")

    _validate_run_config()
    task_id = f"analysis_{uuid.uuid4().hex[:12]}"
    task = create_task(query, task_id)
    await enqueue_task(task.id)
    return EventSourceResponse(watch_task_events(task.id, start_seq=0))


@router.post("/{task_id}/continue")
async def continue_analysis_task(task_id: str):
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    if task.status == AnalysisTaskStatus.RUNNING:
        if not _is_stale_running(task):
            raise HTTPException(status_code=409, detail="任务正在执行中")
        # 停滞的孤儿任务：先复位为 paused，再从断点继续（双保险，避免卡死无法恢复）
        mark_task_paused(task, "检测到任务长时间无更新，已暂停后从断点继续")
        task = load_task(task_id) or task
    elif task.status not in {AnalysisTaskStatus.PAUSED, AnalysisTaskStatus.FAILED}:
        raise HTTPException(status_code=400, detail="当前任务状态不支持继续执行")

    _validate_run_config()
    start_seq = len(task.events)
    await enqueue_task(task.id)
    return EventSourceResponse(watch_task_events(task.id, start_seq=start_seq))


@router.post("/{task_id}/pause")
async def pause_analysis_task(task_id: str):
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    if task.status != AnalysisTaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="只有执行中的任务支持暂停")
    request_task_pause(task)
    return {"status": "ok", "message": "已收到暂停请求，将在当前SOP环节完成后暂停"}
