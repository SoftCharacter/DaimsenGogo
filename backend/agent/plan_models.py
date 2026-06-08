"""
Recursive Evidence-Planning Agent 执行模型
定义固定SOP计划、步骤结果和可恢复执行状态。
"""
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PlanStepStatus:
    """计划步骤状态常量。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanStep(BaseModel):
    """固定SOP中的单个执行步骤。"""

    id: int
    key: str
    name: str
    objective: str
    allowed_tools: list[str] = Field(default_factory=list)
    max_actions: int = 3
    required_outputs: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    status: str = PlanStepStatus.PENDING


class AnalysisPlan(BaseModel):
    """全局分析计划，步骤顺序由后端固定。"""

    version: str = "plan_execute_react_v1"
    query: str
    topic_name: str = ""
    description: str = ""
    candidate_search_terms: list[str] = Field(default_factory=list)
    category_hypotheses: list[str] = Field(default_factory=list)
    planning_candidate: list[dict[str, Any]] = Field(default_factory=list)
    planning_errors: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_planning_evidence(cls, data: Any) -> Any:
        """兼容旧 checkpoint 中的 planning_evidence 字段。"""
        if isinstance(data, dict) and "planning_candidate" not in data and "planning_evidence" in data:
            data = dict(data)
            data["planning_candidate"] = data.get("planning_evidence") or []
        return data


class CompletedStep(BaseModel):
    """已完成SOP步骤的结构化结果。"""

    step_id: int
    key: str
    name: str
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)


class HybridExecutionState(BaseModel):
    """递归证据规划智能体的可恢复运行状态。"""

    architecture: str = "plan_execute_react_v1"
    plan: AnalysisPlan | None = None
    current_plan_step: int = 1
    step_attempt: int = 1
    local_action_count: int = 0
    completed_steps: list[CompletedStep] = Field(default_factory=list)
    current_step_messages: list[dict[str, Any]] = Field(default_factory=list)
    verified_stock_codes: list[str] = Field(default_factory=list)
    last_step_error: str = ""
