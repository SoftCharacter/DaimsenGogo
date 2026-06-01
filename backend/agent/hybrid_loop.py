"""
Plan-and-Execute + 局部ReAct混合主循环
全局SOP由后端固定控制，单个步骤内部使用有界ReAct处理局部不确定性。
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from backend.agent.output_parser import ParsedAction, ParsedFinalAnswer, ParsedStepResult, parse_llm_output
from backend.agent.plan_models import AnalysisPlan, CompletedStep, HybridExecutionState, PlanStep, PlanStepStatus
from backend.agent.prompts import get_final_assembly_prompt, get_planner_prompt, get_step_react_prompt
from backend.agent.react_loop import (
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
from backend.models.analysis_task_models import AnalysisCheckpoint
from backend.models.config_models import AppConfig
from backend.services.akshare_adapter import format_stock_code, get_stock_list
from backend.services.llm_client import create_client

logger = logging.getLogger(__name__)
_ARCHITECTURE = "plan_execute_react_v1"
_STEP_ATTEMPTS = 3
_FORMAT_REPAIR_ATTEMPTS = 2
_FINAL_ATTEMPTS = 3
_PLANNING_WEB_SEARCH_LIMIT = 26
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


async def _collect_planning_web_context(query: str, task_id: str | None) -> dict[str, Any]:
    """在规划前执行网页检索，让planner先看到新事件的真实边界和直接候选。"""
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    query_specs = _planning_web_query_specs(query)
    for spec in query_specs:
        search_query = spec["query"]
        action_input = json.dumps({
            "query": search_query,
            "search_depth": "advanced",
            "max_results": 20,
            "topic": spec.get("topic", "general"),
            "include_raw_content": True,
            "chunks_per_source": 3,
        }, ensure_ascii=False)
        action = ParsedAction(thought="规划前网页检索校准候选。", action="web_search", action_input=action_input)
        try:
            result = await _execute_tool(action, task_id=task_id)
        except Exception as exc:
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
    return {"queries": query_specs, "entries": entries, "stock_terms": stock_terms, "errors": errors}


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
    try:
        planner_output = await _call_llm(client, model, messages, temperature, max_tokens, 0)
        planner_data = _parse_json_object(planner_output)
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
    max_tokens = config.settings.max_tokens

    observations: list[dict[str, Any]] = []

    for attempt in range(state.step_attempt, _STEP_ATTEMPTS + 1):
        state.step_attempt = attempt
        state.local_action_count = 0
        if not state.current_step_messages:
            state.current_step_messages = [
                {
                    "role": "system",
                    "content": get_step_react_prompt(
                        query,
                        state.plan.model_dump() if state.plan else {},
                        step.model_dump(),
                        _completed_steps_dump(state),
                        attempt,
                    ),
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
            repair_messages = [dict(item) for item in state.current_step_messages]
            for repair_index in range(_FORMAT_REPAIR_ATTEMPTS + 1):
                try:
                    llm_output = await _call_llm(client, model, repair_messages, temperature, max_tokens, step.id)
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
    max_tokens = config.settings.max_tokens
    messages = [
        {
            "role": "system",
            "content": get_final_assembly_prompt(
                query,
                state.plan.model_dump() if state.plan else {},
                _completed_steps_dump(state),
                state.verified_stock_codes,
            ),
        },
        {"role": "user", "content": "请生成最终Theme JSON。"},
    ]

    for attempt in range(1, _FINAL_ATTEMPTS + 1):
        try:
            output = await _call_llm(client, model, messages, temperature, max_tokens, step.id)
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
        except Exception as exc:
            if attempt == _FINAL_ATTEMPTS:
                yield _StepOutcome(error=f"最终组装失败: {exc}")
                return
            messages.extend([
                {"role": "assistant", "content": output if 'output' in locals() else ""},
                {"role": "user", "content": f"最终JSON无法解析或校验失败：{exc}。请只使用已验证代码重新输出 Final Answer 和合法JSON。"},
            ])


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
        errors = state.plan.planning_errors if not evidence_count and config.web_search.enabled else []
        error_note = f"；规划前网页搜索不可用或未命中：{errors[0]}" if errors else ""
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
