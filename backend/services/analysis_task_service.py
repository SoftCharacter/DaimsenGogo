"""
分析任务持久化服务
使用data/analysis_tasks目录保存每个任务的JSON文件。
"""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.models.analysis_task_models import (
    AnalysisCheckpoint,
    AnalysisTask,
    AnalysisTaskEvent,
    AnalysisTaskStatus,
    AnalysisTaskSummary,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
TASKS_DIR = DATA_DIR / "analysis_tasks"
TASK_CACHE_DIR = DATA_DIR / "task_cache"
_SAFE_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def ensure_dirs() -> None:
    """确保分析任务目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def _task_path(task_id: str) -> Path:
    """校验任务ID并返回限定在任务目录内的JSON路径。"""
    if not _SAFE_TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("任务ID格式不合法")
    path = (TASKS_DIR / f"{task_id}.json").resolve()
    base = TASKS_DIR.resolve()
    if path.parent != base:
        raise ValueError("任务路径越界")
    return path


def _task_cache_path(task_id: str) -> Path:
    """校验任务ID并返回限定在任务缓存目录内的路径。"""
    if not _SAFE_TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("任务ID格式不合法")
    path = (TASK_CACHE_DIR / task_id).resolve()
    base = TASK_CACHE_DIR.resolve()
    if path.parent != base:
        raise ValueError("任务缓存路径越界")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_task_raw(task_id: str) -> Optional[str]:
    path = _task_path(task_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def load_task(task_id: str) -> Optional[AnalysisTask]:
    """读取单个任务。"""
    raw = _read_task_raw(task_id)
    if raw is None:
        return None
    return AnalysisTask.model_validate_json(raw)


def save_task(task: AnalysisTask) -> AnalysisTask:
    """保存任务到JSON文件。"""
    ensure_dirs()
    task.updated_at = _now()
    _task_path(task.id).write_text(
        task.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return task


def create_task(query: str, task_id: str) -> AnalysisTask:
    """创建新任务。"""
    now = _now()
    task = AnalysisTask(
        id=task_id,
        query=query,
        status=AnalysisTaskStatus.PENDING,
        created_at=now,
        updated_at=now,
        started_at="",
        finished_at="",
        current_step=0,
        max_steps=15,
        events=[],
        result=None,
        error="",
        saved_theme_id="",
        checkpoint=AnalysisCheckpoint(updated_at=now),
    )
    return save_task(task)


def list_tasks() -> list[AnalysisTaskSummary]:
    """列出所有任务摘要。"""
    ensure_dirs()
    summaries: list[AnalysisTaskSummary] = []
    for path in TASKS_DIR.glob("*.json"):
        try:
            task = AnalysisTask.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summaries.append(
            AnalysisTaskSummary(
                id=task.id,
                query=task.query,
                status=task.status,
                current_step=task.current_step,
                max_steps=task.max_steps,
                updated_at=task.updated_at,
                created_at=task.created_at,
                result_name=task.result.name if task.result else "",
                error=task.error,
                saved_theme_id=task.saved_theme_id,
            )
        )
    summaries.sort(key=lambda item: item.updated_at, reverse=True)
    return summaries


def delete_task(task_id: str) -> bool:
    """删除任务文件并清理对应任务缓存目录。"""
    path = _task_path(task_id)
    if not path.exists():
        return False
    path.unlink()
    cache_path = _task_cache_path(task_id)
    if cache_path.exists():
        shutil.rmtree(cache_path)
    return True


def append_task_event(task: AnalysisTask, event_type: str, data: dict, seq: int) -> AnalysisTask:
    """追加任务事件。"""
    event = AnalysisTaskEvent(seq=seq, type=event_type, data=data, created_at=_now())
    task.events.append(event)
    task.updated_at = _now()
    return save_task(task)


def update_task_checkpoint(task: AnalysisTask, checkpoint: AnalysisCheckpoint) -> AnalysisTask:
    """更新任务断点。"""
    task.checkpoint = checkpoint
    task.updated_at = _now()
    return save_task(task)


def mark_task_running(task: AnalysisTask) -> AnalysisTask:
    """标记任务运行中。"""
    now = _now()
    task.status = AnalysisTaskStatus.RUNNING
    if not task.started_at:
        task.started_at = now
    task.updated_at = now
    return save_task(task)


def mark_task_paused(task: AnalysisTask, error: str = "") -> AnalysisTask:
    """标记任务暂停。"""
    task.status = AnalysisTaskStatus.PAUSED
    task.error = error
    task.updated_at = _now()
    return save_task(task)


def mark_task_failed(task: AnalysisTask, error: str) -> AnalysisTask:
    """标记任务失败。"""
    now = _now()
    task.status = AnalysisTaskStatus.FAILED
    task.error = error
    task.finished_at = now
    task.updated_at = now
    return save_task(task)


def mark_task_completed(task: AnalysisTask) -> AnalysisTask:
    """标记任务完成。"""
    now = _now()
    task.status = AnalysisTaskStatus.COMPLETED
    task.finished_at = now
    task.updated_at = now
    return save_task(task)


def set_task_saved_theme(task_id: str, theme_id: str) -> AnalysisTask | None:
    """记录分析任务保存出的主题ID。"""
    task = load_task(task_id)
    if not task:
        return None
    task.saved_theme_id = theme_id
    return save_task(task)


def reconcile_running_tasks() -> int:
    """启动时复位残留的 running 任务。

    进程重启后不会有真正在执行的任务，任何仍标记为 running 的都是上次
    异常退出/连接中断遗留的孤儿，统一复位为 paused，断点保留以便继续执行，
    避免前端因状态卡在 running 而无法「继续/删除」。返回复位的任务数量。
    """
    ensure_dirs()
    count = 0
    for path in TASKS_DIR.glob("*.json"):
        try:
            task = AnalysisTask.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if task.status == AnalysisTaskStatus.RUNNING:
            mark_task_paused(task, "服务重启时检测到中断的任务，已暂停，可点击「继续」从断点恢复")
            count += 1
    return count


def mark_task_cancelled(task: AnalysisTask, error: str = "") -> AnalysisTask:
    """标记任务取消。"""
    now = _now()
    task.status = AnalysisTaskStatus.CANCELLED
    task.error = error
    task.finished_at = now
    task.updated_at = now
    return save_task(task)
