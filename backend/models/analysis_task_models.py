"""
分析任务数据模型
定义历史分析任务、事件和断点恢复所需的数据结构。
"""
from typing import Any

from pydantic import BaseModel, Field

from backend.models.theme_models import Theme


class AnalysisTaskStatus:
    """分析任务状态常量。"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisTaskEvent(BaseModel):
    """分析任务的持久化事件。"""

    seq: int
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class AnalysisCheckpoint(BaseModel):
    """可恢复的分析执行快照。"""

    step: int = 0
    max_steps: int = 15
    messages: list[dict[str, Any]] = Field(default_factory=list)
    last_llm_output: str = ""
    last_action: dict[str, Any] | None = None
    last_observation: str = ""
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = ""
    architecture: str = ""
    plan: dict[str, Any] | None = None
    current_plan_step: int = 1
    step_attempt: int = 1
    local_action_count: int = 0
    completed_steps: list[dict[str, Any]] = Field(default_factory=list)
    current_step_messages: list[dict[str, Any]] = Field(default_factory=list)
    verified_stock_codes: list[str] = Field(default_factory=list)
    last_step_error: str = ""


class AnalysisTask(BaseModel):
    """完整分析任务。"""

    id: str
    query: str
    status: str = AnalysisTaskStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    current_step: int = 0
    max_steps: int = 15
    events: list[AnalysisTaskEvent] = Field(default_factory=list)
    result: Theme | None = None
    error: str = ""
    saved_theme_id: str = ""
    checkpoint: AnalysisCheckpoint | None = None


class AnalysisTaskSummary(BaseModel):
    """分析任务摘要。"""

    id: str
    query: str
    status: str
    current_step: int = 0
    max_steps: int = 15
    updated_at: str = ""
    created_at: str = ""
    result_name: str = ""
    error: str = ""
    saved_theme_id: str = ""
