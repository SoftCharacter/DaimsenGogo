"""
Plan-and-Execute + 局部ReAct混合主循环
全局SOP由后端固定控制，单个步骤内部使用有界ReAct处理局部不确定性。
"""
import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from backend.agent.output_parser import ParsedAction, ParsedFinalAnswer, ParsedStepResult, parse_llm_output
from backend.agent.plan_models import AnalysisPlan, CompletedStep, HybridExecutionState, PlanStep, PlanStepStatus
from backend.agent.prompts import get_final_assembly_prompt, get_planner_prompt, get_step_react_prompt
from backend.agent.react_loop import (
    _LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
    _LLM_SYNTHESIS_MAX_TOKENS_FLOOR,
    _build_theme_from_json,
    _call_llm,
    _execute_tool,
    _extract_theme_codes,
    _extract_verified_codes,
    _is_fatal_tool_failure,
    _make_event,
    _parse_tool_payload,
    _save_checkpoint,
)
from backend.agent.tools import web_search
from backend.models.analysis_task_models import AnalysisCheckpoint
from backend.models.config_models import AppConfig
from backend.models.theme_models import Theme
from backend.services.akshare_adapter import format_stock_code, get_stock_list
from backend.services.llm_client import LLMTruncationError, create_client

logger = logging.getLogger(__name__)
_ARCHITECTURE = "plan_execute_react_v1"
_STEP_ATTEMPTS = 3
_FORMAT_REPAIR_ATTEMPTS = 2
_FINAL_ATTEMPTS = 3
_PLANNING_WEB_SEARCH_LIMIT = 6
_PLANNING_WEB_SEARCH_TIMEOUT_SECONDS = 10
_PLANNING_LOCAL_CANDIDATE_SKIP_THRESHOLD = 8
_PLANNING_WEB_CONTEXT_CHARS = 1200
_PLANNING_WEB_STOCK_LIMIT = 20
_PLANNING_WEB_ENTRY_LIMIT = 30
_NEGATIVE_KEYWORDS = ("暂未", "否认", "不构成重大影响", "未采购", "无合作", "未合作", "不涉及", "传闻不实")
_STRONG_SOURCE_DOMAINS = ("cninfo.com.cn", "sse.com.cn", "szse.cn", "static.cninfo.com.cn")
_SECURITIES_SOURCE_DOMAINS = ("stcn.com", "cs.com.cn", "cnstock.com", "证券时报", "中国证券报", "上海证券报")
_SHARED_STOCK_LIST_CACHE = Path(__file__).resolve().parents[2] / "data" / "task_cache" / "_shared" / "stock_list.json"
_CODE_FIELD_NAMES = {"code", "stock_code", "symbol", "股票代码", "证券代码"}
_NAME_FIELD_NAMES = {"name", "stock_name", "股票名称", "股票简称", "证券简称"}
_CANDIDATE_STEP_KEYS = {"candidate_discovery", "candidate_expansion"}
_MIN_CANDIDATE_CODES = 18
_BUSINESS_CONFIRMATION_WEB_SEARCH_LIMIT = 4
# 结果分组上下文压缩参数。同一标的会在候选发现/业务确认/候选补全中重复出现，
# 跨步骤按代码去重可消除近3倍冗余、显著缩短prompt，降低第4步生成超时概率。
_GROUPING_FIELD_TRUNCATE_CHARS = 120   # 单只股票每个字段的最大字符数
_GROUPING_SUMMARY_TRUNCATE_CHARS = 400  # 每个步骤叙述摘要的最大字符数
_GROUPING_CANDIDATE_POOL_LIMIT = 80     # 去重后候选池上限，避免极端情况下仍过大
_MARKET_CODE_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)[:：]?\s*(\d{6})\b", re.IGNORECASE)
_SUFFIX_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})\s*[.．]\s*(SH|SZ|BJ)(?![A-Za-z0-9])", re.IGNORECASE)
_DIGIT_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_SEARCH_KEYWORD_SPLIT_PATTERN = re.compile(r"[,，、;；\n\r\t ]+")


@dataclass
class _StepOutcome:
    completed_step: CompletedStep | None = None
    error: str = ""
    fatal: bool = False


def _parse_json_object(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("结果必须是JSON对象")
    return data


def _completed_steps_dump(state: HybridExecutionState) -> list[dict[str, Any]]:
    return [item.model_dump() for item in state.completed_steps]


def _truncate_prompt_value(value: Any, limit: int = 1200) -> Any:
    if isinstance(value, str):
        text = value.strip()
        return text if len(text) <= limit else f"{text[:limit]}...（已截断）"
    if isinstance(value, list):
        return [_truncate_prompt_value(item, limit) for item in value[:30]]
    if isinstance(value, dict):
        return {str(key): _truncate_prompt_value(item, limit) for key, item in list(value.items())[:40]}
    return value


def _compact_completed_steps_for_prompt(state: HybridExecutionState) -> list[dict[str, Any]]:
    compact_steps: list[dict[str, Any]] = []
    for item in state.completed_steps:
        compact_steps.append({
            "step_id": item.step_id,
            "key": item.key,
            "name": item.name,
            "summary": _truncate_prompt_value(item.summary, 800),
            "data": _truncate_prompt_value(item.data, 1200),
        })
    return compact_steps


def _json_char_count(value: Any) -> int:
    """统计提示词上下文序列化后的字符数，用于定位模型超时输入规模。"""
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def _compact_stock_for_grouping(value: dict[str, Any]) -> dict[str, Any]:
    """仅保留结果分组所需的股票身份、关联依据和强度字段。"""
    keep_keys = (
        "code",
        "stock_code",
        "symbol",
        "股票代码",
        "证券代码",
        "name",
        "stock_name",
        "股票名称",
        "股票简称",
        "证券简称",
        "summary",
        "business_summary",
        "description",
        "relation",
        "relation_summary",
        "supply_chain_role",
        "role",
        "percentage",
        "score",
        "source",
        "source_type",
        "reason",
        "recommend_reason",
    )
    return {key: _truncate_prompt_value(value.get(key), _GROUPING_FIELD_TRUNCATE_CHARS) for key in keep_keys if value.get(key) not in (None, "", [], {})}


def _extract_grouping_stocks(value: Any, results: list[dict[str, Any]]) -> None:
    """从嵌套步骤数据中提取包含股票代码或名称的候选记录。"""
    if isinstance(value, dict):
        compact = _compact_stock_for_grouping(value)
        has_code = any(key in compact for key in _CODE_FIELD_NAMES)
        has_name = any(key in compact for key in _NAME_FIELD_NAMES)
        if has_code or has_name:
            results.append(compact)
        for nested in value.values():
            _extract_grouping_stocks(nested, results)
    elif isinstance(value, list):
        for item in value[:80]:
            _extract_grouping_stocks(item, results)


def _grouping_dedup_key(compact: dict[str, Any]) -> str:
    """为候选记录生成去重键，优先用规范化股票代码，其次用股票名称。"""
    for key in _CODE_FIELD_NAMES:
        raw = compact.get(key)
        if isinstance(raw, str) and raw.strip():
            normalized = _normalize_stock_code(raw)
            if normalized:
                return normalized
    for key in _NAME_FIELD_NAMES:
        raw = compact.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _merge_grouping_stock(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """把后续步骤补充的非空字段并入已有候选记录，保留更完整的关联依据。"""
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        if target.get(key) in (None, "", [], {}):
            target[key] = value


def _compact_completed_steps_for_grouping(state: HybridExecutionState) -> list[dict[str, Any]]:
    """为结果分组步骤构造最小上下文，避免携带长Observation和网页原文。

    同一标的会在候选发现/业务确认/候选补全三步重复出现，过去按步骤各自携带会把
    候选规模放大近3倍。这里改为跨步骤按代码/名称去重为单一候选池，并把后续步骤
    补充的非空字段并入同一记录，既消除冗余又保留更完整的关联依据，显著缩短输入。
    """
    # 仅保留各步骤的轻量叙述摘要，供模型理解步骤上下文，不再逐步重复携带股票。
    compact_steps: list[dict[str, Any]] = [
        {
            "step_id": item.step_id,
            "key": item.key,
            "name": item.name,
            "summary": _truncate_prompt_value(item.summary, _GROUPING_SUMMARY_TRUNCATE_CHARS),
        }
        for item in state.completed_steps
    ]

    # 跨步骤汇聚并去重股票，构造单一候选池。
    pool: dict[str, dict[str, Any]] = {}
    for item in state.completed_steps:
        stocks: list[dict[str, Any]] = []
        _extract_grouping_stocks(item.data, stocks)
        for compact in stocks:
            dedup_key = _grouping_dedup_key(compact)
            if not dedup_key:
                continue
            if dedup_key in pool:
                _merge_grouping_stock(pool[dedup_key], compact)
            else:
                pool[dedup_key] = compact

    candidate_pool = list(pool.values())[:_GROUPING_CANDIDATE_POOL_LIMIT]
    compact_steps.append({
        "key": "candidate_pool",
        "name": "去重后的候选池",
        "summary": f"跨步骤去重后共{len(candidate_pool)}个候选标的，请基于此池分组。",
        "stocks": candidate_pool,
    })
    return compact_steps


def _completed_steps_for_step_prompt(state: HybridExecutionState, step: PlanStep) -> list[dict[str, Any]]:
    """按步骤类型选择上下文压缩策略。"""
    if step.key == "category_grouping":
        return _compact_completed_steps_for_grouping(state)
    return _compact_completed_steps_for_prompt(state)


def _state_from_checkpoint(checkpoint: AnalysisCheckpoint | None) -> HybridExecutionState:
    if not checkpoint or checkpoint.architecture != _ARCHITECTURE or not checkpoint.plan:
        return HybridExecutionState()
    step_attempt = checkpoint.step_attempt
    if checkpoint.last_step_error and not checkpoint.current_step_messages:
        step_attempt = 1
    return HybridExecutionState(
        architecture=checkpoint.architecture,
        plan=AnalysisPlan.model_validate(checkpoint.plan),
        current_plan_step=checkpoint.current_plan_step,
        step_attempt=step_attempt,
        local_action_count=checkpoint.local_action_count,
        completed_steps=[CompletedStep.model_validate(item) for item in checkpoint.completed_steps],
        current_step_messages=[dict(item) for item in checkpoint.current_step_messages],
        verified_stock_codes=list(checkpoint.verified_stock_codes),
        last_step_error=checkpoint.last_step_error,
    )


def _checkpoint_payload(
    state: HybridExecutionState,
    model: str,
    temperature: float,
    max_tokens: int,
    *,
    messages: list[dict[str, Any]] | None = None,
    last_llm_output: str = "",
    last_action: dict[str, Any] | None = None,
    last_observation: str = "",
) -> dict[str, Any]:
    max_steps = len(state.plan.steps) if state.plan else 6
    return {
        "architecture": _ARCHITECTURE,
        "step": state.current_plan_step,
        "max_steps": max_steps,
        "messages": messages or [],
        "last_llm_output": last_llm_output,
        "last_action": last_action,
        "last_observation": last_observation,
        "config_snapshot": {
            "selected_model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "plan": state.plan.model_dump() if state.plan else None,
        "current_plan_step": state.current_plan_step,
        "step_attempt": state.step_attempt,
        "local_action_count": state.local_action_count,
        "completed_steps": _completed_steps_dump(state),
        "current_step_messages": state.current_step_messages,
        "verified_stock_codes": state.verified_stock_codes,
        "last_step_error": state.last_step_error,
    }


def _fixed_steps(planner_data: dict[str, Any], web_search_enabled: bool = False) -> list[PlanStep]:
    search_hints = [str(item) for item in planner_data.get("candidate_search_terms", []) if str(item).strip()]
    category_hints = [str(item) for item in planner_data.get("category_hypotheses", []) if str(item).strip()]
    business_confirmation_tools = ["get_company_info"]
    if web_search_enabled:
        business_confirmation_tools.append("web_search")
    return [
        PlanStep(
            id=1,
            key="candidate_discovery",
            name="候选发现",
            objective="根据规划提示中的公司简称、股票简称或明确企业名搜索A股候选标的。",
            allowed_tools=["search_stocks"],
            max_actions=20,
            required_outputs=["candidate_stocks"],
            hints=search_hints,
        ),
        PlanStep(
            id=2,
            key="business_confirmation",
            name="业务确认",
            objective="对核心候选调用公司信息工具，确认主营业务和供应链角色。",
            allowed_tools=business_confirmation_tools,
            max_actions=12,
            required_outputs=["confirmed_stocks"],
        ),
        PlanStep(
            id=3,
            key="candidate_expansion",
            name="候选补全",
            objective="基于已发现候选和供应链环节缺口，继续使用明确公司简称或股票简称补充A股候选标的。",
            allowed_tools=["search_stocks"],
            max_actions=14,
            required_outputs=["expanded_candidates"],
            hints=category_hints,
        ),
        PlanStep(
            id=4,
            key="category_grouping",
            name="结果分组",
            objective="基于已确认公司信息和补全候选按供应链环节分组，不调用工具。",
            allowed_tools=[],
            max_actions=0,
            required_outputs=["categories"],
            hints=category_hints,
        ),
        PlanStep(
            id=5,
            key="code_verification",
            name="代码校验",
            objective="一次性验证最终候选股票代码。",
            allowed_tools=["verify_stock_code"],
            max_actions=1,
            required_outputs=["verified_codes"],
        ),
        PlanStep(
            id=6,
            key="final_assembly",
            name="最终组装",
            objective="只使用已验证代码输出Theme JSON。",
            allowed_tools=[],
            max_actions=0,
            required_outputs=["theme"],
        ),
    ]


def _sanitize_plan_for_config(plan: AnalysisPlan, web_search_enabled: bool) -> AnalysisPlan:
    if web_search_enabled:
        return plan
    for step in plan.steps:
        if step.allowed_tools:
            step.allowed_tools = [tool for tool in step.allowed_tools if tool != "web_search"]
    return plan


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _build_plan(
    query: str,
    planner_data: dict[str, Any],
    web_search_enabled: bool = False,
    planning_evidence: list[dict[str, Any]] | None = None,
    planning_errors: list[str] | None = None,
) -> AnalysisPlan:
    topic_name = str(planner_data.get("topic_name") or query)
    description = str(planner_data.get("description") or f"{query}供应链分析")
    candidate_search_terms = [str(item) for item in planner_data.get("candidate_search_terms", []) if str(item).strip()]
    category_hypotheses = [str(item) for item in planner_data.get("category_hypotheses", []) if str(item).strip()]
    evidence = planning_evidence or []
    evidence_terms = [
        str(item.get("name") or item.get("code") or "").strip()
        for item in evidence
        if isinstance(item, dict)
    ]
    candidate_search_terms = _dedupe_preserve_order(evidence_terms + candidate_search_terms)
    if not candidate_search_terms:
        candidate_search_terms = [query]
    return AnalysisPlan(
        query=query,
        topic_name=topic_name,
        description=description,
        candidate_search_terms=candidate_search_terms,
        category_hypotheses=category_hypotheses,
        planning_evidence=evidence,
        planning_errors=planning_errors or [],
        steps=_fixed_steps({
            "candidate_search_terms": candidate_search_terms,
            "category_hypotheses": category_hypotheses,
        }, web_search_enabled=web_search_enabled),
    )


def _validate_step_result(step: PlanStep, data: dict[str, Any]) -> None:
    for key in step.required_outputs:
        value = data.get(key)
        if value in (None, "", [], {}):
            raise ValueError(f"步骤结果缺少必要字段或字段为空: {key}")


def _normalize_stock_code(raw_code: str) -> str | None:
    text = raw_code.strip().upper().replace("：", ":")
    market_match = _MARKET_CODE_PATTERN.search(text)
    if market_match:
        prefix = text[:market_match.start(1)].replace(" ", "").replace(":", "")[-2:]
        return f"{prefix}:{market_match.group(1)}"
    digit_match = _DIGIT_CODE_PATTERN.search(text)
    if digit_match:
        return format_stock_code(digit_match.group(1))
    return None


def _collect_stock_codes(value: Any) -> set[str]:
    codes: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(nested, str):
                normalized = _normalize_stock_code(nested)
                if normalized and (key in _CODE_FIELD_NAMES or _MARKET_CODE_PATTERN.search(nested)):
                    codes.add(normalized)
            codes.update(_collect_stock_codes(nested))
    elif isinstance(value, list):
        for item in value:
            codes.update(_collect_stock_codes(item))
    elif isinstance(value, str):
        for match in _MARKET_CODE_PATTERN.finditer(value):
            prefix = value[:match.start(1)].replace(" ", "").replace(":", "").replace("：", "")[-2:].upper()
            codes.add(f"{prefix}:{match.group(1)}")
    return codes


def _candidate_codes(state: HybridExecutionState) -> list[str]:
    codes: set[str] = set()
    for step in state.completed_steps:
        codes.update(_collect_stock_codes(step.data))
        codes.update(_collect_stock_codes(step.observations))
    return sorted(code for code in codes if code)


def _split_search_keywords(action_input: str) -> list[str]:
    keywords = [item.strip() for item in _SEARCH_KEYWORD_SPLIT_PATTERN.split(action_input) if item.strip()]
    return keywords or [action_input.strip()]


def _candidate_count_from_observations(observations: list[dict[str, Any]]) -> int:
    codes: set[str] = set()
    for observation in observations:
        if observation.get("tool") == "search_stocks":
            codes.update(_collect_stock_codes(observation.get("output", {})))
    return len(codes)


def _search_action_count(observations: list[dict[str, Any]]) -> int:
    return sum(1 for observation in observations if observation.get("tool") == "search_stocks")


def _tool_action_count(observations: list[dict[str, Any]], tool: str) -> int:
    """统计当前步骤内指定工具的调用次数。"""
    return sum(1 for observation in observations if observation.get("tool") == tool)


def _minimum_candidate_codes(state: HybridExecutionState, step: PlanStep) -> int:
    if step.key == "candidate_discovery" and state.plan and state.plan.planning_evidence:
        return max(3, min(8, len(state.plan.planning_evidence)))
    return _MIN_CANDIDATE_CODES


def _stock_name_code_map(state: HybridExecutionState) -> dict[str, str]:
    name_code_map: dict[str, str] = {}

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            code = ""
            name = ""
            for key, nested in value.items():
                if key in _CODE_FIELD_NAMES and isinstance(nested, str):
                    code = _normalize_stock_code(nested) or ""
                if key in _NAME_FIELD_NAMES and isinstance(nested, str):
                    name = nested.strip()
            if name and code:
                name_code_map[name] = code
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for step in state.completed_steps:
        collect(step.data)
        collect(step.observations)
    return name_code_map


def _normalize_company_info_input(action_input: str, state: HybridExecutionState) -> str | None:
    normalized = _normalize_stock_code(action_input)
    if normalized:
        return normalized
    text = action_input.strip()
    name_code_map = _stock_name_code_map(state)
    if text in name_code_map:
        return name_code_map[text]
    for name, code in name_code_map.items():
        if name and (name in text or text in name):
            return code
    return None


def _planning_entity_terms(query: str) -> list[str]:
    """从用户主题中生成主体/别名候选，避免直接拿“供应链”去搜本地股票名。"""
    topic = query.strip()
    if not topic:
        return []
    cleaned = re.sub(r"(供应链|产业链|概念股|概念|分析|相关股票|股票)$", "", topic).strip()
    terms = [topic]
    if cleaned and cleaned != topic:
        terms.append(cleaned)
    if cleaned and 2 <= len(cleaned) <= 12:
        terms.append(f"{cleaned} 工业有限公司")
        if not cleaned.startswith("重庆"):
            terms.append(f"重庆{cleaned}工业有限公司")
    return _dedupe_preserve_order(terms)


def _planning_web_query_specs(query: str) -> list[dict[str, str]]:
    """构造分层规划检索词：主体/股权/供应链/零部件/负向验证。"""
    entities = _planning_entity_terms(query)
    entity = entities[1] if len(entities) > 1 else entities[0] if entities else query.strip()
    company_entity = next((item for item in entities if "有限公司" in item), entity)
    specs: list[dict[str, str]] = []

    def add(group: str, text: str, topic: str = "general") -> None:
        if text.strip():
            specs.append({"group": group, "query": text.strip(), "topic": topic})

    # Entity Resolve：先锁定非上市主体、股东、融资与别名。
    add("entity_resolve", f"{entity} 工商 股东 A轮 融资", "general")
    add("entity_resolve", f"{company_entity} 股东 投资方 A轮 估值", "general")
    add("entity_resolve", f"{entity} 创始人 品牌 工商 主体", "general")

    # Capital Graph：寻找基金、LP、上市公司公告和穿透持股。
    add("capital_graph", f"{entity} A股 上市公司 投资 入股 公告", "finance")
    add("capital_graph", f"{entity} 基金 LP 上市公司 持股", "finance")
    add("capital_graph", f"{entity} 浙创投 金华浙创 金义智控 A股", "finance")
    add("capital_graph", f"金华浙创金义智控 {entity} 宏昌科技", "finance")
    add("capital_graph", f"宏昌科技 金华浙创金义智控 {entity}", "finance")

    # Supply Graph：找客户、供应商、技术合作伙伴、量产项目。
    add("supply_graph", f"{entity} 供应商 A股", "general")
    add("supply_graph", f"{entity} 官方技术合作伙伴", "general")
    add("supply_graph", f"{entity} 战略合作伙伴 供应商", "general")
    add("supply_graph", f"{entity} 量产 项目 A股", "general")
    add("supply_graph", f"{entity} 客户 年报", "finance")
    add("supply_graph", f"{entity} 客户 量产 项目", "general")

    # Part Supply Graph：按摩托车/二轮车关键部件枚举，避免泛“概念股”。
    for part in ["链传动", "轮毂", "进气系统", "智能仪表", "T-BOX", "BCM", "车身控制器", "芯片 仪表", "机油泵", "发动机"]:
        add("part_supply_graph", f"{entity} {part}", "general")

    # Negative Check：抓否认、弱口径和不构成重大影响，用于降权。
    add("negative_check", f"{entity} 暂未 采购 发动机", "general")
    add("negative_check", f"{entity} 不构成重大影响", "finance")
    add("negative_check", f"{entity} 否认 供应商", "general")
    add("negative_check", f"隆鑫通用 {entity} 暂未 大批量采购", "finance")

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for spec in specs:
        if spec["query"] in seen:
            continue
        seen.add(spec["query"])
        deduped.append(spec)
    return deduped[:_PLANNING_WEB_SEARCH_LIMIT]


def _load_stock_list_for_planning(task_id: str | None) -> list[dict[str, Any]]:
    """规划阶段优先读共享缓存，避免网页证据提取因行情源网络抖动变慢。"""
    try:
        cached = json.loads(_SHARED_STOCK_LIST_CACHE.read_text(encoding="utf-8"))
        if isinstance(cached, list) and cached:
            return [item for item in cached if isinstance(item, dict)]
    except Exception:
        pass
    try:
        return get_stock_list(task_id=task_id)
    except Exception as exc:
        logger.warning("规划阶段加载股票列表失败: %s", exc)
        return []


def _extract_web_stock_terms(entries: list[dict[str, Any]], task_id: str | None) -> list[dict[str, str]]:
    """从网页标题/摘要中提取直接出现的A股名称或代码，作为规划阶段强提示。"""
    chunks: list[str] = []
    for entry in entries:
        chunks.append(str(entry.get("title", "")))
        chunks.append(str(entry.get("content", "")))
        chunks.append(str(entry.get("raw_content", "")))
        chunks.append(str(entry.get("url", "")))
    text = "\n".join(chunks)
    if not text.strip():
        return []

    stock_list = _load_stock_list_for_planning(task_id=task_id)

    code_map = {str(item.get("code")): str(item.get("name")) for item in stock_list if item.get("code") and item.get("name")}
    name_map = {str(item.get("name")): str(item.get("code")) for item in stock_list if item.get("code") and item.get("name")}
    hits: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    def source_grade(url: str) -> str:
        lowered = url.lower()
        if any(domain in lowered for domain in _STRONG_SOURCE_DOMAINS):
            return "exchange_or_disclosure"
        if any(domain in lowered for domain in _SECURITIES_SOURCE_DOMAINS):
            return "securities_media"
        return "web"

    def relation_hint(entry_text: str, group: str) -> str:
        if group == "negative_check" or any(keyword in entry_text for keyword in _NEGATIVE_KEYWORDS):
            return "negative_or_weak"
        if any(keyword in entry_text for keyword in ("持股", "入股", "投资", "LP", "有限合伙", "基金", "股东")):
            return "capital"
        if any(keyword in entry_text for keyword in ("年报", "公告", "客户", "供应商", "量产", "项目", "供货")):
            return "supply_disclosure"
        if any(keyword in entry_text for keyword in ("技术合作伙伴", "战略合作伙伴", "官方合作伙伴")):
            return "partner"
        return group or "web_match"

    def add_hit(code: str, name: str, source: str, entry: dict[str, Any] | None = None) -> None:
        if not code or code in seen_codes:
            return
        seen_codes.add(code)
        entry = entry or {}
        entry_text = " ".join([
            str(entry.get("title", "")),
            str(entry.get("content", "")),
            str(entry.get("raw_content", ""))[:_PLANNING_WEB_CONTEXT_CHARS],
        ])
        hits.append({
            "code": code,
            "name": name or code_map.get(code, "") or code,
            "source": source,
            "group": str(entry.get("group", "")),
            "relation_hint": relation_hint(entry_text, str(entry.get("group", ""))),
            "source_grade": source_grade(str(entry.get("url", ""))),
            "url": str(entry.get("url", "")),
            "title": str(entry.get("title", "")),
        })

    for entry in entries:
        entry_text = "\n".join([
            str(entry.get("title", "")),
            str(entry.get("content", "")),
            str(entry.get("raw_content", "")),
            str(entry.get("url", "")),
        ])
        for match in _SUFFIX_CODE_PATTERN.finditer(entry_text):
            code = f"{match.group(2).upper()}:{match.group(1)}"
            add_hit(code, code_map.get(code, ""), "web_code", entry)
        for name, code in name_map.items():
            if len(name) < 2 or code in seen_codes:
                continue
            if name in entry_text:
                add_hit(code, name, "web_name", entry)
            if len(hits) >= _PLANNING_WEB_STOCK_LIMIT:
                break
        if len(hits) >= _PLANNING_WEB_STOCK_LIMIT:
            break

    return hits[:_PLANNING_WEB_STOCK_LIMIT]


def _planning_cache_path(query: str, task_id: str | None) -> Path | None:
    """返回规划阶段网页检索缓存路径；无任务ID时不落盘。"""
    if not task_id:
        return None
    safe_task_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())[:80]
    if not safe_task_id:
        return None
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return Path(__file__).resolve().parents[2] / "data" / "task_cache" / safe_task_id / f"planning_web_{query_hash}.json"


def _read_planning_cache(query: str, task_id: str | None) -> dict[str, Any] | None:
    """读取任务级规划检索缓存，避免继续任务时重复调用Tavily。"""
    path = _planning_cache_path(query, task_id)
    if not path:
        return None
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None
    return None


def _write_planning_cache(query: str, task_id: str | None, payload: dict[str, Any]) -> None:
    """写入任务级规划检索缓存，失败不影响主分析流程。"""
    path = _planning_cache_path(query, task_id)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _collect_local_planning_candidates(query: str, task_id: str | None) -> list[dict[str, str]]:
    """从本地股票列表提取直接候选，足够时跳过规划前网页搜索。"""
    terms = [term for term in _planning_entity_terms(query) if len(term) >= 2]
    stock_list = _load_stock_list_for_planning(task_id=task_id)
    hits: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for item in stock_list:
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        if not code or not name or code in seen_codes:
            continue
        if any(term in name or name in term for term in terms):
            seen_codes.add(code)
            hits.append({
                "code": code,
                "name": name,
                "source": "local_stock_list",
                "group": "local_candidate",
                "relation_hint": "local_name_match",
                "source_grade": "local_cache",
                "url": "",
                "title": "本地股票列表命中",
            })
        if len(hits) >= _PLANNING_WEB_STOCK_LIMIT:
            break
    return hits


def _planning_result(queries: list[dict[str, str]], entries: list[dict[str, Any]], stock_terms: list[dict[str, str]], errors: list[str]) -> dict[str, Any]:
    return {"queries": queries, "entries": entries, "stock_terms": stock_terms, "errors": errors}


def _format_planning_web_context(payload: dict[str, Any]) -> str:
    stock_terms = payload.get("stock_terms") if isinstance(payload, dict) else None
    entries = payload.get("entries") if isinstance(payload, dict) else None
    lines: list[str] = []
    if isinstance(stock_terms, list) and stock_terms:
        formatted_terms = []
        for item in stock_terms[:_PLANNING_WEB_STOCK_LIMIT]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("code") or "").strip()
            code = str(item.get("code") or "").strip()
            if name and code:
                relation = str(item.get("relation_hint") or "").strip()
                grade = str(item.get("source_grade") or "").strip()
                formatted_terms.append(f"{name}({code}, {relation}, {grade})")
        if formatted_terms:
            lines.append("网页直接命中的A股候选：" + "、".join(formatted_terms))

    if isinstance(entries, list):
        for index, entry in enumerate(entries[:_PLANNING_WEB_ENTRY_LIMIT], start=1):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            url = str(entry.get("url", "")).strip()
            group = str(entry.get("group", "")).strip()
            content_source = str(entry.get("raw_content") or entry.get("content") or "")
            content = content_source.strip().replace("\n", " ")
            if len(content) > _PLANNING_WEB_CONTEXT_CHARS:
                content = content[:_PLANNING_WEB_CONTEXT_CHARS] + "..."
            lines.append(f"[{index}] {group} | {title} | {url} | {content}")
    return "\n".join(lines)


async def _execute_planning_web_search(action_input: str, task_id: str | None) -> str:
    """规划阶段网页搜索使用短超时，失败时降级为非致命错误。"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(web_search, action_input, task_id),
            timeout=_PLANNING_WEB_SEARCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return json.dumps({
            "error": "规划阶段网页搜索超时，已降级继续分析",
            "fatal": False,
            "retryable": False,
            "results": [],
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "error": f"规划阶段网页搜索异常，已降级继续分析: {exc}",
            "fatal": False,
            "retryable": False,
            "results": [],
        }, ensure_ascii=False)


async def _collect_planning_web_context(query: str, task_id: str | None) -> dict[str, Any]:
    """在规划前执行网页检索，让planner先看到新事件的真实边界和直接候选。"""
    cached = _read_planning_cache(query, task_id)
    if cached is not None:
        return cached

    query_specs = _planning_web_query_specs(query)
    local_candidates = _collect_local_planning_candidates(query, task_id)
    if len(local_candidates) >= _PLANNING_LOCAL_CANDIDATE_SKIP_THRESHOLD:
        payload = _planning_result(
            query_specs,
            [],
            local_candidates,
            ["本地股票列表候选已足够，跳过规划前网页搜索"],
        )
        _write_planning_cache(query, task_id, payload)
        return payload

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for spec in query_specs:
        search_query = spec["query"]
        action_input = json.dumps({
            "query": search_query,
            "search_depth": "basic",
            "max_results": 5,
            "topic": spec.get("topic", "general"),
            "include_raw_content": False,
            "chunks_per_source": 1,
        }, ensure_ascii=False)
        try:
            result = await _execute_planning_web_search(action_input, task_id=task_id)
        except Exception as exc:
            error_message = f"规划阶段网页检索超时或异常: {exc}"
            errors.append(error_message)
            logger.warning("规划阶段网页检索异常 [%s]: %s", search_query, exc)
            continue
        payload = _parse_tool_payload(result)
        if not payload or payload.get("error"):
            error_message = str(payload.get("error") if payload else "非JSON")
            errors.append(error_message)
            logger.info("规划阶段网页检索不可用 [%s]: %s", search_query, error_message)
            if "TAVILY_API_KEY" in error_message:
                break
            continue
        for item in payload.get("results", []):
            if isinstance(item, dict):
                entries.append({
                    "query": search_query,
                    "group": spec.get("group", ""),
                    "title": str(item.get("title", "")),
                    "url": str(item.get("url", "")),
                    "content": str(item.get("content", "")),
                    "raw_content": str(item.get("raw_content", "")),
                    "score": item.get("score"),
                })

    stock_terms = _extract_web_stock_terms(entries, task_id=task_id)
    payload = _planning_result(query_specs, entries, local_candidates + stock_terms, errors)
    _write_planning_cache(query, task_id, payload)
    return payload


async def _create_plan(
    query: str,
    client,
    model: str,
    temperature: float,
    max_tokens: int,
    web_search_enabled: bool = False,
    task_id: str | None = None,
) -> AnalysisPlan:
    planning_web_context: dict[str, Any] = {}
    if web_search_enabled:
        planning_web_context = await _collect_planning_web_context(query, task_id=task_id)
    planning_evidence = planning_web_context.get("stock_terms", []) if planning_web_context else []
    planning_errors = planning_web_context.get("errors", []) if planning_web_context else []
    web_context_text = _format_planning_web_context(planning_web_context)
    messages = [
        {"role": "system", "content": get_planner_prompt(query, web_context=web_context_text)},
        {"role": "user", "content": "请输出规划JSON。"},
    ]
    # 规划同为纯合成步骤，需输出15-30个候选词加8-15个分类；思考型模型推理链会额外吃预算，
    # 故对输出预算取下限兜底，避免正文未写完就被max_tokens截断、回退成只含主题原文的降级计划。
    planning_max_tokens = max(max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR)
    try:
        planner_output = await _call_llm(
            client, model, messages, temperature, planning_max_tokens, 0,
            idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
        )
        planner_data = _parse_json_object(planner_output)
    except LLMTruncationError as exc:
        # 已抬到合成下限仍被截断：重试同样会再次截断，直接降级为最小可用计划，避免空转。
        logger.warning("规划输出在max_tokens=%d仍被截断（已生成%d字符），回退为降级计划。", planning_max_tokens, exc.generated_chars)
        planner_data = {
            "topic_name": query,
            "description": f"{query}供应链分析",
            "candidate_search_terms": [query],
            "category_hypotheses": [],
        }
    except Exception:
        planner_data = {
            "topic_name": query,
            "description": f"{query}供应链分析",
            "candidate_search_terms": [query],
            "category_hypotheses": [],
        }
    return _build_plan(
        query,
        planner_data,
        web_search_enabled=web_search_enabled,
        planning_evidence=planning_evidence,
        planning_errors=planning_errors,
    )


async def _run_bounded_react_step(
    query: str,
    config: AppConfig,
    client,
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
    save_checkpoint,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    model = config.selected_model
    temperature = config.settings.temperature
    # 结果分组需输出全部候选的分类JSON，体量大，对输出预算取下限兜底，避免被max_tokens截断。
    max_tokens = config.settings.max_tokens
    if step.key == "category_grouping":
        max_tokens = max(max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR)

    observations: list[dict[str, Any]] = []

    for attempt in range(state.step_attempt, _STEP_ATTEMPTS + 1):
        state.step_attempt = attempt
        state.local_action_count = 0
        if not state.current_step_messages:
            completed_steps_for_prompt = _completed_steps_for_step_prompt(state, step)
            prompt_content = get_step_react_prompt(
                query,
                state.plan.model_dump() if state.plan else {},
                step.model_dump(),
                completed_steps_for_prompt,
                attempt,
            )
            if step.key == "category_grouping":
                logger.info(
                    "结果分组LLM输入规模：raw_completed_steps=%d, compact_completed_steps=%d, prompt=%d, model=%s, max_tokens=%d, temperature=%s",
                    _json_char_count(_completed_steps_dump(state)),
                    _json_char_count(completed_steps_for_prompt),
                    len(prompt_content),
                    model,
                    max_tokens,
                    temperature,
                )
            state.current_step_messages = [
                {
                    "role": "system",
                    "content": prompt_content,
                },
                {"role": "user", "content": f"请执行当前SOP步骤：{step.name}"},
            ]

        await _save_checkpoint(
            save_checkpoint,
            _checkpoint_payload(state, model, temperature, max_tokens, messages=state.current_step_messages),
        )
        yield _make_event(
            "thinking",
            content=f"开始执行计划步骤 {step.id}/{len(state.plan.steps) if state.plan else 6}：{step.name}（第{attempt}/3次尝试）。",
            step=step.id,
            task_id=task_id,
            plan_step=step.name,
            attempt=attempt,
        )

        local_turn_count = 0
        max_local_turns = max(step.max_actions + 3, 3)
        # 结果分组为纯合成步骤，输出长且首token前可能有较长思考，放宽流式空闲超时。
        step_idle_timeout = _LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS if step.key == "category_grouping" else None
        while local_turn_count < max_local_turns:
            local_turn_count += 1
            llm_output = ""
            parsed = None
            # 标记本轮是否因输出被max_tokens截断而需要抬高预算后原地重试（区别于格式修复与致命失败）。
            truncation_retry = False
            repair_messages = [dict(item) for item in state.current_step_messages]
            for repair_index in range(_FORMAT_REPAIR_ATTEMPTS + 1):
                try:
                    llm_started_at = time.perf_counter()
                    llm_output = await _call_llm(
                        client, model, repair_messages, temperature, max_tokens, step.id,
                        idle_timeout=step_idle_timeout,
                    )
                    if step.key == "category_grouping":
                        logger.info(
                            "结果分组LLM调用完成：耗时=%.2fs, 输出字符数=%d, 修复轮次=%d",
                            time.perf_counter() - llm_started_at,
                            len(llm_output),
                            repair_index + 1,
                        )
                except LLMTruncationError as exc:
                    # 中间步骤输出被max_tokens截断：与最终组装不同，这里重试有意义——
                    # 抬高输出预算后，模型通常能产出完整且可解析的 Step Result。
                    # 因此不按致命错误处理，而是优先在保留已有工具结果的前提下原地重试。
                    bumped = max(max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR)
                    if bumped > max_tokens:
                        logger.warning(
                            "步骤%d输出被max_tokens截断（已生成%d字符）：将max_tokens从%d提升到%d后原地重试，不丢弃已完成的工具调用。",
                            step.id, exc.generated_chars, max_tokens, bumped,
                        )
                        max_tokens = bumped
                        truncation_retry = True
                    else:
                        # 已处于输出预算上限仍被截断：按可重试的步骤失败处理，交由外层尝试循环。
                        logger.warning(
                            "步骤%d在max_tokens=%d仍被截断（已生成%d字符），按步骤失败重试。",
                            step.id, max_tokens, exc.generated_chars,
                        )
                        state.last_step_error = f"模型输出被max_tokens截断（已生成{exc.generated_chars}字符）"
                    break
                except Exception as exc:
                    if step.key == "category_grouping":
                        logger.warning(
                            "结果分组LLM调用失败：异常类型=%s, 耗时=%.2fs, 修复轮次=%d, 错误=%s",
                            type(exc).__name__,
                            time.perf_counter() - llm_started_at,
                            repair_index + 1,
                            str(exc) or type(exc).__name__,
                        )
                    yield _StepOutcome(error=str(exc), fatal=True)
                    return

                parsed = parse_llm_output(llm_output)
                await _save_checkpoint(
                    save_checkpoint,
                    _checkpoint_payload(state, model, temperature, max_tokens, messages=repair_messages, last_llm_output=llm_output),
                )
                if parsed is not None:
                    break
                if repair_index == _FORMAT_REPAIR_ATTEMPTS:
                    state.last_step_error = "模型输出格式连续不符合当前SOP步骤要求"
                    break
                repair_messages.extend([
                    {"role": "assistant", "content": llm_output},
                    {"role": "user", "content": "上一条无法解析。请只输出 Thought/Action/Action Input 或 Thought/Step Result；不要输出 Observation 或 Final Answer。"},
                ])

            # 截断后已抬高输出预算：原地重试本轮（state.current_step_messages 未变，保留前序工具结果），
            # 不计入格式修复、不致命退出，让模型用更大预算重新产出完整 Step Result。
            if truncation_retry:
                continue

            if parsed and getattr(parsed, "thought", ""):
                yield _make_event("thinking", content=parsed.thought, step=step.id, task_id=task_id, plan_step=step.name, attempt=attempt)

            if isinstance(parsed, ParsedStepResult):
                try:
                    data = _parse_json_object(parsed.result)
                    _validate_step_result(step, data)
                    candidate_count = _candidate_count_from_observations(observations)
                    search_count = _search_action_count(observations)
                    min_candidate_codes = _minimum_candidate_codes(state, step)
                    if step.key in _CANDIDATE_STEP_KEYS and candidate_count < min_candidate_codes and state.local_action_count < step.max_actions:
                        state.current_step_messages = repair_messages + [
                            {"role": "assistant", "content": llm_output},
                            {"role": "user", "content": f"当前步骤候选覆盖不足，至少需要{min_candidate_codes}个已搜索到的A股候选。请优先使用全局计划 candidate_search_terms 前列的公司简称或股票代码调用 search_stocks；不要搜索泛行业词，也不要直接输出 Step Result。"},
                        ]
                        continue
                    if step.key in _CANDIDATE_STEP_KEYS and search_count == 0:
                        raise ValueError("候选步骤必须先实际调用 search_stocks，再输出 Step Result")
                    completed = CompletedStep(
                        step_id=step.id,
                        key=step.key,
                        name=step.name,
                        summary=str(data.get("summary", "")),
                        data=data,
                        observations=observations,
                    )
                    yield _StepOutcome(completed_step=completed)
                    return
                except Exception as exc:
                    state.last_step_error = str(exc)
                    break

            if isinstance(parsed, ParsedFinalAnswer):
                state.last_step_error = "当前步骤不能输出Final Answer"
                break

            if isinstance(parsed, ParsedAction):
                if parsed.action not in step.allowed_tools:
                    state.current_step_messages = repair_messages + [
                        {"role": "assistant", "content": llm_output},
                        {"role": "user", "content": f"工具 {parsed.action} 不允许在当前步骤使用。当前步骤只允许：{','.join(step.allowed_tools) or '无'}。请改用允许工具或输出 Step Result。"},
                    ]
                    continue
                if step.key == "business_confirmation" and parsed.action == "web_search" and _tool_action_count(observations, "web_search") >= _BUSINESS_CONFIRMATION_WEB_SEARCH_LIMIT:
                    state.current_step_messages = repair_messages + [
                        {"role": "assistant", "content": llm_output},
                        {"role": "user", "content": "本步骤 web_search 额度已用尽。请基于已有 get_company_info 和网页Observation输出 Step Result JSON，不要继续网页搜索。"},
                    ]
                    continue
                action_inputs = [parsed.action_input]
                if parsed.action == "search_stocks":
                    action_inputs = _split_search_keywords(parsed.action_input)
                elif parsed.action == "get_company_info":
                    normalized_input = _normalize_company_info_input(parsed.action_input, state)
                    if not normalized_input:
                        state.current_step_messages = repair_messages + [
                            {"role": "assistant", "content": llm_output},
                            {"role": "user", "content": "get_company_info 必须使用已发现候选的股票代码。请从候选列表中选择 code 字段作为 Action Input。"},
                        ]
                        continue
                    action_inputs = [normalized_input]

                tool_results: list[str] = []
                executed_inputs: list[str] = []
                for action_input in action_inputs:
                    if state.local_action_count >= step.max_actions:
                        break
                    state.local_action_count += 1
                    action = ParsedAction(thought=parsed.thought, action=parsed.action, action_input=action_input)
                    executed_inputs.append(action_input)
                    yield _make_event("tool_call", tool=action.action, input=action.action_input, step=step.id, task_id=task_id, plan_step=step.name, attempt=attempt)
                    tool_result = await _execute_tool(action, task_id=task_id)
                    tool_results.append(tool_result)
                    yield _make_event("tool_result", tool=action.action, output=tool_result, step=step.id, task_id=task_id, plan_step=step.name, attempt=attempt)

                    payload = _parse_tool_payload(tool_result)
                    observations.append({"tool": action.action, "input": action.action_input, "output": payload or tool_result})
                    if _is_fatal_tool_failure(tool_result):
                        message = (payload or {}).get("error", "工具返回格式异常")
                        yield _StepOutcome(error=message, fatal=True)
                        return

                if not tool_results:
                    state.current_step_messages = repair_messages + [
                        {"role": "assistant", "content": llm_output},
                        {"role": "user", "content": "本步骤工具行动额度已用尽，请基于已有Observation输出 Step Result JSON。"},
                    ]
                    continue

                observation_text = "\n".join(f"Observation: {result}" for result in tool_results)
                state.current_step_messages = repair_messages + [
                    {"role": "assistant", "content": llm_output},
                    {"role": "user", "content": observation_text},
                ]
                await _save_checkpoint(
                    save_checkpoint,
                    _checkpoint_payload(
                        state,
                        model,
                        temperature,
                        max_tokens,
                        messages=state.current_step_messages,
                        last_llm_output=llm_output,
                        last_action={"action": parsed.action, "action_input": ",".join(executed_inputs), "thought": parsed.thought},
                        last_observation="\n".join(tool_results),
                    ),
                )
                continue

            state.current_step_messages = []
            break

        yield _make_event(
            "thinking",
            content=f"计划步骤「{step.name}」第{attempt}/3次尝试失败：{state.last_step_error or '未能产出合法步骤结果'}。",
            step=step.id,
            task_id=task_id,
            plan_step=step.name,
            attempt=attempt,
        )
        state.current_step_messages = []
        await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))

    yield _StepOutcome(error=f"计划步骤「{step.name}」连续3次失败：{state.last_step_error}")


async def _run_code_verification(
    config: AppConfig,
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
    save_checkpoint,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    model = config.selected_model
    temperature = config.settings.temperature
    max_tokens = config.settings.max_tokens
    codes = _candidate_codes(state)
    if not codes:
        yield _StepOutcome(error="没有可校验的候选股票代码")
        return

    action = ParsedAction(thought="按SOP一次性校验最终候选股票代码。", action="verify_stock_code", action_input=",".join(codes))
    yield _make_event("tool_call", tool=action.action, input=action.action_input, step=step.id, task_id=task_id, plan_step=step.name, attempt=state.step_attempt)
    tool_result = await _execute_tool(action, task_id=task_id)
    yield _make_event("tool_result", tool=action.action, output=tool_result, step=step.id, task_id=task_id, plan_step=step.name, attempt=state.step_attempt)

    if _is_fatal_tool_failure(tool_result):
        message = (_parse_tool_payload(tool_result) or {}).get("error", "工具返回格式异常")
        yield _StepOutcome(error=message, fatal=True)
        return

    verified_codes = sorted(_extract_verified_codes(tool_result))
    if not verified_codes:
        yield _StepOutcome(error="股票代码校验未得到任何有效代码")
        return

    state.verified_stock_codes = verified_codes
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=f"已验证{len(verified_codes)}个股票代码。",
        data={"verified_codes": verified_codes, "raw_result": _parse_tool_payload(tool_result) or {}},
    )
    await _save_checkpoint(
        save_checkpoint,
        _checkpoint_payload(
            state,
            model,
            temperature,
            max_tokens,
            last_action={"action": action.action, "action_input": action.action_input, "thought": action.thought},
            last_observation=tool_result,
        ),
    )
    yield _StepOutcome(completed_step=completed)


def _stock_code_from_record(record: dict[str, Any]) -> str | None:
    """从单条记录中提取并规范化股票代码，找不到返回None。"""
    for key in _CODE_FIELD_NAMES:
        raw = record.get(key)
        if isinstance(raw, str) and raw.strip():
            normalized = _normalize_stock_code(raw)
            if normalized:
                return normalized
    return None


def _walk_stock_records(value: Any, out: list[dict[str, Any]]) -> None:
    """深度遍历步骤数据，收集所有带股票代码的原始记录（不截断，保留完整业务依据）。"""
    if isinstance(value, dict):
        if _stock_code_from_record(value):
            out.append(value)
        for nested in value.values():
            _walk_stock_records(nested, out)
    elif isinstance(value, list):
        for item in value:
            _walk_stock_records(item, out)


def _verification_name_map(state: HybridExecutionState) -> dict[str, str]:
    """从代码校验步骤原始结果提取权威 code->name 映射，作为最终股票名的首选来源。"""
    name_map: dict[str, str] = {}
    for item in state.completed_steps:
        if item.key != "code_verification":
            continue
        raw_result = (item.data or {}).get("raw_result") or {}
        for entry in raw_result.get("results", []):
            if isinstance(entry, dict) and entry.get("valid") and entry.get("code"):
                name_map[str(entry["code"])] = str(entry.get("name") or "").strip()
    return name_map


# 程序化组装时挑选业务描述的字段优先级：直接业务说明 > 公告/年报证据 > 关联关系 > 入选理由 > 摘要。
_DESCRIPTION_FIELD_PRIORITY = (
    "description",
    "business_summary",
    "evidence",
    "relation_summary",
    "relation",
    "reason",
    "recommend_reason",
    "summary",
)


def _description_evidence_map(state: HybridExecutionState) -> tuple[dict[str, str], set[str]]:
    """汇聚 code->业务描述 映射，并标记拥有直接业务证据的强关联代码。

    返回:
        (描述映射, 强关联代码集合)。强关联指出现在业务确认步骤或带 evidence/description
        字段的记录，程序化组装时给予更高的关联强度分。
    """
    desc_map: dict[str, str] = {}
    evidence_codes: set[str] = set()
    for item in state.completed_steps:
        records: list[dict[str, Any]] = []
        _walk_stock_records(item.data, records)
        for record in records:
            code = _stock_code_from_record(record)
            if not code:
                continue
            if item.key == "business_confirmation" or record.get("evidence") or record.get("description"):
                evidence_codes.add(code)
            if code in desc_map:
                continue
            for field in _DESCRIPTION_FIELD_PRIORITY:
                value = record.get(field)
                if isinstance(value, str) and value.strip():
                    desc_map[code] = value.strip()
                    break
    return desc_map, evidence_codes


def _grouping_category_items(state: HybridExecutionState) -> list[tuple[str, list[Any]]]:
    """从结果分组步骤提取 (分类名, 股票记录列表)，兼容dict和list两种产出形态。"""
    grouping_data: Any = None
    for item in state.completed_steps:
        if item.key == "category_grouping":
            grouping_data = (item.data or {}).get("categories")
            break
    items: list[tuple[str, list[Any]]] = []
    if isinstance(grouping_data, dict):
        for name, records in grouping_data.items():
            if isinstance(records, list):
                items.append((str(name).strip(), records))
    elif isinstance(grouping_data, list):
        for entry in grouping_data:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("category") or entry.get("id") or "").strip()
            records = entry.get("stocks") or entry.get("members") or []
            if name and isinstance(records, list):
                items.append((name, records))
    return items


# 程序化组装的关联强度默认分：有直接业务证据的标的更高，仅凭分组归类的取中性分。
_FALLBACK_PERCENTAGE_WITH_EVIDENCE = 85
_FALLBACK_PERCENTAGE_DEFAULT = 60


def _assemble_theme_from_completed_steps(
    query: str,
    state: HybridExecutionState,
    task_id: str | None,
) -> Theme:
    """LLM最终组装失败时的程序化兜底：复用已完成步骤的分组结构和校验结果直接拼装Theme。

    分组步骤已完成全部分类智力工作、代码已逐一验证，因此最终组装本质只是格式转换，
    完全可以脱离模型确定性地完成，避免长JSON被max_tokens截断导致整任务失败。

    异常:
        ValueError: 缺少分组数据或拼装后没有任何有效分类。
    """
    category_items = _grouping_category_items(state)
    if not category_items:
        raise ValueError("缺少结果分组数据，无法程序化组装")

    verified = set(state.verified_stock_codes)
    name_map = _verification_name_map(state)
    desc_map, evidence_codes = _description_evidence_map(state)
    plan = state.plan
    topic_name = (plan.topic_name if plan else "") or query
    description = (plan.description if plan else "") or f"{query}供应链分析"

    categories: list[dict[str, Any]] = []
    order = 0
    for cat_name, records in category_items:
        if not cat_name:
            continue
        seen_codes: set[str] = set()
        stocks: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            code = _stock_code_from_record(record)
            # 只接纳已验证且未在本分类重复的代码，确保最终结果可信、无重复。
            if not code or code not in verified or code in seen_codes:
                continue
            seen_codes.add(code)
            stock_name = name_map.get(code) or str(record.get("name") or "").strip() or code
            stock_desc = desc_map.get(code) or str(record.get("role") or "").strip() or f"{cat_name}相关标的"
            stocks.append({
                "code": code,
                "name": stock_name,
                "name_en": "",
                "percentage": _FALLBACK_PERCENTAGE_WITH_EVIDENCE if code in evidence_codes else _FALLBACK_PERCENTAGE_DEFAULT,
                "description": stock_desc,
                "category_tag": cat_name,
            })
        if not stocks:
            continue
        order += 1
        categories.append({
            "id": f"cat_{order}",
            "name": cat_name,
            "order": order,
            "stocks": stocks,
        })

    if not categories:
        raise ValueError("程序化组装未得到任何有效分类")

    theme_dict = {
        "name": topic_name,
        "description": description,
        "source_task_id": task_id or "",
        "categories": categories,
    }
    # 复用统一构建逻辑：补全id/时间、做Theme业务校验并按关联强度排序。
    return _build_theme_from_json(json.dumps(theme_dict, ensure_ascii=False))


async def _emit_programmatic_assembly(
    query: str,
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
    llm_error: str,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    """在LLM最终组装失败后发出程序化兜底结果；兜底也失败时返回带双重原因的错误。"""
    try:
        theme = _assemble_theme_from_completed_steps(query, state, task_id)
    except Exception as exc:
        yield _StepOutcome(error=f"最终组装失败: {llm_error}；程序化兜底也失败: {exc}")
        return
    logger.warning("最终组装回退为程序化组装：LLM失败=%s，生成分类=%d", llm_error, len(theme.categories))
    yield _make_event(
        "thinking",
        content=f"最终组装由程序化兜底生成（{len(theme.categories)}个分类），原因：{llm_error}。",
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )
    yield _make_event("result", theme=json.loads(theme.model_dump_json()), task_id=task_id)
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=f"最终Theme由程序化组装兜底生成（{len(theme.categories)}个分类）。",
        data={"theme_id": theme.id, "fallback": True},
    )
    yield _StepOutcome(completed_step=completed)


async def _run_final_assembly(
    query: str,
    config: AppConfig,
    client,
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    model = config.selected_model
    temperature = config.settings.temperature
    # 最终组装输出全部已验证股票的完整Theme JSON，体量大，对输出预算取下限兜底，避免被截断。
    max_tokens = max(config.settings.max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR)
    messages = [
        {
            "role": "system",
            "content": get_final_assembly_prompt(
                query,
                state.plan.model_dump() if state.plan else {},
                _compact_completed_steps_for_prompt(state),
                state.verified_stock_codes,
            ),
        },
        {"role": "user", "content": "请生成最终Theme JSON。"},
    ]

    llm_error = ""
    for attempt in range(1, _FINAL_ATTEMPTS + 1):
        try:
            # 最终组装同为纯合成步骤，输出长JSON，放宽流式空闲超时。
            output = await _call_llm(
                client, model, messages, temperature, max_tokens, step.id,
                idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
            )
            parsed = parse_llm_output(output)
            if parsed and getattr(parsed, "thought", ""):
                yield _make_event("thinking", content=parsed.thought, step=step.id, task_id=task_id, plan_step=step.name, attempt=attempt)
            if not isinstance(parsed, ParsedFinalAnswer):
                raise ValueError("最终组装必须输出Final Answer")
            theme = _build_theme_from_json(parsed.answer)
            missing_codes = sorted(_extract_theme_codes(theme) - set(state.verified_stock_codes))
            if missing_codes:
                raise ValueError(f"最终答案包含未验证股票代码: {','.join(missing_codes)}")
            yield _make_event("result", theme=json.loads(theme.model_dump_json()), task_id=task_id)
            completed = CompletedStep(
                step_id=step.id,
                key=step.key,
                name=step.name,
                summary="最终Theme JSON已生成。",
                data={"theme_id": theme.id},
            )
            yield _StepOutcome(completed_step=completed)
            return
        except LLMTruncationError as exc:
            # 截断重试无意义（相同max_tokens会再次截断），直接转程序化兜底。
            llm_error = f"模型输出被max_tokens截断（已生成{exc.generated_chars}字符）"
            break
        except Exception as exc:
            llm_error = str(exc)
            if attempt == _FINAL_ATTEMPTS:
                break
            messages.extend([
                {"role": "assistant", "content": output if 'output' in locals() else ""},
                {"role": "user", "content": f"最终JSON无法解析或校验失败：{exc}。请只使用已验证代码重新输出 Final Answer 和合法JSON。"},
            ])

    # LLM路径已耗尽或被截断，转为程序化组装兜底，避免丢弃前序所有有效成果。
    async for event in _emit_programmatic_assembly(query, state, step, task_id, llm_error):
        yield event


async def plan_execute_react_loop(
    query: str,
    config: AppConfig,
    *,
    checkpoint: AnalysisCheckpoint | None = None,
    task_id: str | None = None,
    save_checkpoint=None,
) -> AsyncGenerator[dict, None]:
    """Plan-and-Execute主循环，单个SOP步骤内部使用有界ReAct。"""
    client = create_client(config)
    model = config.selected_model
    temperature = config.settings.temperature
    max_tokens = config.settings.max_tokens
    state = _state_from_checkpoint(checkpoint)
    if state.plan:
        state.plan = _sanitize_plan_for_config(state.plan, config.web_search.enabled)

    if not state.plan:
        yield _make_event("thinking", content="正在生成全局执行计划，SOP步骤将由系统固定控制；如已启用网页搜索，会先检索公开证据校准候选。", step=0, task_id=task_id)
        state.plan = await _create_plan(query, client, model, temperature, max_tokens, config.web_search.enabled, task_id=task_id)
        state.current_plan_step = 1
        state.step_attempt = 1
        await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
        step_names = " → ".join(step.name for step in state.plan.steps)
        evidence_count = len(state.plan.planning_evidence)
        evidence_note = f"；规划前网页命中{evidence_count}个A股候选" if evidence_count else ""
        errors = state.plan.planning_errors if config.web_search.enabled else []
        error_note = f"；规划前网页搜索降级：{errors[0]}" if errors else ""
        yield _make_event("thinking", content=f"已生成全局SOP计划：{step_names}{evidence_note}{error_note}。", step=0, task_id=task_id)

    while state.plan and state.current_plan_step <= len(state.plan.steps):
        step = state.plan.steps[state.current_plan_step - 1]
        step.status = PlanStepStatus.RUNNING
        yield _make_event(
            "progress",
            step=state.current_plan_step,
            max_steps=len(state.plan.steps),
            task_id=task_id,
            phase="execute",
            plan_step=step.name,
            attempt=state.step_attempt,
        )

        if step.key == "code_verification":
            executor = _run_code_verification(config, state, step, task_id, save_checkpoint)
        elif step.key == "final_assembly":
            executor = _run_final_assembly(query, config, client, state, step, task_id)
        else:
            executor = _run_bounded_react_step(query, config, client, state, step, task_id, save_checkpoint)

        outcome: _StepOutcome | None = None
        async for item in executor:
            if isinstance(item, _StepOutcome):
                outcome = item
            else:
                yield item

        if not outcome or outcome.error:
            message = outcome.error if outcome else f"计划步骤「{step.name}」未返回执行结果"
            state.last_step_error = message
            step.status = PlanStepStatus.FAILED
            await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
            yield _make_event("error", message=message, task_id=task_id)
            yield _make_event("done", task_id=task_id)
            return

        if outcome.completed_step:
            step.status = PlanStepStatus.COMPLETED
            state.completed_steps.append(outcome.completed_step)
            state.current_plan_step += 1
            state.step_attempt = 1
            state.local_action_count = 0
            state.current_step_messages = []
            state.last_step_error = ""
            await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
            yield _make_event(
                "thinking",
                content=f"计划步骤「{step.name}」已完成：{outcome.completed_step.summary}",
                step=step.id,
                task_id=task_id,
                plan_step=step.name,
            )

    yield _make_event("done", task_id=task_id)
