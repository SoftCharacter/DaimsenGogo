"""
分析任务路由
提供历史任务列表、详情、删除以及继续执行接口。
"""
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.agent.hybrid_loop import plan_execute_react_loop
from backend.models.analysis_task_models import AnalysisCheckpoint, AnalysisTask, AnalysisTaskStatus
from backend.services.analysis_task_service import (
    append_task_event,
    create_task,
    delete_task,
    load_task,
    list_tasks,
    mark_task_completed,
    mark_task_failed,
    mark_task_paused,
    mark_task_running,
    save_task,
    update_task_checkpoint,
)
from backend.services.file_service import load_config

logger = logging.getLogger(__name__)
router = APIRouter()
_MAX_QUERY_LENGTH = 120


class CreateAnalysisTaskRequest(BaseModel):
    query: str


async def _run_task_stream(task: AnalysisTask):
    config = load_config()
    checkpoint = task.checkpoint

    async def _save_checkpoint(payload: dict[str, Any]):
        current = load_task(task.id)
        if not current:
            return
        current.checkpoint = AnalysisCheckpoint.model_validate(payload)
        current.current_step = current.checkpoint.step
        current.max_steps = current.checkpoint.max_steps
        update_task_checkpoint(current, current.checkpoint)

    try:
        mark_task_running(task)
        async for event in plan_execute_react_loop(
            task.query,
            config,
            checkpoint=checkpoint,
            task_id=task.id,
            save_checkpoint=_save_checkpoint,
        ):
            event_type = event.get("event", "message")
            event_data = event.get("data", {})
            task = load_task(task.id) or task
            if task:
                append_task_event(task, event_type, event_data, len(task.events) + 1)

            if event_type == "result":
                loaded = load_task(task.id)
                if loaded:
                    loaded.result = loaded.result or None
                    try:
                        from backend.models.theme_models import Theme
                        loaded.result = Theme.model_validate(event_data.get("theme", {}))
                    except Exception:
                        loaded.result = None
                    save_task(loaded)

            if event_type == "error":
                error_message = event_data.get("message", "")
                loaded = load_task(task.id)
                if loaded:
                    mark_task_failed(loaded, error_message)

            if event_type == "done":
                loaded = load_task(task.id)
                if loaded and loaded.status == AnalysisTaskStatus.RUNNING:
                    if loaded.result is not None:
                        mark_task_completed(loaded)
                    elif loaded.error:
                        mark_task_failed(loaded, loaded.error)
                    else:
                        mark_task_paused(loaded)

            yield {
                "event": event_type,
                "data": json.dumps(event_data, ensure_ascii=False),
            }
    except Exception as exc:
        logger.error("分析任务执行异常 [%s]: %s", task.id, exc, exc_info=True)
        loaded = load_task(task.id)
        if loaded:
            mark_task_failed(loaded, f"分析过程发生异常: {exc}")
        yield {"event": "error", "data": json.dumps({"message": f"分析过程发生异常: {exc}"}, ensure_ascii=False)}
        yield {"event": "done", "data": json.dumps({}, ensure_ascii=False)}


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


@router.post("/run")
async def run_analysis_task(body: CreateAnalysisTaskRequest):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="分析查询不能为空")
    if len(query) > _MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail=f"分析查询不能超过{_MAX_QUERY_LENGTH}个字符")

    config = load_config()
    if not config.provider.api_key:
        raise HTTPException(status_code=400, detail="请先在配置页面设置API密钥")
    if not config.selected_model:
        raise HTTPException(status_code=400, detail="请先在配置页面选择一个AI模型")
    if not config.provider.base_url:
        raise HTTPException(status_code=400, detail="请先在配置页面设置API地址")

    task_id = f"analysis_{uuid.uuid4().hex[:12]}"
    task = create_task(query, task_id)
    return EventSourceResponse(_run_task_stream(task))


@router.post("/{task_id}/continue")
async def continue_analysis_task(task_id: str):
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    if task.status == AnalysisTaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="任务正在执行中")
    if task.status not in {AnalysisTaskStatus.PAUSED, AnalysisTaskStatus.FAILED}:
        raise HTTPException(status_code=400, detail="当前任务状态不支持继续执行")
    return EventSourceResponse(_run_task_stream(task))
