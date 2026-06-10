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


class AnalysisTaskRunner:
    """集中管理分析任务队列、活动任务和串行 worker。"""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] | None = None
        self.queued_ids: set[str] = set()
        self.worker_task: asyncio.Task | None = None
        self.active_task_id: str | None = None
        self.state_lock = asyncio.Lock()
        self.watchers: dict[str, set[asyncio.Queue[None]]] = {}

    def get_queue(self) -> asyncio.Queue[str]:
        if self.queue is None:
            self.queue = asyncio.Queue()
        return self.queue

    async def ensure_started(self) -> None:
        if self.worker_task and not self.worker_task.done():
            return
        self.worker_task = asyncio.create_task(self.worker_loop(), name="analysis-task-worker")

    async def enqueue(self, task_id: str) -> None:
        await self.ensure_started()
        async with self.state_lock:
            if task_id == self.active_task_id or task_id in self.queued_ids:
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
            self.queued_ids.add(task_id)
            self.get_queue().put_nowait(task_id)
        await self.notify(task_id)

    async def enqueue_pending(self) -> None:
        await self.ensure_started()
        for task in reversed(list_tasks()):
            if task.status == AnalysisTaskStatus.PENDING:
                await self.enqueue(task.id)

    async def subscribe(self, task_id: str) -> asyncio.Queue[None]:
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        async with self.state_lock:
            self.watchers.setdefault(task_id, set()).add(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue[None]) -> None:
        async with self.state_lock:
            watchers = self.watchers.get(task_id)
            if not watchers:
                return
            watchers.discard(queue)
            if not watchers:
                self.watchers.pop(task_id, None)

    async def notify(self, task_id: str) -> None:
        async with self.state_lock:
            watchers = list(self.watchers.get(task_id, set()))
        for queue in watchers:
            if queue.full():
                continue
            queue.put_nowait(None)

    async def worker_loop(self) -> None:
        queue = self.get_queue()
        while True:
            task_id = await queue.get()
            async with self.state_lock:
                self.queued_ids.discard(task_id)
                self.active_task_id = task_id
            try:
                await _run_task(task_id)
            finally:
                async with self.state_lock:
                    if self.active_task_id == task_id:
                        self.active_task_id = None
                queue.task_done()


_runner = AnalysisTaskRunner()


def active_task_id() -> str | None:
    return _runner.active_task_id


async def ensure_runner_started() -> None:
    """确保单 worker 已启动。"""
    await _runner.ensure_started()


async def enqueue_task(task_id: str) -> None:
    """把任务加入串行执行队列；重复入队会被忽略。"""
    await _runner.enqueue(task_id)


async def enqueue_pending_tasks() -> None:
    """服务启动时恢复等待中的任务队列。"""
    await _runner.enqueue_pending()


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
            await _runner.notify(task.id)

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


async def watch_task_events(task_id: str, start_seq: int = 0):
    """输出任务 SSE 事件；先补文件历史事件，再订阅运行时新事件。"""
    last_seq = start_seq
    yielded_done = False
    queue = await _runner.subscribe(task_id)
    try:
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
                payload = dict(event.data)
                payload["seq"] = event.seq
                yield {
                    "event": event.type,
                    "data": json.dumps(payload, ensure_ascii=False),
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

            await queue.get()
    finally:
        await _runner.unsubscribe(task_id, queue)
