"""
Recursive Evidence-Planning Agent 主循环。
全局SOP由后端固定控制，执行中持续进行证据发现、业务确证、递归补搜和规则校准。
"""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from backend.agent.output_parser import ParsedAction, ParsedFinalAnswer, ParsedStepResult, parse_llm_output
from backend.agent.plan_models import AnalysisPlan, CompletedStep, HybridExecutionState, PlanStep, PlanStepStatus
from backend.agent.prompts import (
    get_candidate_expansion_search_prompt,
    get_category_grouping_prompt,
    get_business_confirmation_prompt,
    get_final_assembly_prompt,
    get_planner_prompt,
    get_search_more_query_prompt,
    get_search_query_planner_prompt,
    get_step_react_prompt,
)
from backend.agent.react_loop import (
    _LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
    _LLM_SYNTHESIS_MAX_TOKENS_FLOOR,
    _build_theme_from_json,
    _call_llm,
    _execute_tool,
    _extract_theme_codes,
    _is_fatal_tool_failure,
    _make_event,
    _parse_tool_payload,
    _save_checkpoint,
)
from backend.agent.tools import web_search
from backend.models.analysis_task_models import AnalysisCheckpoint
from backend.models.config_models import AppConfig
from backend.models.theme_models import RejectedStock, Theme
from backend.services.akshare_adapter import format_stock_code, get_stock_list
from backend.services.llm_client import LLMTruncationError, create_client

logger = logging.getLogger(__name__)
_ARCHITECTURE = "plan_execute_react_v1"
_STEP_ATTEMPTS = 3
_FORMAT_REPAIR_ATTEMPTS = 2
_FINAL_ATTEMPTS = 3
_PLANNING_WEB_SEARCH_LIMIT = 6
_PLANNING_WEB_SEARCH_TIMEOUT_SECONDS = 10
_SEARCH_QUERY_PLAN_MAX_TOKENS = _LLM_SYNTHESIS_MAX_TOKENS_FLOOR
_PLANNING_WEB_CONTEXT_CHARS = 1200
_PLANNING_WEB_STOCK_LIMIT = 20
_PLANNING_WEB_ENTRY_LIMIT = 30
_PLANNING_CANDIDATE_TARGET = 18
_PLANNING_SEARCH_MORE_LIMIT = 10
_PLANNING_SEARCH_MORE_CACHE_VERSION = 1
_NEGATIVE_KEYWORDS = ("暂未", "否认", "不构成重大影响", "未采购", "无合作", "未合作", "不涉及", "传闻不实")
_STRONG_SOURCE_DOMAINS = ("cninfo.com.cn", "sse.com.cn", "szse.cn", "static.cninfo.com.cn")
_SECURITIES_SOURCE_DOMAINS = ("stcn.com", "cs.com.cn", "cnstock.com", "证券时报", "中国证券报", "上海证券报")
_SHARED_STOCK_LIST_CACHE = Path(__file__).resolve().parents[2] / "data" / "task_cache" / "_shared" / "stock_list.json"
_CODE_FIELD_NAMES = {"code", "stock_code", "symbol", "股票代码", "证券代码"}
_NAME_FIELD_NAMES = {"name", "stock_name", "股票名称", "股票简称", "证券简称"}
_BUSINESS_CONFIRMATION_BATCH_SIZE = 8
_BUSINESS_SEARCH_RESULT_LIMIT = 3
_BUSINESS_SEARCH_CONTENT_LIMIT = 700
_CANDIDATE_EXPANSION_SEARCH_LIMIT = 6
_SOP_DISPLAY_FLOW = "链路编排 → 线索捕获 → 业务确证 → 递归补搜 → 规则校准 → 主题成图"
_BUSINESS_RELATION_TYPES = {
    "strong_supply_chain",
    "capital_relation",
    "business_cooperation",
    "weak_relevance",
    "rejected",
}
_MARKET_CODE_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)[:：]?\s*(\d{6})\b", re.IGNORECASE)
_SUFFIX_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})\s*[.．]\s*(SH|SZ|BJ)(?![A-Za-z0-9])", re.IGNORECASE)
_DIGIT_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_SEARCH_KEYWORD_SPLIT_PATTERN = re.compile(r"[,，、;；\n\r\t ]+")
_SEARCH_QUERY_ANCHOR_TYPES = {
    "company",
    "brand",
    "product",
    "project",
    "material",
    "industry",
    "concept",
    "person_or_team",
    "unknown",
}
_SEARCH_QUERY_INTENTS = {
    "supply_chain",
    "industry_chain",
    "announcement",
    "business_cooperation",
    "equity_investment",
    "company_identity",
}


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
            name="线索捕获",
            objective="基于用户主题生成搜索规划，执行网页搜索并与本地A股列表比对，产出进入业务确证的候选池。",
            allowed_tools=["web_search"] if web_search_enabled else ["search_stocks"],
            max_actions=_PLANNING_WEB_SEARCH_LIMIT + _PLANNING_SEARCH_MORE_LIMIT,
            required_outputs=["candidate_stocks"],
            hints=search_hints,
        ),
        PlanStep(
            id=2,
            key="business_confirmation",
            name="业务确证",
            objective="对核心候选调用公司业务画像工具，确认主营业务和供应链角色。",
            allowed_tools=business_confirmation_tools,
            max_actions=12,
            required_outputs=["confirmed_stocks"],
        ),
        PlanStep(
            id=3,
            key="candidate_expansion",
            name="递归补搜",
            objective="当业务确证后的最终候选不足目标数量时，执行公告/合作优先的补搜并评分新候选。",
            allowed_tools=business_confirmation_tools,
            max_actions=_CANDIDATE_EXPANSION_SEARCH_LIMIT,
            required_outputs=["expanded_candidates", "confirmed_stocks", "rejected_stocks"],
            hints=category_hints,
        ),
        PlanStep(
            id=4,
            key="category_grouping",
            name="链路编排",
            objective="只基于已确认候选按供应链环节、资本关系和业务合作关系分组，不调用工具。",
            allowed_tools=[],
            max_actions=0,
            required_outputs=["categories"],
            hints=category_hints,
        ),
        PlanStep(
            id=5,
            key="code_verification",
            name="规则校准",
            objective="程序化校验最终候选池一致性，剔除未确认、重复或低分记录。",
            allowed_tools=[],
            max_actions=0,
            required_outputs=["final_candidate_pool", "warnings"],
        ),
        PlanStep(
            id=6,
            key="final_assembly",
            name="主题成图",
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
    planning_candidate: list[dict[str, Any]] | None = None,
    planning_errors: list[str] | None = None,
) -> AnalysisPlan:
    topic_name = str(planner_data.get("topic_name") or query)
    description = str(planner_data.get("description") or f"{query}供应链分析")
    category_hypotheses = [str(item) for item in planner_data.get("category_hypotheses", []) if str(item).strip()]
    candidate = planning_candidate or []
    candidate_terms = [
        str(item.get("name") or item.get("code") or "").strip()
        for item in candidate
        if isinstance(item, dict)
    ]
    fallback_terms = [str(item) for item in planner_data.get("candidate_search_terms", []) if str(item).strip()]
    candidate_search_terms = _dedupe_preserve_order(candidate_terms or fallback_terms)
    if not candidate_search_terms:
        candidate_search_terms = [query]
    return AnalysisPlan(
        query=query,
        topic_name=topic_name,
        description=description,
        candidate_search_terms=candidate_search_terms,
        category_hypotheses=category_hypotheses,
        planning_candidate=candidate,
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


def _split_search_keywords(action_input: str) -> list[str]:
    keywords = [item.strip() for item in _SEARCH_KEYWORD_SPLIT_PATTERN.split(action_input) if item.strip()]
    return keywords or [action_input.strip()]


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
    """构造线索捕获分层检索词：主体/股权/供应链/零部件/负向验证。"""
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
    """线索捕获优先读共享缓存，避免网页证据提取因行情源网络抖动变慢。"""
    try:
        cached = json.loads(_SHARED_STOCK_LIST_CACHE.read_text(encoding="utf-8"))
        if isinstance(cached, list) and cached:
            return [item for item in cached if isinstance(item, dict)]
    except Exception:
        pass
    try:
        return get_stock_list(task_id=task_id)
    except Exception as exc:
        logger.warning("线索捕获加载股票列表失败: %s", exc)
        return []


def _extract_web_stock_terms(entries: list[dict[str, Any]], task_id: str | None) -> list[dict[str, str]]:
    """从网页标题/摘要中提取直接出现的A股名称或代码，作为线索捕获强提示。"""
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
        catalog_name = code_map.get(code, "")
        if not code or code in seen_codes or not catalog_name:
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
            "name": name or catalog_name,
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
    """返回线索捕获网页检索缓存路径；无任务ID时不落盘。"""
    if not task_id:
        return None
    safe_task_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())[:80]
    if not safe_task_id:
        return None
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return Path(__file__).resolve().parents[2] / "data" / "task_cache" / safe_task_id / f"planning_web_{query_hash}.json"


def _search_query_plan_cache_path(query: str, task_id: str | None) -> Path | None:
    """返回LLM搜索规划JSON缓存路径；无任务ID时不落盘。"""
    if not task_id:
        return None
    safe_task_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id).strip())[:80]
    if not safe_task_id:
        return None
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return Path(__file__).resolve().parents[2] / "data" / "task_cache" / safe_task_id / f"planning_query_plan_{query_hash}.json"


def _read_planning_cache(query: str, task_id: str | None) -> dict[str, Any] | None:
    """读取任务级线索捕获检索缓存，避免继续任务时重复调用Tavily。"""
    path = _planning_cache_path(query, task_id)
    if not path:
        return None
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("planning_candidate_source") == "web_search"
                and payload.get("planning_search_more_version") == _PLANNING_SEARCH_MORE_CACHE_VERSION
            ):
                return payload
    except Exception:
        return None
    return None


def _write_planning_cache(query: str, task_id: str | None, payload: dict[str, Any]) -> None:
    """写入任务级线索捕获检索缓存，失败不影响主分析流程。"""
    path = _planning_cache_path(query, task_id)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _read_search_query_plan_cache(query: str, task_id: str | None, max_queries: int) -> dict[str, Any] | None:
    path = _search_query_plan_cache_path(query, task_id)
    if not path:
        return None
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _validate_search_query_plan(payload, query, max_queries)
    except Exception:
        return None
    return None


def _write_search_query_plan_cache(query: str, task_id: str | None, payload: dict[str, Any]) -> None:
    path = _search_query_plan_cache_path(query, task_id)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _intent_from_legacy_group(group: str) -> str:
    if group == "entity_resolve":
        return "company_identity"
    if group == "capital_graph":
        return "equity_investment"
    if group == "negative_check":
        return "announcement"
    return "supply_chain"


def _fallback_search_query_plan(query: str, max_queries: int) -> dict[str, Any]:
    terms = _planning_entity_terms(query)
    anchor = terms[1] if len(terms) > 1 else terms[0] if terms else query.strip()
    search_queries = [
        {
            "query": spec["query"],
            "intent": _intent_from_legacy_group(spec.get("group", "")),
            "priority": index,
        }
        for index, spec in enumerate(_planning_web_query_specs(query)[:max_queries], start=1)
    ]
    return {
        "anchor": anchor or query.strip(),
        "anchor_type": "unknown",
        "search_queries": search_queries,
    }


def _validate_search_query_plan(payload: Any, query: str, max_queries: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("搜索规划必须是JSON对象")
    anchor = str(payload.get("anchor") or "").strip() or query.strip()
    anchor_type = str(payload.get("anchor_type") or "unknown").strip()
    if anchor_type not in _SEARCH_QUERY_ANCHOR_TYPES:
        anchor_type = "unknown"
    raw_queries = payload.get("search_queries")
    if not isinstance(raw_queries, list):
        raise ValueError("search_queries必须是数组")

    seen: set[str] = set()
    search_queries: list[dict[str, Any]] = []
    for item in raw_queries:
        if not isinstance(item, dict):
            continue
        search_query = str(item.get("query") or "").strip()
        if not search_query or search_query in seen:
            continue
        intent = str(item.get("intent") or "supply_chain").strip()
        if intent not in _SEARCH_QUERY_INTENTS:
            intent = "supply_chain"
        try:
            priority = int(item.get("priority") or len(search_queries) + 1)
        except (TypeError, ValueError):
            priority = len(search_queries) + 1
        seen.add(search_query)
        search_queries.append({
            "query": search_query,
            "intent": intent,
            "priority": priority,
        })
        if len(search_queries) >= max_queries:
            break

    if not search_queries:
        raise ValueError("search_queries为空")
    return {
        "anchor": anchor,
        "anchor_type": anchor_type,
        "search_queries": search_queries,
    }


def _topic_from_search_intent(intent: str) -> str:
    if intent in {"announcement", "equity_investment", "company_identity"}:
        return "finance"
    return "general"


def _normalize_search_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "").strip()).lower()


def _query_specs_from_search_query_plan(search_query_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "group": str(item.get("intent") or ""),
            "query": str(item.get("query") or "").strip(),
            "topic": _topic_from_search_intent(str(item.get("intent") or "")),
            "priority": item.get("priority"),
        }
        for item in search_query_plan.get("search_queries", [])
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ]


def _compact_planning_candidate_for_search_more(stock_terms: list[dict[str, Any]]) -> list[dict[str, str]]:
    fields = ("code", "name", "group", "relation_hint", "source_grade", "title", "url")
    compacted: list[dict[str, str]] = []
    for item in stock_terms[:_PLANNING_WEB_STOCK_LIMIT]:
        if not isinstance(item, dict):
            continue
        compacted.append({field: str(item.get(field) or "").strip() for field in fields})
    return compacted


def _fallback_search_more_query_plan(
    anchor: str,
    anchor_type: str,
    used_search_queries: list[dict[str, Any]],
    max_queries: int,
) -> dict[str, Any]:
    used = {
        _normalize_search_query_text(str(item.get("query") or ""))
        for item in used_search_queries
        if isinstance(item, dict)
    }
    templates = [
        ("equity_investment", f"{anchor} 股东 投资方 入股 融资 上市公司"),
        ("equity_investment", f"{anchor} 间接持股 基金 LP 上市公司"),
        ("announcement", f"{anchor} 上市公司 公告 年报 客户 供应商"),
        ("announcement", f"{anchor} 互动易 合作协议 重大合同 A股"),
        ("business_cooperation", f"{anchor} 合作伙伴 战略合作 联合开发 上市公司"),
    ]
    search_queries: list[dict[str, Any]] = []
    for intent, query_text in templates:
        normalized = _normalize_search_query_text(query_text)
        if not query_text.strip() or normalized in used:
            continue
        search_queries.append({
            "query": query_text,
            "intent": intent,
            "priority": len(search_queries) + 1,
        })
        if len(search_queries) >= max_queries:
            break
    return {
        "anchor": anchor,
        "anchor_type": anchor_type if anchor_type in _SEARCH_QUERY_ANCHOR_TYPES else "unknown",
        "search_queries": search_queries,
    }


def _fallback_candidate_expansion_query_plan(
    anchor: str,
    anchor_type: str,
    used_search_queries: list[dict[str, Any]],
    max_queries: int,
) -> dict[str, Any]:
    used = {
        _normalize_search_query_text(str(item.get("query") or ""))
        for item in used_search_queries
        if isinstance(item, dict)
    }
    templates = [
        ("announcement", f"{anchor} 上市公司 公告 年报 互动易 项目合作"),
        ("announcement", f"{anchor} 合作协议 重大合同 供货 量产 A股"),
        ("business_cooperation", f"{anchor} 合作伙伴 战略合作 联合开发 上市公司"),
        ("business_cooperation", f"{anchor} 生态合作 解决方案 认证伙伴 A股"),
        ("equity_investment", f"{anchor} 产业基金 间接持股 上市公司 公告"),
        ("equity_investment", f"{anchor} 投资 入股 参股 有限合伙 A股"),
    ]
    search_queries: list[dict[str, Any]] = []
    for intent, query_text in templates:
        normalized = _normalize_search_query_text(query_text)
        if not query_text.strip() or normalized in used:
            continue
        search_queries.append({
            "query": query_text,
            "intent": intent,
            "priority": len(search_queries) + 1,
        })
        if len(search_queries) >= max_queries:
            break
    return {
        "anchor": anchor,
        "anchor_type": anchor_type if anchor_type in _SEARCH_QUERY_ANCHOR_TYPES else "unknown",
        "search_queries": search_queries,
    }


async def _create_search_query_plan(
    query: str,
    client,
    model: str,
    temperature: float,
    max_queries: int,
    task_id: str | None,
) -> tuple[dict[str, Any], list[str]]:
    cached = _read_search_query_plan_cache(query, task_id, max_queries)
    if cached is not None:
        return cached, []

    messages = [
        {"role": "system", "content": get_search_query_planner_prompt(query, max_queries=max_queries)},
        {"role": "user", "content": "请输出搜索规划JSON。"},
    ]
    errors: list[str] = []
    try:
        output = await _call_llm(
            client,
            model,
            messages,
            temperature,
            _SEARCH_QUERY_PLAN_MAX_TOKENS,
            0,
            idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
        )
        payload = _validate_search_query_plan(json.loads(_strip_json_fence(output)), query, max_queries)
    except Exception as exc:
        errors.append(f"LLM搜索规划失败，已回退旧模板: {exc}")
        payload = _fallback_search_query_plan(query, max_queries)

    _write_search_query_plan_cache(query, task_id, payload)
    return payload, errors


async def _create_search_more_query_plan(
    query: str,
    anchor: str,
    anchor_type: str,
    used_search_queries: list[dict[str, Any]],
    planning_candidate: list[dict[str, Any]],
    missing_count: int,
    client,
    model: str,
    temperature: float,
    max_queries: int,
) -> tuple[dict[str, Any], list[str]]:
    messages = [
        {
            "role": "system",
            "content": get_search_more_query_prompt(
                query,
                anchor,
                anchor_type,
                used_search_queries,
                planning_candidate,
                missing_count,
                max_queries,
            ),
        },
        {"role": "user", "content": "请输出补充搜索规划JSON。"},
    ]
    errors: list[str] = []
    try:
        output = await _call_llm(
            client,
            model,
            messages,
            temperature,
            _SEARCH_QUERY_PLAN_MAX_TOKENS,
            0,
            idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
        )
        payload = _validate_search_query_plan(json.loads(_strip_json_fence(output)), query, max_queries)
        payload["anchor"] = anchor
        payload["anchor_type"] = anchor_type if anchor_type in _SEARCH_QUERY_ANCHOR_TYPES else "unknown"
    except Exception as exc:
        errors.append(f"LLM补充搜索规划失败，已回退补搜模板: {exc}")
        payload = _fallback_search_more_query_plan(anchor, anchor_type, used_search_queries, max_queries)
    return payload, errors


async def _create_candidate_expansion_query_plan(
    query: str,
    anchor: str,
    anchor_type: str,
    target_count: int,
    confirmed_stocks: list[dict[str, Any]],
    rejected_stocks: list[dict[str, Any]],
    planning_candidate: list[dict[str, Any]],
    used_search_queries: list[dict[str, Any]],
    client,
    model: str,
    temperature: float,
    max_queries: int,
) -> tuple[dict[str, Any], list[str]]:
    confirmed_count = len(confirmed_stocks)
    missing_count = max(0, target_count - confirmed_count)
    messages = [
        {
            "role": "system",
            "content": get_candidate_expansion_search_prompt(
                query,
                anchor,
                anchor_type,
                target_count,
                confirmed_count,
                missing_count,
                used_search_queries,
                confirmed_stocks,
                rejected_stocks,
                planning_candidate,
                max_queries,
            ),
        },
        {"role": "user", "content": "请输出递归补搜搜索规划JSON。"},
    ]
    errors: list[str] = []
    try:
        output = await _call_llm(
            client,
            model,
            messages,
            temperature,
            _SEARCH_QUERY_PLAN_MAX_TOKENS,
            0,
            idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
        )
        payload = _validate_search_query_plan(json.loads(_strip_json_fence(output)), query, max_queries)
        payload["anchor"] = anchor
        payload["anchor_type"] = anchor_type if anchor_type in _SEARCH_QUERY_ANCHOR_TYPES else "unknown"
    except Exception as exc:
        errors.append(f"LLM递归补搜搜索规划失败，已回退补全模板: {exc}")
        payload = _fallback_candidate_expansion_query_plan(anchor, anchor_type, used_search_queries, max_queries)
    return payload, errors


def _planning_result(
    queries: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    stock_terms: list[dict[str, str]],
    errors: list[str],
    search_query_plan: dict[str, Any] | None = None,
    search_more_query_plans: list[dict[str, Any]] | None = None,
    search_more_search_count: int = 0,
) -> dict[str, Any]:
    return {
        "queries": queries,
        "entries": entries,
        "stock_terms": stock_terms,
        "errors": errors,
        "search_query_plan": search_query_plan or {},
        "search_more_query_plans": search_more_query_plans or [],
        "search_more_search_count": search_more_search_count,
        "planning_candidate_source": "web_search",
        "planning_search_more_version": _PLANNING_SEARCH_MORE_CACHE_VERSION,
    }


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
    """线索捕获网页搜索使用短超时，失败时降级为非致命错误。"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(web_search, action_input, task_id),
            timeout=_PLANNING_WEB_SEARCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return json.dumps({
            "error": "线索捕获网页搜索超时，已降级继续分析",
            "fatal": False,
            "retryable": False,
            "results": [],
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "error": f"线索捕获网页搜索异常，已降级继续分析: {exc}",
            "fatal": False,
            "retryable": False,
            "results": [],
        }, ensure_ascii=False)


async def _collect_planning_web_context(
    query: str,
    client,
    model: str,
    temperature: float,
    task_id: str | None,
) -> dict[str, Any]:
    """在线索捕获步骤执行网页检索，得到主题边界、搜索证据和直接A股候选。"""
    cached = _read_planning_cache(query, task_id)
    if cached is not None:
        return cached

    search_query_plan, errors = await _create_search_query_plan(
        query,
        client,
        model,
        temperature,
        _PLANNING_WEB_SEARCH_LIMIT,
        task_id,
    )
    query_specs = _query_specs_from_search_query_plan(search_query_plan)
    used_search_queries = [
        {
            "query": spec["query"],
            "intent": spec.get("group", ""),
            "priority": spec.get("priority"),
            "phase": "initial",
        }
        for spec in query_specs
    ]
    used_query_texts = {_normalize_search_query_text(spec["query"]) for spec in query_specs}
    entries: list[dict[str, Any]] = []
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
            error_message = f"线索捕获网页检索超时或异常: {exc}"
            errors.append(error_message)
            logger.warning("线索捕获网页检索异常 [%s]: %s", search_query, exc)
            continue
        payload = _parse_tool_payload(result)
        if not payload or payload.get("error"):
            error_message = str(payload.get("error") if payload else "非JSON")
            errors.append(error_message)
            logger.info("线索捕获网页检索不可用 [%s]: %s", search_query, error_message)
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
    search_more_query_plans: list[dict[str, Any]] = []
    search_more_search_count = 0
    anchor = str(search_query_plan.get("anchor") or query).strip() or query
    anchor_type = str(search_query_plan.get("anchor_type") or "unknown").strip()
    if anchor_type not in _SEARCH_QUERY_ANCHOR_TYPES:
        anchor_type = "unknown"

    stop_search_more = any("TAVILY_API_KEY" in str(error) for error in errors)
    while (
        len(stock_terms) < _PLANNING_CANDIDATE_TARGET
        and search_more_search_count < _PLANNING_SEARCH_MORE_LIMIT
        and not stop_search_more
    ):
        missing_count = _PLANNING_CANDIDATE_TARGET - len(stock_terms)
        remaining_search_count = _PLANNING_SEARCH_MORE_LIMIT - search_more_search_count
        max_more_queries = max(1, min(missing_count, remaining_search_count))
        planning_candidate_snapshot = _compact_planning_candidate_for_search_more(stock_terms)
        search_more_plan, search_more_errors = await _create_search_more_query_plan(
            query,
            anchor,
            anchor_type,
            used_search_queries,
            planning_candidate_snapshot,
            missing_count,
            client,
            model,
            temperature,
            max_more_queries,
        )
        errors.extend(search_more_errors)
        raw_more_specs = _query_specs_from_search_query_plan(search_more_plan)
        more_specs: list[dict[str, Any]] = []
        for spec in raw_more_specs:
            normalized = _normalize_search_query_text(spec["query"])
            if not normalized or normalized in used_query_texts:
                continue
            used_query_texts.add(normalized)
            more_specs.append(spec)
            if len(more_specs) >= max_more_queries:
                break
        if not more_specs:
            errors.append("补充搜索规划未产生新的可执行query，已停止补搜")
            break

        executed_specs: list[dict[str, Any]] = []
        for spec in more_specs:
            if search_more_search_count >= _PLANNING_SEARCH_MORE_LIMIT:
                break
            search_query = spec["query"]
            used_search_queries.append({
                "query": search_query,
                "intent": spec.get("group", ""),
                "priority": spec.get("priority"),
                "phase": "search_more",
            })
            executed_specs.append(spec)
            query_specs.append(spec)
            search_more_search_count += 1
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
                error_message = f"线索捕获补充网页检索超时或异常: {exc}"
                errors.append(error_message)
                logger.warning("线索捕获补充网页检索异常 [%s]: %s", search_query, exc)
                continue
            payload = _parse_tool_payload(result)
            if not payload or payload.get("error"):
                error_message = str(payload.get("error") if payload else "非JSON")
                errors.append(error_message)
                logger.info("线索捕获补充网页检索不可用 [%s]: %s", search_query, error_message)
                if "TAVILY_API_KEY" in error_message:
                    stop_search_more = True
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
            if len(stock_terms) >= _PLANNING_CANDIDATE_TARGET:
                break

        search_more_query_plans.append({
            **search_more_plan,
            "missing_count": missing_count,
            "max_queries": max_more_queries,
            "executed_search_queries": executed_specs,
            "candidate_count_after": len(stock_terms),
        })
        if not executed_specs:
            break

    payload = _planning_result(
        query_specs,
        entries,
        stock_terms,
        errors,
        search_query_plan,
        search_more_query_plans,
        search_more_search_count,
    )
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
    messages = [
        {"role": "system", "content": get_planner_prompt(query)},
        {"role": "user", "content": "请输出规划JSON。"},
    ]
    # 规划同为纯合成步骤，需输出主题元信息和8-15个分类；思考型模型推理链会额外吃预算，
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
    )


def _candidate_stock_from_planning_candidate(item: dict[str, Any]) -> dict[str, Any] | None:
    code = _normalize_stock_code(str(item.get("code") or ""))
    name = str(item.get("name") or "").strip()
    if not code or not name:
        return None
    return {
        "code": code,
        "name": name,
        "search_term": name,
        "source": str(item.get("source") or "").strip(),
        "group": str(item.get("group") or "").strip(),
        "relation_hint": str(item.get("relation_hint") or "").strip(),
        "source_grade": str(item.get("source_grade") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "title": str(item.get("title") or "").strip(),
    }


def _stock_catalog_by_code(task_id: str | None) -> dict[str, str]:
    """返回本地A股股票库映射，仅保留代码和名称都存在的记录。"""
    return {
        str(item.get("code")): str(item.get("name"))
        for item in _load_stock_list_for_planning(task_id=task_id)
        if isinstance(item, dict) and item.get("code") and item.get("name")
    }


def _planning_candidate_stocks(state: HybridExecutionState) -> list[dict[str, Any]]:
    seen_codes: set[str] = set()
    candidate_stocks: list[dict[str, Any]] = []
    for item in state.plan.planning_candidate if state.plan else []:
        if not isinstance(item, dict):
            continue
        stock = _candidate_stock_from_planning_candidate(item)
        if not stock or stock["code"] in seen_codes:
            continue
        seen_codes.add(stock["code"])
        candidate_stocks.append(stock)
    return candidate_stocks


def _candidate_stocks_for_business_confirmation(state: HybridExecutionState) -> list[dict[str, Any]]:
    for item in state.completed_steps:
        if item.key != "candidate_discovery":
            continue
        candidate_stocks = (item.data or {}).get("candidate_stocks")
        if isinstance(candidate_stocks, list):
            seen_codes: set[str] = set()
            stocks: list[dict[str, Any]] = []
            for stock in candidate_stocks:
                if not isinstance(stock, dict):
                    continue
                code = _stock_code_from_record(stock)
                name = str(stock.get("name") or "").strip()
                if not code or not name or code in seen_codes:
                    continue
                seen_codes.add(code)
                stocks.append({**stock, "code": code, "name": name})
            if stocks:
                return stocks
    return []


def _business_confirmation_anchor(query: str, state: HybridExecutionState) -> str:
    terms = _planning_entity_terms(query)
    if len(terms) > 1:
        return terms[1]
    if terms:
        return terms[0]
    return (state.plan.topic_name if state.plan else "") or query


def _business_search_query(name: str, anchor: str, group: str, relation_hint: str) -> str:
    relation_text = f"{group} {relation_hint}".lower()
    if "equity" in relation_text or "capital" in relation_text or "investment" in relation_text:
        return f"{name} {anchor} 投资 入股 参股 持股 基金 LP 公告"
    if "cooperation" in relation_text or "partnership" in relation_text:
        return f"{name} {anchor} 合作伙伴 战略合作 联合开发 项目 供货 公告"
    if "announcement" in relation_text:
        return f"{name} {anchor} 年报 公告 互动易 客户 供应商 采购 销售"
    return f"{name} {anchor} 主营业务 供应商 客户 合作 供货 项目 公告"


def _compact_business_search_results(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload or payload.get("error"):
        return []
    results: list[dict[str, Any]] = []
    for item in payload.get("results", [])[:_BUSINESS_SEARCH_RESULT_LIMIT]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("raw_content") or "").strip().replace("\n", " ")
        if len(content) > _BUSINESS_SEARCH_CONTENT_LIMIT:
            content = content[:_BUSINESS_SEARCH_CONTENT_LIMIT] + "..."
        results.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "content": content,
            "score": item.get("score"),
        })
    return results


def _score_to_confirmation_level(score: int) -> str:
    if score >= 85:
        return "strong_confirmed"
    if score >= 70:
        return "confirmed"
    if score >= 40:
        return "weak_confirmed"
    return "rejected"


def _clean_relation_type(value: Any, score: int) -> str:
    relation_type = str(value or "").strip()
    if relation_type in _BUSINESS_RELATION_TYPES:
        return relation_type
    if score >= 85:
        return "strong_supply_chain"
    if score >= 70:
        return "capital_relation"
    if score >= 55:
        return "business_cooperation"
    if score >= 40:
        return "weak_relevance"
    return "rejected"


def _clean_relation_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def _normalize_business_confirmation_payload(
    payload: Any,
    batch_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("业务确证结果必须是JSON对象")
    candidates_by_code = {item["code"]: item for item in batch_candidates}
    seen_codes: set[str] = set()
    confirmed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in payload.get("confirmed_stocks", []):
        if not isinstance(raw, dict):
            continue
        code = _normalize_stock_code(str(raw.get("code") or "")) or ""
        if code not in candidates_by_code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidate = candidates_by_code[code]
        score = _clean_relation_score(raw.get("relation_score"))
        record = {
            "code": code,
            "name": str(raw.get("name") or candidate.get("name") or "").strip(),
            "relation_score": score,
            "percentage": score,
            "confirmation_level": _score_to_confirmation_level(score),
            "relation_type": _clean_relation_type(raw.get("relation_type"), score),
            "business_summary": str(raw.get("business_summary") or "").strip(),
            "relation_evidence": str(raw.get("relation_evidence") or raw.get("evidence") or "").strip(),
            "evidence_url": str(raw.get("evidence_url") or "").strip(),
            "negative_evidence": str(raw.get("negative_evidence") or "").strip(),
            "confidence_reason": str(raw.get("confidence_reason") or "").strip(),
            "source_phase": str(raw.get("source_phase") or candidate.get("source_phase") or "business_confirmation").strip(),
        }
        if score >= 40:
            confirmed.append(record)
        else:
            rejected.append({
                "code": code,
                "name": record["name"],
                "relation_score": score,
                "relation_type": "rejected",
                "reason": record["confidence_reason"] or record["negative_evidence"] or "关联评分低于40，未进入看板",
                "evidence_url": record["evidence_url"],
            })

    for raw in payload.get("rejected_stocks", []):
        if not isinstance(raw, dict):
            continue
        code = _normalize_stock_code(str(raw.get("code") or "")) or ""
        if code not in candidates_by_code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidate = candidates_by_code[code]
        score = _clean_relation_score(raw.get("relation_score"))
        if score >= 40:
            confirmed.append({
                "code": code,
                "name": str(raw.get("name") or candidate.get("name") or "").strip(),
                "relation_score": score,
                "percentage": score,
                "confirmation_level": _score_to_confirmation_level(score),
                "relation_type": _clean_relation_type(raw.get("relation_type"), score),
                "business_summary": "",
                "relation_evidence": str(raw.get("reason") or "").strip(),
                "evidence_url": str(raw.get("evidence_url") or "").strip(),
                "negative_evidence": "",
                "confidence_reason": str(raw.get("reason") or "").strip(),
                "source_phase": str(raw.get("source_phase") or candidate.get("source_phase") or "business_confirmation").strip(),
            })
        else:
            rejected.append({
                "code": code,
                "name": str(raw.get("name") or candidate.get("name") or "").strip(),
                "relation_score": score,
                "relation_type": "rejected",
                "reason": str(raw.get("reason") or "模型判定业务关联不足").strip(),
                "evidence_url": str(raw.get("evidence_url") or "").strip(),
            })

    for code, candidate in candidates_by_code.items():
        if code in seen_codes:
            continue
        rejected.append({
            "code": code,
            "name": str(candidate.get("name") or code).strip(),
            "relation_score": 0,
            "relation_type": "rejected",
            "reason": "业务确证模型未返回该候选评分，按不确认处理",
            "evidence_url": "",
        })

    return {
        "summary": str(payload.get("summary") or "").strip(),
        "confirmed_stocks": confirmed,
        "rejected_stocks": rejected,
    }


async def _score_business_confirmation_batch(
    query: str,
    anchor: str,
    candidate_context: list[dict[str, Any]],
    client,
    model: str,
    temperature: float,
    max_tokens: int,
    step_id: int,
    source_phase: str = "business_confirmation",
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": get_business_confirmation_prompt(query, anchor, candidate_context, source_phase=source_phase)},
        {"role": "user", "content": "请输出业务确证评分JSON。"},
    ]
    last_error = ""
    for attempt in range(1, _STEP_ATTEMPTS + 1):
        try:
            output = await _call_llm(
                client,
                model,
                messages,
                temperature,
                max(max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR),
                step_id,
                idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
            )
            payload = json.loads(_strip_json_fence(output))
            return _normalize_business_confirmation_payload(payload, candidate_context)
        except Exception as exc:
            last_error = str(exc)
            messages.extend([
                {"role": "assistant", "content": output if "output" in locals() else ""},
                {"role": "user", "content": f"上一轮业务确证评分JSON无效：{exc}。请只输出严格JSON，并确保本批所有候选都在 confirmed_stocks 或 rejected_stocks 中出现。"},
            ])
    raise ValueError(f"业务确证评分连续失败：{last_error}")


async def _run_business_confirmation(
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
    max_tokens = config.settings.max_tokens
    candidates = _candidate_stocks_for_business_confirmation(state)
    if not candidates:
        yield _StepOutcome(error="业务确证缺少线索捕获输出 candidate_stocks")
        return

    anchor = _business_confirmation_anchor(query, state)
    yield _make_event(
        "thinking",
        content=f"业务确证开始：将为{len(candidates)}只候选批量补充公司业务画像，并逐只搜索与「{anchor}」的业务关联证据。",
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )

    candidate_context: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        name = candidate["name"]
        info_action = ParsedAction(thought="批量补充候选公司业务画像。", action="get_company_info", action_input=code)
        yield _make_event("tool_call", tool=info_action.action, input=info_action.action_input, step=step.id, task_id=task_id, plan_step=step.name)
        info_result = await _execute_tool(info_action, task_id=task_id)
        yield _make_event("tool_result", tool=info_action.action, output=info_result, step=step.id, task_id=task_id, plan_step=step.name)
        info_payload = _parse_tool_payload(info_result) or {}
        observations.append({"tool": info_action.action, "input": info_action.action_input, "output": info_payload or info_result})

        business_results: list[dict[str, Any]] = []
        business_query = _business_search_query(
            name,
            anchor,
            str(candidate.get("group") or ""),
            str(candidate.get("relation_hint") or ""),
        )
        if config.web_search.enabled:
            action_input = json.dumps({
                "query": business_query,
                "search_depth": "basic",
                "max_results": _BUSINESS_SEARCH_RESULT_LIMIT,
                "topic": "finance",
                "include_raw_content": False,
                "chunks_per_source": 1,
            }, ensure_ascii=False)
            search_action = ParsedAction(thought="逐只补充候选公司与主题的业务关系证据。", action="web_search", action_input=action_input)
            yield _make_event("tool_call", tool=search_action.action, input=business_query, step=step.id, task_id=task_id, plan_step=step.name)
            search_result = await _execute_tool(search_action, task_id=task_id)
            yield _make_event("tool_result", tool=search_action.action, output=search_result, step=step.id, task_id=task_id, plan_step=step.name)
            search_payload = _parse_tool_payload(search_result) or {}
            observations.append({"tool": search_action.action, "input": business_query, "output": search_payload or search_result})
            business_results = _compact_business_search_results(search_payload)

        candidate_context.append({
            "code": code,
            "name": name,
            "source_phase": str(candidate.get("source_phase") or "business_confirmation"),
            "business_profile": (
                info_payload.get("business_profile") or info_payload.get("info") or {}
                if isinstance(info_payload, dict)
                else {}
            ),
            "candidate_evidence": {
                "group": str(candidate.get("group") or ""),
                "relation_hint": str(candidate.get("relation_hint") or ""),
                "source_grade": str(candidate.get("source_grade") or ""),
                "title": str(candidate.get("title") or ""),
                "url": str(candidate.get("url") or ""),
                "source": str(candidate.get("source") or ""),
            },
            "business_search_query": business_query,
            "business_search_results": business_results,
        })
        if index % 5 == 0 or index == len(candidates):
            yield _make_event(
                "thinking",
                content=f"业务确证材料收集进度：{index}/{len(candidates)}。",
                step=step.id,
                task_id=task_id,
                plan_step=step.name,
            )

    confirmed_stocks: list[dict[str, Any]] = []
    rejected_stocks: list[dict[str, Any]] = []
    summaries: list[str] = []
    for start in range(0, len(candidate_context), _BUSINESS_CONFIRMATION_BATCH_SIZE):
        batch = candidate_context[start:start + _BUSINESS_CONFIRMATION_BATCH_SIZE]
        batch_index = start // _BUSINESS_CONFIRMATION_BATCH_SIZE + 1
        yield _make_event(
            "thinking",
            content=f"业务确证评分：正在由模型评估第{batch_index}批{len(batch)}只候选。",
            step=step.id,
            task_id=task_id,
            plan_step=step.name,
        )
        batch_result = await _score_business_confirmation_batch(
            query,
            anchor,
            batch,
            client,
            model,
            temperature,
            max_tokens,
            step.id,
        )
        summaries.append(batch_result.get("summary") or "")
        confirmed_stocks.extend(batch_result["confirmed_stocks"])
        rejected_stocks.extend(batch_result["rejected_stocks"])

    confirmed_stocks = sorted(confirmed_stocks, key=lambda item: (-int(item.get("relation_score") or 0), item.get("name", ""), item.get("code", "")))
    rejected_stocks = sorted(rejected_stocks, key=lambda item: (int(item.get("relation_score") or 0), item.get("name", ""), item.get("code", "")))
    summary = (
        f"业务确证完成：{len(confirmed_stocks)}只候选评分>=40进入看板，"
        f"{len(rejected_stocks)}只候选评分<40进入未收录名单。"
    )
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=summary,
        data={
            "summary": summary,
            "anchor": anchor,
            "confirmed_stocks": confirmed_stocks,
            "rejected_stocks": rejected_stocks,
            "candidate_business_context": candidate_context,
            "batch_summaries": [item for item in summaries if item],
        },
        observations=observations,
    )
    await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
    yield _StepOutcome(completed_step=completed)


async def _run_candidate_expansion(
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
    max_tokens = config.settings.max_tokens
    anchor = _business_confirmation_anchor(query, state)
    planning_cache = _read_planning_cache(query, task_id) or {}
    search_query_plan = planning_cache.get("search_query_plan") if isinstance(planning_cache, dict) else {}
    anchor_type = str((search_query_plan or {}).get("anchor_type") or "unknown")
    if anchor_type not in _SEARCH_QUERY_ANCHOR_TYPES:
        anchor_type = "unknown"

    confirmed_stocks = _confirmed_stocks_for_pipeline(state)
    rejected_stocks = _rejected_stocks_for_pipeline(state)
    missing_count = max(0, _PLANNING_CANDIDATE_TARGET - len(confirmed_stocks))
    if missing_count <= 0:
        summary = f"递归补搜跳过：业务确证后已有{len(confirmed_stocks)}只确认候选，已达到目标{_PLANNING_CANDIDATE_TARGET}只。"
        completed = CompletedStep(
            step_id=step.id,
            key=step.key,
            name=step.name,
            summary=summary,
            data={
                "summary": summary,
                "expanded_candidates": [],
                "confirmed_stocks": [],
                "rejected_stocks": [],
                "warnings": [],
            },
        )
        yield _StepOutcome(completed_step=completed)
        return

    if not config.web_search.enabled:
        warning = "网页搜索未启用，递归补搜无法追加新候选。"
        completed = CompletedStep(
            step_id=step.id,
            key=step.key,
            name=step.name,
            summary=f"递归补搜未执行：{warning}",
            data={
                "summary": f"递归补搜未执行：{warning}",
                "expanded_candidates": [],
                "confirmed_stocks": [],
                "rejected_stocks": [],
                "warnings": [warning],
            },
        )
        yield _StepOutcome(completed_step=completed)
        return

    max_queries = min(missing_count, _CANDIDATE_EXPANSION_SEARCH_LIMIT)
    used_search_queries = _used_web_search_queries(state, query, task_id)
    search_plan, planning_errors = await _create_candidate_expansion_query_plan(
        query,
        anchor,
        anchor_type,
        _PLANNING_CANDIDATE_TARGET,
        confirmed_stocks,
        rejected_stocks,
        state.plan.planning_candidate if state.plan else [],
        used_search_queries,
        client,
        model,
        temperature,
        max_queries,
    )
    query_specs = _query_specs_from_search_query_plan(search_plan)
    query_specs = [
        spec for spec in query_specs
        if spec.get("group") in {"announcement", "business_cooperation", "equity_investment"}
    ][:max_queries]

    yield _make_event(
        "thinking",
        content=f"递归补搜开始：当前确认{len(confirmed_stocks)}只，缺口{missing_count}只，本轮最多执行{len(query_specs)}次补搜搜索。",
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )

    entries: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for spec in query_specs:
        search_query = spec["query"]
        action_input = json.dumps({
            "query": search_query,
            "search_depth": "basic",
            "max_results": 5,
            "topic": spec.get("topic", "finance"),
            "include_raw_content": False,
            "chunks_per_source": 1,
        }, ensure_ascii=False)
        yield _make_event("tool_call", tool="web_search", input=search_query, step=step.id, task_id=task_id, plan_step=step.name)
        result = await _execute_planning_web_search(action_input, task_id=task_id)
        yield _make_event("tool_result", tool="web_search", output=result, step=step.id, task_id=task_id, plan_step=step.name)
        payload = _parse_tool_payload(result)
        observations.append({"tool": "web_search", "input": search_query, "output": payload or result})
        if not payload or payload.get("error"):
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
    stock_catalog = _stock_catalog_by_code(task_id=task_id)
    existing_codes = {
        code
        for record in [*confirmed_stocks, *rejected_stocks]
        if isinstance(record, dict)
        for code in [_stock_code_from_record(record)]
        if code
    }
    expanded_candidates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for item in stock_terms:
        stock = _candidate_stock_from_planning_candidate(item) if isinstance(item, dict) else None
        if not stock or stock["code"] in existing_codes or stock["code"] in seen_codes:
            continue
        catalog_name = stock_catalog.get(stock["code"], "")
        if not catalog_name:
            continue
        stock["name"] = catalog_name
        seen_codes.add(stock["code"])
        expanded_candidates.append({**stock, "source_phase": "candidate_expansion"})
        if len(expanded_candidates) >= missing_count:
            break

    if not expanded_candidates:
        warning = "递归补搜未命中新的A股候选。"
        summary = f"递归补搜完成：{warning}"
        completed = CompletedStep(
            step_id=step.id,
            key=step.key,
            name=step.name,
            summary=summary,
            data={
                "summary": summary,
                "expanded_candidates": [],
                "confirmed_stocks": [],
                "rejected_stocks": [],
                "search_query_plan": search_plan,
                "warnings": [*planning_errors, warning],
            },
            observations=observations,
        )
        yield _StepOutcome(completed_step=completed)
        return

    candidate_context: list[dict[str, Any]] = []
    business_observations: list[dict[str, Any]] = []
    for index, candidate in enumerate(expanded_candidates, start=1):
        code = candidate["code"]
        name = candidate["name"]
        info_action = ParsedAction(thought="补全候选公司业务画像。", action="get_company_info", action_input=code)
        yield _make_event("tool_call", tool=info_action.action, input=code, step=step.id, task_id=task_id, plan_step=step.name)
        info_result = await _execute_tool(info_action, task_id=task_id)
        yield _make_event("tool_result", tool=info_action.action, output=info_result, step=step.id, task_id=task_id, plan_step=step.name)
        info_payload = _parse_tool_payload(info_result) or {}
        business_observations.append({"tool": info_action.action, "input": code, "output": info_payload or info_result})

        business_query = _business_search_query(
            name,
            anchor,
            str(candidate.get("group") or ""),
            str(candidate.get("relation_hint") or ""),
        )
        action_input = json.dumps({
            "query": business_query,
            "search_depth": "basic",
            "max_results": _BUSINESS_SEARCH_RESULT_LIMIT,
            "topic": "finance",
            "include_raw_content": False,
            "chunks_per_source": 1,
        }, ensure_ascii=False)
        search_action = ParsedAction(thought="补充候选与主题的业务关系证据。", action="web_search", action_input=action_input)
        yield _make_event("tool_call", tool=search_action.action, input=business_query, step=step.id, task_id=task_id, plan_step=step.name)
        search_result = await _execute_tool(search_action, task_id=task_id)
        yield _make_event("tool_result", tool=search_action.action, output=search_result, step=step.id, task_id=task_id, plan_step=step.name)
        search_payload = _parse_tool_payload(search_result) or {}
        business_observations.append({"tool": search_action.action, "input": business_query, "output": search_payload or search_result})

        candidate_context.append({
            "code": code,
            "name": name,
            "source_phase": "candidate_expansion",
            "business_profile": (
                info_payload.get("business_profile") or info_payload.get("info") or {}
                if isinstance(info_payload, dict)
                else {}
            ),
            "candidate_evidence": {
                "group": str(candidate.get("group") or ""),
                "relation_hint": str(candidate.get("relation_hint") or ""),
                "source_grade": str(candidate.get("source_grade") or ""),
                "title": str(candidate.get("title") or ""),
                "url": str(candidate.get("url") or ""),
                "source": str(candidate.get("source") or ""),
            },
            "business_search_query": business_query,
            "business_search_results": _compact_business_search_results(search_payload),
        })
        if index % 5 == 0 or index == len(expanded_candidates):
            yield _make_event(
                "thinking",
                content=f"递归补搜业务材料收集进度：{index}/{len(expanded_candidates)}。",
                step=step.id,
                task_id=task_id,
                plan_step=step.name,
            )

    confirmed_new: list[dict[str, Any]] = []
    rejected_new: list[dict[str, Any]] = []
    summaries: list[str] = []
    for start in range(0, len(candidate_context), _BUSINESS_CONFIRMATION_BATCH_SIZE):
        batch = candidate_context[start:start + _BUSINESS_CONFIRMATION_BATCH_SIZE]
        batch_result = await _score_business_confirmation_batch(
            query,
            anchor,
            batch,
            client,
            model,
            temperature,
            max_tokens,
            step.id,
            source_phase="candidate_expansion",
        )
        summaries.append(batch_result.get("summary") or "")
        confirmed_new.extend(batch_result["confirmed_stocks"])
        rejected_new.extend(batch_result["rejected_stocks"])

    confirmed_new = sorted(confirmed_new, key=lambda item: (-_clean_relation_score(item.get("relation_score")), item.get("name", ""), item.get("code", "")))
    rejected_new = sorted(rejected_new, key=lambda item: (_clean_relation_score(item.get("relation_score")), item.get("name", ""), item.get("code", "")))
    summary = (
        f"递归补搜完成：补搜命中{len(expanded_candidates)}只新A股候选，"
        f"业务评分后{len(confirmed_new)}只进入看板，{len(rejected_new)}只进入未收录名单。"
    )
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=summary,
        data={
            "summary": summary,
            "expanded_candidates": expanded_candidates,
            "confirmed_stocks": confirmed_new,
            "rejected_stocks": rejected_new,
            "candidate_business_context": candidate_context,
            "search_query_plan": search_plan,
            "batch_summaries": [item for item in summaries if item],
            "warnings": planning_errors,
        },
        observations=[*observations, *business_observations],
    )
    await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
    yield _StepOutcome(completed_step=completed)


async def _run_candidate_discovery_from_planning_candidate(
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    """已有网页候选时，直接完成线索捕获，避免重复搜索。"""
    planning_candidate_count = len(state.plan.planning_candidate) if state.plan else 0
    candidate_stocks = _planning_candidate_stocks(state)

    if not candidate_stocks:
        yield _StepOutcome(error="线索捕获缺少可用的网页A股候选")
        return

    summary = (
        f"线索捕获由已缓存网页候选直通完成，网页命中{planning_candidate_count}条A股候选，"
        f"去重后输出{len(candidate_stocks)}只A股候选；"
        "这些候选已通过web_search结果与本地A股列表比对命中。"
    )
    yield _make_event(
        "thinking",
        content=summary,
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=summary,
        data={
            "summary": summary,
            "candidate_stocks": candidate_stocks,
            "source": "planning_candidate",
            "target_count": _PLANNING_CANDIDATE_TARGET,
            "planning_candidate_count": planning_candidate_count,
        },
        observations=[],
    )
    yield _StepOutcome(completed_step=completed)


def _apply_candidate_discovery_context_to_plan(state: HybridExecutionState, context: dict[str, Any]) -> None:
    if not state.plan:
        return
    stock_terms = [item for item in context.get("stock_terms", []) if isinstance(item, dict)]
    state.plan.planning_candidate = stock_terms
    state.plan.planning_errors = [str(item) for item in context.get("errors", []) if str(item).strip()]
    candidate_terms = [
        str(item.get("name") or item.get("code") or "").strip()
        for item in stock_terms
        if isinstance(item, dict)
    ]
    if candidate_terms:
        state.plan.candidate_search_terms = _dedupe_preserve_order(candidate_terms)
        for plan_step in state.plan.steps:
            if plan_step.key == "candidate_discovery":
                plan_step.hints = state.plan.candidate_search_terms
                break


async def _run_candidate_discovery(
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
    max_tokens = config.settings.max_tokens

    if state.plan and state.plan.planning_candidate:
        async for item in _run_candidate_discovery_from_planning_candidate(state, step, task_id):
            yield item
        return

    if not config.web_search.enabled:
        async for item in _run_bounded_react_step(query, config, client, state, step, task_id, save_checkpoint):
            yield item
        return

    yield _make_event(
        "thinking",
        content=(
            "线索捕获开始：正在让模型生成搜索query，随后执行web_search，"
            "并用本地A股列表比对网页结果中的股票命中。"
        ),
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )

    context = await _collect_planning_web_context(
        query,
        client,
        model,
        temperature,
        task_id=task_id,
    )
    _apply_candidate_discovery_context_to_plan(state, context)
    candidate_stocks = _planning_candidate_stocks(state)
    errors = [str(item) for item in context.get("errors", []) if str(item).strip()]
    search_query_plan = context.get("search_query_plan") if isinstance(context, dict) else {}
    query_count = len(context.get("queries", [])) if isinstance(context.get("queries"), list) else 0
    search_more_count = int(context.get("search_more_search_count") or 0) if isinstance(context, dict) else 0
    candidate_count = len(state.plan.planning_candidate) if state.plan else 0

    if not candidate_stocks:
        error_suffix = f"；错误：{errors[0]}" if errors else ""
        yield _StepOutcome(error=f"线索捕获未命中可用A股候选{error_suffix}")
        return

    summary = (
        f"线索捕获完成：执行{query_count}条搜索query"
        f"（其中补充搜索{search_more_count}次），网页命中{candidate_count}条A股候选，"
        f"去重后输出{len(candidate_stocks)}只候选进入业务确证。"
    )
    if len(candidate_stocks) < _PLANNING_CANDIDATE_TARGET:
        summary += f" 当前候选少于目标{_PLANNING_CANDIDATE_TARGET}只，后续递归补搜环节会继续查漏。"
    yield _make_event(
        "thinking",
        content=summary,
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=summary,
        data={
            "summary": summary,
            "candidate_stocks": candidate_stocks,
            "source": "candidate_discovery_web_search",
            "target_count": _PLANNING_CANDIDATE_TARGET,
            "planning_candidate_count": candidate_count,
            "search_query_plan": search_query_plan,
            "search_queries": context.get("queries", []),
            "search_more_query_plans": context.get("search_more_query_plans", []),
            "search_more_search_count": search_more_count,
            "web_result_count": len(context.get("entries", [])) if isinstance(context.get("entries"), list) else 0,
            "errors": errors,
        },
        observations=[],
    )
    await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
    yield _StepOutcome(completed_step=completed)


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
    max_tokens = config.settings.max_tokens
    observations: list[dict[str, Any]] = []

    for attempt in range(state.step_attempt, _STEP_ATTEMPTS + 1):
        state.step_attempt = attempt
        state.local_action_count = 0
        if not state.current_step_messages:
            completed_steps_for_prompt = _compact_completed_steps_for_prompt(state)
            prompt_content = get_step_react_prompt(
                query,
                state.plan.model_dump() if state.plan else {},
                step.model_dump(),
                completed_steps_for_prompt,
                attempt,
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
        while local_turn_count < max_local_turns:
            local_turn_count += 1
            llm_output = ""
            parsed = None
            # 标记本轮是否因输出被max_tokens截断而需要抬高预算后原地重试（区别于格式修复与致命失败）。
            truncation_retry = False
            repair_messages = [dict(item) for item in state.current_step_messages]
            for repair_index in range(_FORMAT_REPAIR_ATTEMPTS + 1):
                try:
                    llm_output = await _call_llm(
                        client, model, repair_messages, temperature, max_tokens, step.id,
                    )
                except LLMTruncationError as exc:
                    # 中间步骤输出被max_tokens截断：与主题成图不同，这里重试有意义——
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
                    has_search_action = any(observation.get("tool") == "search_stocks" for observation in observations)
                    if step.key == "candidate_discovery" and not has_search_action:
                        raise ValueError("线索捕获必须先实际调用 search_stocks，再输出 Step Result")
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
    confirmed_map, rejected_stocks = _business_confirmation_maps(state)
    if not confirmed_map:
        yield _StepOutcome(error="最终候选池校验缺少 confirmed_stocks")
        return

    category_items = _grouping_category_items_from_grouping_step(state)
    if not category_items:
        yield _StepOutcome(error="规则校准缺少链路编排 categories")
        return

    warnings: list[str] = []
    seen_codes: set[str] = set()
    final_candidate_pool: list[dict[str, Any]] = []
    final_categories: list[dict[str, Any]] = []

    for index, (category_name, records) in enumerate(category_items, start=1):
        stocks: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            code = _stock_code_from_record(record)
            if not code:
                warnings.append(f"分类 {category_name} 中存在无法识别代码的记录，已忽略。")
                continue
            business_record = confirmed_map.get(code)
            if not business_record:
                warnings.append(f"{code} 未在 confirmed_stocks 中，已从最终候选池剔除。")
                continue
            if code in seen_codes:
                warnings.append(f"{code} 在多个分类重复出现，仅保留首次分类。")
                continue
            seen_codes.add(code)
            score = _clean_relation_score(business_record.get("relation_score"))
            if score < 40:
                warnings.append(f"{code} relation_score 低于40，已剔除。")
                continue
            stock_item = _stock_item_from_business_record(business_record, category_name)
            stocks.append(stock_item)
            final_candidate_pool.append({
                **business_record,
                "code": code,
                "percentage": score,
                "category_tag": category_name,
            })
        if stocks:
            stocks.sort(key=lambda item: (-int(item.get("percentage") or 0), item.get("name", ""), item.get("code", "")))
            final_categories.append({
                "id": _category_id_from_name(category_name, len(final_categories) + 1),
                "name": category_name,
                "order": len(final_categories) + 1,
                "stocks": stocks,
            })

    missing_codes = sorted(set(confirmed_map) - seen_codes)
    if missing_codes:
        category_name = "未分组候选"
        stocks = []
        for code in missing_codes:
            business_record = confirmed_map[code]
            score = _clean_relation_score(business_record.get("relation_score"))
            if score < 40:
                continue
            stock_item = _stock_item_from_business_record(business_record, category_name)
            stocks.append(stock_item)
            final_candidate_pool.append({
                **business_record,
                "code": code,
                "percentage": score,
                "category_tag": category_name,
            })
        if stocks:
            warnings.append(f"{len(stocks)}只 confirmed 股票未被分组，已补入“未分组候选”。")
            final_categories.append({
                "id": _category_id_from_name(category_name, len(final_categories) + 1),
                "name": category_name,
                "order": len(final_categories) + 1,
                "stocks": sorted(stocks, key=lambda item: (-int(item.get("percentage") or 0), item.get("name", ""), item.get("code", ""))),
            })

    if not final_candidate_pool:
        yield _StepOutcome(error="最终候选池校验后没有可进入看板的股票")
        return
    if len(final_candidate_pool) < _PLANNING_CANDIDATE_TARGET:
        warnings.append(
            f"最终确认候选为{len(final_candidate_pool)}只，低于目标{_PLANNING_CANDIDATE_TARGET}只；递归补搜达到上限或更多候选未通过业务确证。"
        )

    final_categories.sort(key=lambda item: (-max((stock["percentage"] for stock in item["stocks"]), default=0), item["order"], item["name"]))
    for index, category in enumerate(final_categories, start=1):
        category["order"] = index
    final_candidate_pool.sort(key=lambda item: (-_clean_relation_score(item.get("relation_score")), str(item.get("name") or ""), str(item.get("code") or "")))
    verified_codes = sorted({str(item["code"]) for item in final_candidate_pool})
    state.verified_stock_codes = verified_codes

    summary = f"最终候选池一致性校验完成：{len(final_candidate_pool)}只股票进入最终候选池，{len(rejected_stocks)}只保留在未收录名单。"
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=summary,
        data={
            "summary": summary,
            "verified_codes": verified_codes,
            "final_candidate_pool": final_candidate_pool,
            "final_categories": final_categories,
            "rejected_stocks": rejected_stocks,
            "warnings": warnings,
        },
    )
    await _save_checkpoint(
        save_checkpoint,
        _checkpoint_payload(
            state,
            model,
            temperature,
            max_tokens,
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
    """从最终候选池或旧规则校准原始结果提取 code->name 映射，作为最终股票名的首选来源。"""
    name_map: dict[str, str] = {}
    for item in state.completed_steps:
        if item.key != "code_verification":
            continue
        for entry in (item.data or {}).get("final_candidate_pool", []):
            if not isinstance(entry, dict):
                continue
            code = _stock_code_from_record(entry)
            name = str(entry.get("name") or "").strip()
            if code and name:
                name_map[code] = name
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
        (描述映射, 强关联代码集合)。强关联指出现在业务确证步骤或带 evidence/description
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


def _business_confirmation_maps(state: HybridExecutionState) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    confirmed_map: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for item in state.completed_steps:
        if item.key not in {"business_confirmation", "candidate_expansion"}:
            continue
        data = item.data or {}
        for record in data.get("confirmed_stocks", []):
            if not isinstance(record, dict):
                continue
            code = _stock_code_from_record(record)
            if code:
                confirmed_map[code] = record
        for record in data.get("rejected_stocks", []):
            if isinstance(record, dict):
                code = _stock_code_from_record(record) or str(record.get("code") or "").strip()
                rejected.append({
                    "code": code,
                    "name": str(record.get("name") or "").strip(),
                    "relation_score": _clean_relation_score(record.get("relation_score")),
                    "relation_type": "rejected",
                    "reason": str(record.get("reason") or "").strip(),
                    "evidence_url": str(record.get("evidence_url") or "").strip(),
                })
    return confirmed_map, rejected


def _confirmed_stocks_for_pipeline(state: HybridExecutionState) -> list[dict[str, Any]]:
    confirmed_map, _ = _business_confirmation_maps(state)
    return sorted(
        confirmed_map.values(),
        key=lambda item: (-_clean_relation_score(item.get("relation_score")), str(item.get("name") or ""), str(item.get("code") or "")),
    )


def _rejected_stocks_for_pipeline(state: HybridExecutionState) -> list[dict[str, Any]]:
    _, rejected = _business_confirmation_maps(state)
    return rejected


def _used_web_search_queries(state: HybridExecutionState, query: str, task_id: str | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    used: list[dict[str, Any]] = []

    def add(search_query: str, phase: str, intent: str = "") -> None:
        normalized = _normalize_search_query_text(search_query)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        used.append({"query": search_query, "phase": phase, "intent": intent})

    planning_cache = _read_planning_cache(query, task_id)
    if isinstance(planning_cache, dict):
        for spec in planning_cache.get("queries", []):
            if isinstance(spec, dict):
                add(str(spec.get("query") or ""), "planning", str(spec.get("group") or ""))
        for plan in planning_cache.get("search_more_query_plans", []):
            if not isinstance(plan, dict):
                continue
            for spec in plan.get("executed_search_queries", []):
                if isinstance(spec, dict):
                    add(str(spec.get("query") or ""), "planning_search_more", str(spec.get("group") or ""))

    for step in state.completed_steps:
        for observation in step.observations:
            if not isinstance(observation, dict) or observation.get("tool") != "web_search":
                continue
            output = observation.get("output")
            if isinstance(output, dict):
                add(str(output.get("query") or observation.get("input") or ""), step.key)
            else:
                add(str(observation.get("input") or ""), step.key)
    return used


def _business_record_description(record: dict[str, Any]) -> str:
    business_summary = str(record.get("business_summary") or "").strip()
    relation_evidence = str(record.get("relation_evidence") or "").strip()
    confidence_reason = str(record.get("confidence_reason") or "").strip()
    parts = [part for part in (business_summary, relation_evidence, confidence_reason) if part]
    return "；".join(parts) if parts else "业务确证评分进入看板"


def _category_id_from_name(name: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]+", "_", name.strip()).strip("_")
    return slug or f"cat_{index}"


def _stock_item_from_business_record(record: dict[str, Any], category_name: str) -> dict[str, Any]:
    score = _clean_relation_score(record.get("relation_score"))
    return {
        "code": _stock_code_from_record(record) or str(record.get("code") or "").strip(),
        "name": str(record.get("name") or "").strip(),
        "name_en": str(record.get("name_en") or "").strip(),
        "percentage": score,
        "description": _business_record_description(record),
        "category_tag": category_name,
    }


def _fallback_categories_from_confirmed(confirmed_stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relation_names = {
        "strong_supply_chain": "强供应链关系",
        "capital_relation": "资本关系",
        "business_cooperation": "业务合作关系",
        "weak_relevance": "弱关联观察",
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in confirmed_stocks:
        relation_type = str(record.get("relation_type") or "weak_relevance")
        name = relation_names.get(relation_type, "其他确认关系")
        grouped.setdefault(name, []).append(record)
    categories: list[dict[str, Any]] = []
    for index, (name, records) in enumerate(grouped.items(), start=1):
        stocks = [_stock_item_from_business_record(record, name) for record in records]
        stocks.sort(key=lambda item: (-int(item.get("percentage") or 0), item.get("name", ""), item.get("code", "")))
        categories.append({
            "id": _category_id_from_name(name, index),
            "name": name,
            "order": index,
            "stocks": stocks,
        })
    categories.sort(key=lambda item: (-max((stock["percentage"] for stock in item["stocks"]), default=0), item["order"], item["name"]))
    for index, category in enumerate(categories, start=1):
        category["order"] = index
    return categories


def _normalize_grouping_payload(payload: Any, confirmed_stocks: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("链路编排必须是JSON对象")
    confirmed_by_code = {
        code: record
        for record in confirmed_stocks
        for code in [_stock_code_from_record(record)]
        if code
    }
    seen_codes: set[str] = set()
    categories: list[dict[str, Any]] = []
    for raw_category in payload.get("categories", []):
        if not isinstance(raw_category, dict):
            continue
        category_name = str(raw_category.get("name") or "").strip()
        if not category_name:
            continue
        stocks: list[dict[str, Any]] = []
        for raw_stock in raw_category.get("stocks", []):
            if not isinstance(raw_stock, dict):
                continue
            code = _normalize_stock_code(str(raw_stock.get("code") or "")) or ""
            record = confirmed_by_code.get(code)
            if not record or code in seen_codes:
                continue
            seen_codes.add(code)
            stocks.append(_stock_item_from_business_record(record, category_name))
        if stocks:
            stocks.sort(key=lambda item: (-int(item.get("percentage") or 0), item.get("name", ""), item.get("code", "")))
            categories.append({
                "id": str(raw_category.get("id") or _category_id_from_name(category_name, len(categories) + 1)).strip(),
                "name": category_name,
                "order": len(categories) + 1,
                "stocks": stocks,
            })

    missing_records = [record for code, record in confirmed_by_code.items() if code not in seen_codes]
    if missing_records:
        category_name = "未分组候选"
        categories.append({
            "id": _category_id_from_name(category_name, len(categories) + 1),
            "name": category_name,
            "order": len(categories) + 1,
            "stocks": [_stock_item_from_business_record(record, category_name) for record in missing_records],
        })

    if not categories and confirmed_stocks:
        categories = _fallback_categories_from_confirmed(confirmed_stocks)
    if not categories:
        raise ValueError("链路编排未得到任何分类")

    categories.sort(key=lambda item: (-max((stock["percentage"] for stock in item["stocks"]), default=0), item["order"], item["name"]))
    for index, category in enumerate(categories, start=1):
        category["order"] = index
    return {
        "summary": str(payload.get("summary") or "链路编排完成").strip(),
        "categories": categories,
    }


async def _run_category_grouping(
    query: str,
    config: AppConfig,
    client,
    state: HybridExecutionState,
    step: PlanStep,
    task_id: str | None,
) -> AsyncGenerator[dict | _StepOutcome, None]:
    model = config.selected_model
    temperature = config.settings.temperature
    max_tokens = max(config.settings.max_tokens, _LLM_SYNTHESIS_MAX_TOKENS_FLOOR)
    anchor = _business_confirmation_anchor(query, state)
    confirmed_stocks = _confirmed_stocks_for_pipeline(state)
    rejected_stocks = _rejected_stocks_for_pipeline(state)
    if not confirmed_stocks:
        yield _StepOutcome(error="链路编排缺少业务确证通过的 confirmed_stocks")
        return
    messages = [
        {"role": "system", "content": get_category_grouping_prompt(query, anchor, confirmed_stocks, rejected_stocks)},
        {"role": "user", "content": "请输出链路编排JSON。"},
    ]
    last_error = ""
    for attempt in range(1, _STEP_ATTEMPTS + 1):
        try:
            output = await _call_llm(
                client,
                model,
                messages,
                temperature,
                max_tokens,
                step.id,
                idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
            )
            payload = json.loads(_strip_json_fence(output))
            data = _normalize_grouping_payload(payload, confirmed_stocks)
            summary = data["summary"]
            completed = CompletedStep(
                step_id=step.id,
                key=step.key,
                name=step.name,
                summary=summary,
                data={
                    **data,
                    "confirmed_stocks": confirmed_stocks,
                    "rejected_stocks": rejected_stocks,
                },
                observations=[],
            )
            yield _StepOutcome(completed_step=completed)
            return
        except Exception as exc:
            last_error = str(exc)
            messages.extend([
                {"role": "assistant", "content": output if "output" in locals() else ""},
                {"role": "user", "content": f"上一轮链路编排JSON无效：{exc}。请只输出严格JSON，且所有confirmed_stocks都必须且只能出现一次。"},
            ])

    try:
        categories = _fallback_categories_from_confirmed(confirmed_stocks)
        summary = f"链路编排由程序化兜底完成：模型分组失败，原因：{last_error}"
        completed = CompletedStep(
            step_id=step.id,
            key=step.key,
            name=step.name,
            summary=summary,
            data={
                "summary": summary,
                "categories": categories,
                "confirmed_stocks": confirmed_stocks,
                "rejected_stocks": rejected_stocks,
                "fallback": True,
            },
            observations=[],
        )
        yield _StepOutcome(completed_step=completed)
    except Exception as exc:
        yield _StepOutcome(error=f"链路编排失败：{last_error}；程序化兜底失败：{exc}")


def _apply_business_confirmation_to_theme(theme: Theme, state: HybridExecutionState) -> Theme:
    confirmed_map, rejected = _business_confirmation_maps(state)
    if not confirmed_map and not rejected:
        return theme

    for category in theme.categories:
        filtered = []
        for stock in category.stocks:
            record = confirmed_map.get(stock.code)
            if not record:
                continue
            score = _clean_relation_score(record.get("relation_score"))
            if score < 40:
                continue
            stock.percentage = score
            desc = _business_record_description(record)
            if desc:
                stock.description = desc
            if not stock.category_tag:
                stock.category_tag = category.name
            filtered.append(stock)
        category.stocks = sorted(filtered, key=lambda stock: (-stock.percentage, stock.name, stock.code))

    theme.categories = [category for category in theme.categories if category.stocks]
    if not theme.categories:
        raise ValueError("最终Theme未包含任何业务确证通过的股票")
    theme.categories = sorted(
        theme.categories,
        key=lambda category: (
            -max((stock.percentage for stock in category.stocks), default=0),
            category.order or 999,
            category.name,
        ),
    )
    for index, category in enumerate(theme.categories, start=1):
        category.order = index
    theme.rejected_stocks = [RejectedStock.model_validate(item) for item in rejected]
    return theme


def _grouping_category_items(state: HybridExecutionState) -> list[tuple[str, list[Any]]]:
    """提取最终分组项，优先使用规则校准后的 final_categories，兼容旧分组形态。"""
    grouping_data: Any = None
    for item in state.completed_steps:
        if item.key == "code_verification":
            final_categories = (item.data or {}).get("final_categories")
            if final_categories:
                grouping_data = final_categories
                break
    if grouping_data is None:
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


def _grouping_category_items_from_grouping_step(state: HybridExecutionState) -> list[tuple[str, list[Any]]]:
    """规则校准使用的分组源：只读取链路编排步骤，避免读取自身 final_categories。"""
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
    """主题成图失败时的程序化兜底：复用已完成步骤的分组结构和校验结果直接拼装Theme。

    链路编排已完成全部分类智力工作、规则校准已统一最终候选池，因此主题成图本质只是格式转换，
    完全可以脱离模型确定性地完成，避免长JSON被max_tokens截断导致整任务失败。

    异常:
        ValueError: 缺少分组数据或拼装后没有任何有效分类。
    """
    category_items = _grouping_category_items(state)
    if not category_items:
        raise ValueError("缺少链路编排数据，无法程序化组装")

    verified = set(state.verified_stock_codes)
    name_map = _verification_name_map(state)
    desc_map, evidence_codes = _description_evidence_map(state)
    confirmed_map, rejected = _business_confirmation_maps(state)
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
            business_record = confirmed_map.get(code)
            if confirmed_map and not business_record:
                continue
            seen_codes.add(code)
            stock_name = name_map.get(code) or str(record.get("name") or "").strip() or code
            stock_desc = (
                _business_record_description(business_record)
                if business_record
                else desc_map.get(code) or str(record.get("role") or "").strip() or f"{cat_name}相关标的"
            )
            relation_score = (
                _clean_relation_score(business_record.get("relation_score"))
                if business_record
                else _FALLBACK_PERCENTAGE_WITH_EVIDENCE if code in evidence_codes else _FALLBACK_PERCENTAGE_DEFAULT
            )
            stocks.append({
                "code": code,
                "name": stock_name,
                "name_en": "",
                "percentage": relation_score,
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
        "rejected_stocks": rejected,
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
    """在LLM主题成图失败后发出程序化兜底结果；兜底也失败时返回带双重原因的错误。"""
    try:
        theme = _assemble_theme_from_completed_steps(query, state, task_id)
        theme = _apply_business_confirmation_to_theme(theme, state)
    except Exception as exc:
        yield _StepOutcome(error=f"主题成图失败: {llm_error}；程序化兜底也失败: {exc}")
        return
    logger.warning("主题成图回退为程序化组装：LLM失败=%s，生成分类=%d", llm_error, len(theme.categories))
    yield _make_event(
        "thinking",
        content=f"主题成图由程序化兜底生成（{len(theme.categories)}个分类），原因：{llm_error}。",
        step=step.id,
        task_id=task_id,
        plan_step=step.name,
    )
    yield _make_event("result", theme=json.loads(theme.model_dump_json()), task_id=task_id)
    completed = CompletedStep(
        step_id=step.id,
        key=step.key,
        name=step.name,
        summary=f"最终Theme由主题成图程序化兜底生成（{len(theme.categories)}个分类）。",
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
    # 主题成图输出全部已验证股票的完整Theme JSON，体量大，对输出预算取下限兜底，避免被截断。
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
        {"role": "user", "content": "请生成主题成图最终Theme JSON。"},
    ]

    llm_error = ""
    for attempt in range(1, _FINAL_ATTEMPTS + 1):
        try:
            # 主题成图同为纯合成步骤，输出长JSON，放宽流式空闲超时。
            output = await _call_llm(
                client, model, messages, temperature, max_tokens, step.id,
                idle_timeout=_LLM_SYNTHESIS_IDLE_TIMEOUT_SECONDS,
            )
            parsed = parse_llm_output(output)
            if parsed and getattr(parsed, "thought", ""):
                yield _make_event("thinking", content=parsed.thought, step=step.id, task_id=task_id, plan_step=step.name, attempt=attempt)
            if not isinstance(parsed, ParsedFinalAnswer):
                raise ValueError("主题成图必须输出Final Answer")
            theme = _build_theme_from_json(parsed.answer)
            theme = _apply_business_confirmation_to_theme(theme, state)
            missing_codes = sorted(_extract_theme_codes(theme) - set(state.verified_stock_codes))
            if missing_codes:
                raise ValueError(f"最终答案包含未验证股票代码: {','.join(missing_codes)}")
            yield _make_event("result", theme=json.loads(theme.model_dump_json()), task_id=task_id)
            completed = CompletedStep(
                step_id=step.id,
                key=step.key,
                name=step.name,
                summary="主题成图最终Theme JSON已生成。",
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
    should_pause=None,
) -> AsyncGenerator[dict, None]:
    """Recursive Evidence-Planning Agent 主循环，单个SOP步骤内部使用有界ReAct或专用核验器。"""
    client = create_client(config)
    model = config.selected_model
    temperature = config.settings.temperature
    max_tokens = config.settings.max_tokens
    state = _state_from_checkpoint(checkpoint)
    if state.plan:
        state.plan = _sanitize_plan_for_config(state.plan, config.web_search.enabled)

    if not state.plan:
        yield _make_event("thinking", content="正在生成全局执行计划，SOP步骤由系统固定控制；候选网页搜索将在第一步「线索捕获」中执行。", step=0, task_id=task_id)
        state.plan = await _create_plan(query, client, model, temperature, max_tokens, config.web_search.enabled, task_id=task_id)
        state.current_plan_step = 1
        state.step_attempt = 1
        await _save_checkpoint(save_checkpoint, _checkpoint_payload(state, model, temperature, max_tokens))
        yield _make_event("thinking", content=f"已生成全局SOP计划：{_SOP_DISPLAY_FLOW}。", step=0, task_id=task_id)

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

        if step.key == "candidate_discovery":
            executor = _run_candidate_discovery(query, config, client, state, step, task_id, save_checkpoint)
        elif step.key == "business_confirmation":
            executor = _run_business_confirmation(query, config, client, state, step, task_id, save_checkpoint)
        elif step.key == "candidate_expansion":
            executor = _run_candidate_expansion(query, config, client, state, step, task_id, save_checkpoint)
        elif step.key == "category_grouping":
            executor = _run_category_grouping(query, config, client, state, step, task_id)
        elif step.key == "code_verification":
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
            if should_pause and should_pause() and state.current_plan_step <= len(state.plan.steps):
                yield _make_event(
                    "paused",
                    message=f"已在「{step.name}」环节完成后暂停，可点击「继续」从下一环节恢复",
                    task_id=task_id,
                    step=step.id,
                    plan_step=step.name,
                )
                yield _make_event("done", task_id=task_id)
                return

    yield _make_event("done", task_id=task_id)
