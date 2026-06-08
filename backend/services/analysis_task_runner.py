"""
分析任务串行执行器。

前端 SSE 连接只负责观察事件；真实执行由后端单 worker 串行消费队列，
避免刷新页面或发起新任务时中断当前 SOP。
"""
import asyncio
import json
import logging
from typing import Any

from backend.agent.hybrid_loop import plan_execute_react_loop
from backend.models.analysis_task_models import AnalysisCheckpoint, AnalysisTaskStatus
from backend.models.theme_models import Theme
from backend.services.analysis_task_service import (
    append_task_event,
    list_tasks,
    load_task,
    mark_task_completed,
    mark_task_failed,
    mark_task_paused,
    mark_task_pending,
    mark_task_running,
    update_task_checkpoint,
)
from backend.services.file_service import load_config

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[str] | None = None
_queued_ids: set[str] = set()
_worker_task: asyncio.Task | None = None
_active_task_id: str | None = None
_state_lock = asyncio.Lock()


def _get_queue() -> asyncio.Queue[str]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def active_task_id() -> str | None:
    return _active_task_id


async def ensure_runner_started() -> None:
    """确保单 worker 已启动。"""
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop(), name="analysis-task-worker")


async def enqueue_task(task_id: str) -> None:
    """把任务加入串行执行队列；重复入队会被忽略。"""
    await ensure_runner_started()
    async with _state_lock:
        if task_id == _active_task_id or task_id in _queued_ids:
            return
        task = load_task(task_id)
        if not task:
            return
        if task.status in {
            AnalysisTaskStatus.COMPLETED,
            AnalysisTaskStatus.CANCELLED,
            AnalysisTaskStatus.RUNNING,
        }:
            return
        mark_task_pending(task)
        _queued_ids.add(task_id)
        _get_queue().put_nowait(task_id)


async def enqueue_pending_tasks() -> None:
    """服务启动时恢复等待中的任务队列。"""
    await ensure_runner_started()
    for task in reversed(list_tasks()):
        if task.status == AnalysisTaskStatus.PENDING:
            await enqueue_task(task.id)


async def _save_checkpoint(task_id: str, payload: dict[str, Any]) -> None:
    current = load_task(task_id)
    if not current:
        return
    current.checkpoint = AnalysisCheckpoint.model_validate(payload)
    current.current_step = current.checkpoint.step
    current.max_steps = current.checkpoint.max_steps
    update_task_checkpoint(current, current.checkpoint)


def _pause_requested(task_id: str) -> bool:
    task = load_task(task_id)
    return bool(task and task.pause_requested)


async def _run_task(task_id: str) -> None:
    task = load_task(task_id)
    if not task:
        return

    config = load_config()
    if not config.provider.api_key:
        mark_task_failed(task, "请先在配置页面设置API密钥")
        return
    if not config.selected_model:
        mark_task_failed(task, "请先在配置页面选择一个AI模型")
        return
    if not config.provider.base_url:
        mark_task_failed(task, "请先在配置页面设置API地址")
        return
    if not config.web_search.enabled or not config.web_search.tavily_api_key:
        mark_task_failed(task, "DG 分析必须先配置并启用 web_search 的 Tavily API Key")
        return

    checkpoint = task.checkpoint
    mark_task_running(task)

    try:
        async for event in plan_execute_react_loop(
            task.query,
            config,
            checkpoint=checkpoint,
            task_id=task.id,
            save_checkpoint=lambda payload: _save_checkpoint(task.id, payload),
            should_pause=lambda: _pause_requested(task.id),
        ):
            event_type = event.get("event", "message")
            event_data = event.get("data", {})
            current = load_task(task.id)
            if not current:
                return
            append_task_event(current, event_type, event_data, len(current.events) + 1)

            if event_type == "result":
                loaded = load_task(task.id)
                if loaded:
                    try:
                        loaded.result = Theme.model_validate(event_data.get("theme", {}))
                    except Exception:
                        loaded.result = None
                    from backend.services.analysis_task_service import save_task

                    save_task(loaded)

            if event_type == "error":
                loaded = load_task(task.id)
                if loaded:
                    mark_task_failed(loaded, str(event_data.get("message", "")))

            if event_type == "paused":
                loaded = load_task(task.id)
                if loaded:
                    mark_task_paused(loaded, str(event_data.get("message", "")))

            if event_type == "done":
                loaded = load_task(task.id)
                if loaded and loaded.status == AnalysisTaskStatus.RUNNING:
                    if loaded.result is not None:
                        mark_task_completed(loaded)
                    elif loaded.error:
                        mark_task_failed(loaded, loaded.error)
                    else:
                        mark_task_paused(loaded)
    except Exception as exc:
        logger.error("分析任务执行异常 [%s]: %s", task_id, exc, exc_info=True)
        loaded = load_task(task_id)
        if loaded:
            mark_task_failed(loaded, f"分析过程发生异常: {exc}")


async def _worker_loop() -> None:
    global _active_task_id
    queue = _get_queue()
    while True:
        task_id = await queue.get()
        async with _state_lock:
            _queued_ids.discard(task_id)
            _active_task_id = task_id
        try:
            await _run_task(task_id)
        finally:
            async with _state_lock:
                if _active_task_id == task_id:
                    _active_task_id = None
            queue.task_done()


async def watch_task_events(task_id: str, start_seq: int = 0):
    """轮询任务事件并输出 SSE，用于观察已入队/运行中的任务。"""
    last_seq = start_seq
    yielded_done = False
    yield {
        "event": "queued",
        "data": json.dumps({"task_id": task_id}, ensure_ascii=False),
    }
    while True:
        task = load_task(task_id)
        if not task:
            yield {
                "event": "error",
                "data": json.dumps({"message": "分析任务不存在", "task_id": task_id}, ensure_ascii=False),
            }
            yield {"event": "done", "data": json.dumps({"task_id": task_id}, ensure_ascii=False)}
            return

        for event in task.events:
            if event.seq <= last_seq:
                continue
            last_seq = event.seq
            yielded_done = yielded_done or event.type == "done"
            yield {
                "event": event.type,
                "data": json.dumps(event.data, ensure_ascii=False),
            }

        if task.status in {
            AnalysisTaskStatus.COMPLETED,
            AnalysisTaskStatus.FAILED,
            AnalysisTaskStatus.PAUSED,
            AnalysisTaskStatus.CANCELLED,
        }:
            if not yielded_done:
                yield {"event": "done", "data": json.dumps({"task_id": task_id}, ensure_ascii=False)}
            return

        await asyncio.sleep(0.5)
