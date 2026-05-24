"""
ReAct主循环
实现 Reason + Act 推理循环，作为异步生成器向前端流式推送SSE事件。
支持历史任务checkpoint恢复。
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Iterable

from backend.agent.output_parser import ParsedAction, ParsedFinalAnswer, parse_llm_output
from backend.agent.prompts import get_system_prompt
from backend.agent.tools import get_company_info, search_stocks, verify_stock_code
from backend.models.config_models import AppConfig
from backend.models.theme_models import Theme
from backend.services.llm_client import chat_complete, create_client

logger = logging.getLogger(__name__)
_MAX_ITERATIONS = 15
_LLM_TIMEOUT_SECONDS = 60
_LLM_RETRY_COUNT = 2
_TOOL_TIMEOUT_SECONDS = 45
_TOOL_ATTEMPTS = 3
_FORMAT_REPAIR_ATTEMPTS = 2
_FINAL_REPAIR_ATTEMPTS = 2
_CODE_PATTERN = re.compile(r"^(SZ|SH|BJ):\d{6}$")
_TOOL_MAP = {
    "search_stocks": search_stocks,
    "get_company_info": get_company_info,
    "verify_stock_code": verify_stock_code,
}


def _validate_theme(theme: Theme) -> None:
    """对最终主题做轻量业务校验，避免明显坏结果进入前端。"""
    if not theme.categories:
        raise ValueError("categories不能为空")

    for category in theme.categories:
        if not category.stocks:
            raise ValueError(f"分类 {category.name} 至少需要1只股票")
        category_codes: set[str] = set()
        for stock in category.stocks:
            if not _CODE_PATTERN.match(stock.code):
                raise ValueError(f"股票代码格式错误: {stock.code}")
            if not 0 <= stock.percentage <= 100:
                raise ValueError(f"percentage必须在0-100之间: {stock.code}")
            if stock.code in category_codes:
                raise ValueError(f"分类 {category.name} 内股票代码重复: {stock.code}")
            category_codes.add(stock.code)


def _build_theme_from_json(raw_json: str) -> Theme:
    data = json.loads(raw_json)
    now = datetime.now(timezone.utc).isoformat()
    theme_id = f"theme_{uuid.uuid4().hex[:8]}"
    data.setdefault("id", theme_id)
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)
    theme = Theme.model_validate(data)
    _validate_theme(theme)
    return theme


def _parse_tool_payload(tool_result: str) -> dict[str, Any] | None:
    """解析工具返回JSON，失败时返回None。"""
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _is_fatal_tool_failure(tool_result: str) -> bool:
    """判断工具返回是否属于应立即停止的致命失败。"""
    payload = _parse_tool_payload(tool_result)
    return payload is None or payload.get("fatal") is True


def _extract_verified_codes(tool_result: str) -> set[str]:
    """提取 verify_stock_code 中已确认有效的股票代码。"""
    payload = _parse_tool_payload(tool_result)
    results = payload.get("results") if payload else None
    if payload and not payload.get("error") and isinstance(results, list):
        return {
            str(item.get("code"))
            for item in results
            if isinstance(item, dict) and item.get("valid") is True and item.get("code")
        }
    return set()


def _extract_theme_codes(theme: Theme) -> set[str]:
    """提取最终主题中出现的全部股票代码。"""
    return {stock.code for category in theme.categories for stock in category.stocks}


def _recover_verified_stock_codes(messages: list[dict[str, Any]]) -> set[str]:
    """从checkpoint消息中恢复已完成有效校验的股票代码集合。"""
    verified_codes: set[str] = set()
    for index, message in enumerate(messages[:-1]):
        if message.get("role") != "assistant":
            continue
        parsed = parse_llm_output(str(message.get("content", "")))
        if not isinstance(parsed, ParsedAction) or parsed.action != "verify_stock_code":
            continue
        observation = messages[index + 1]
        if observation.get("role") != "user":
            continue
        content = str(observation.get("content", ""))
        if content.startswith("Observation:"):
            verified_codes.update(_extract_verified_codes(content.removeprefix("Observation:").strip()))
    return verified_codes


def _make_event(event_type: str, **kwargs) -> dict:
    return {"event": event_type, "data": kwargs}


def _clone_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in messages]


async def _call_llm(client, model: str, messages: list[dict[str, Any]], temperature: float, max_tokens: int, step: int) -> str:
    last_error: Exception | None = None
    for attempt in range(_LLM_RETRY_COUNT + 1):
        try:
            return await asyncio.wait_for(
                chat_complete(client, model, messages, temperature, max_tokens),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            last_error = exc
            logger.warning("LLM调用失败 (第%d轮，第%d次): %s", step, attempt + 1, exc)
            if attempt < _LLM_RETRY_COUNT:
                await asyncio.sleep(1 + attempt)
    raise RuntimeError(f"LLM调用失败，已重试{_LLM_RETRY_COUNT}次: {last_error}")


async def _execute_tool(action: ParsedAction, task_id: str | None = None) -> str:
    tool_fn = _TOOL_MAP.get(action.action)
    if not tool_fn:
        return json.dumps({"error": f"未知工具: {action.action}", "fatal": True, "retryable": False}, ensure_ascii=False)

    action_input = action.action_input.strip()
    if not action_input:
        return json.dumps({"error": "工具参数不能为空", "tool": action.action, "fatal": True, "retryable": False}, ensure_ascii=False)

    last_result = ""
    for attempt in range(1, _TOOL_ATTEMPTS + 1):
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool_fn, action_input, task_id),
                timeout=_TOOL_TIMEOUT_SECONDS,
            )
            if _parse_tool_payload(result) is not None:
                return result
            last_result = json.dumps(
                {"error": "工具返回非JSON格式", "tool": action.action, "fatal": True, "retryable": False},
                ensure_ascii=False,
            )
        except asyncio.TimeoutError:
            logger.error("工具执行超时 [%s] 第%d次", action.action, attempt)
            last_result = json.dumps(
                {"error": "工具执行超时", "tool": action.action, "fatal": True, "retryable": attempt < _TOOL_ATTEMPTS},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error("工具执行失败 [%s] 第%d次: %s", action.action, attempt, e)
            last_result = json.dumps(
                {"error": f"工具执行异常: {e}", "tool": action.action, "fatal": True, "retryable": attempt < _TOOL_ATTEMPTS},
                ensure_ascii=False,
            )
    return last_result


async def _save_checkpoint(save_checkpoint, payload: dict[str, Any]) -> None:
    if not save_checkpoint:
        return
    maybe = save_checkpoint(payload)
    if asyncio.iscoroutine(maybe):
        await maybe


def _checkpoint_payload(
    step: int,
    max_steps: int,
    messages: list[dict[str, Any]],
    model: str,
    temperature: float,
    max_tokens: int,
    last_llm_output: str = "",
    last_action: dict[str, Any] | None = None,
    last_observation: str = "",
) -> dict[str, Any]:
    return {
        "step": step,
        "max_steps": max_steps,
        "messages": _clone_messages(messages),
        "last_llm_output": last_llm_output,
        "last_action": last_action,
        "last_observation": last_observation,
        "config_snapshot": {
            "selected_model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def react_loop(
    query: str,
    config: AppConfig,
    *,
    initial_messages: list[dict[str, Any]] | None = None,
    start_step: int = 1,
    max_steps: int = _MAX_ITERATIONS,
    task_id: str | None = None,
    save_checkpoint=None,
) -> AsyncGenerator[dict, None]:
    """ReAct推理循环，支持从checkpoint恢复。"""
    client = create_client(config)
    model = config.selected_model
    temperature = config.settings.temperature
    max_tokens = config.settings.max_tokens
    messages = _clone_messages(initial_messages) if initial_messages else [
        {"role": "system", "content": get_system_prompt(query)},
        {"role": "user", "content": f"请分析: {query}"},
    ]
    verified_stock_codes = _recover_verified_stock_codes(messages)

    await _save_checkpoint(save_checkpoint, _checkpoint_payload(start_step, max_steps, messages, model, temperature, max_tokens))

    for step in range(start_step, max_steps + 1):
        yield _make_event("progress", step=step, max_steps=max_steps, task_id=task_id)
        repair_messages = _clone_messages(messages)
        parsed = None
        llm_output = ""

        for repair_index in range(_FORMAT_REPAIR_ATTEMPTS + 1):
            try:
                llm_output = await _call_llm(client, model, repair_messages, temperature, max_tokens, step)
                logger.info("ReAct第%d轮LLM返回%d字符", step, len(llm_output))
            except Exception as e:
                logger.error("LLM调用失败 (第%d轮): %s", step, e)
                yield _make_event("error", message=str(e), task_id=task_id)
                yield _make_event("done", task_id=task_id)
                return

            await _save_checkpoint(
                save_checkpoint,
                _checkpoint_payload(step, max_steps, repair_messages, model, temperature, max_tokens, llm_output),
            )
            parsed = parse_llm_output(llm_output)
            if parsed is not None:
                break

            yield _make_event("thinking", content=llm_output, step=step, task_id=task_id)
            if repair_index == _FORMAT_REPAIR_ATTEMPTS:
                yield _make_event("error", message="模型输出格式连续不符合ReAct要求，请重试。", task_id=task_id)
                yield _make_event("done", task_id=task_id)
                return
            repair_messages.extend([
                {"role": "assistant", "content": llm_output},
                {"role": "user", "content": "上一条无法解析。请只输出 Thought/Action/Action Input 或 Final Answer；不要输出 Observation。"},
            ])

        if parsed and parsed.thought:
            yield _make_event("thinking", content=parsed.thought, step=step, task_id=task_id)

        if isinstance(parsed, ParsedFinalAnswer):
            final_messages = _clone_messages(repair_messages)
            final_output = llm_output
            final_answer = parsed.answer
            needs_verification = False
            for repair_index in range(_FINAL_REPAIR_ATTEMPTS + 1):
                try:
                    theme = _build_theme_from_json(final_answer)
                    missing_codes = sorted(_extract_theme_codes(theme) - verified_stock_codes)
                    if missing_codes:
                        yield _make_event("thinking", content="最终答案前必须先调用 verify_stock_code 并确认所有股票代码有效。", step=step, task_id=task_id)
                        messages = _clone_messages(repair_messages)
                        messages.extend([
                            {"role": "assistant", "content": final_output},
                            {"role": "user", "content": f"最终答案中还有未验证股票代码：{','.join(missing_codes)}。请先调用 verify_stock_code，Action Input 为这些代码的逗号分隔列表。"},
                        ])
                        await _save_checkpoint(
                            save_checkpoint,
                            _checkpoint_payload(step + 1, max_steps, messages, model, temperature, max_tokens, final_output),
                        )
                        needs_verification = True
                        break
                    yield _make_event("result", theme=json.loads(theme.model_dump_json()), task_id=task_id)
                    yield _make_event("done", task_id=task_id)
                    return
                except Exception as e:
                    logger.warning("解析最终答案失败 (第%d轮，第%d次): %s", step, repair_index + 1, e)
                    if repair_index == _FINAL_REPAIR_ATTEMPTS:
                        yield _make_event("error", message=f"解析分析结果失败: {e}", task_id=task_id)
                        yield _make_event("done", task_id=task_id)
                        return
                    final_messages.extend([
                        {"role": "assistant", "content": final_output},
                        {"role": "user", "content": f"最终JSON无法解析或校验失败：{e}。请只输出 Final Answer 和修复后的合法JSON。"},
                    ])
                    final_output = await _call_llm(client, model, final_messages, temperature, max_tokens, step)
                    repaired = parse_llm_output(final_output)
                    if repaired and repaired.thought:
                        yield _make_event("thinking", content=repaired.thought, step=step, task_id=task_id)
                    if isinstance(repaired, ParsedFinalAnswer):
                        final_answer = repaired.answer
                    else:
                        final_answer = final_output
            if needs_verification:
                continue

        if isinstance(parsed, ParsedAction):
            yield _make_event("tool_call", tool=parsed.action, input=parsed.action_input, step=step, task_id=task_id)
            logger.info("ReAct第%d轮执行工具: %s(%s)", step, parsed.action, parsed.action_input)
            tool_result = await _execute_tool(parsed, task_id=task_id)
            if parsed.action == "verify_stock_code":
                verified_stock_codes.update(_extract_verified_codes(tool_result))
            yield _make_event("tool_result", tool=parsed.action, output=tool_result, step=step, task_id=task_id)
            if _is_fatal_tool_failure(tool_result):
                message = (_parse_tool_payload(tool_result) or {}).get("error", "工具返回格式异常")
                yield _make_event("error", message=message, task_id=task_id)
                yield _make_event("done", task_id=task_id)
                return
            messages = _clone_messages(repair_messages)
            messages.extend([
                {"role": "assistant", "content": llm_output},
                {"role": "user", "content": f"Observation: {tool_result}"},
            ])
            await _save_checkpoint(
                save_checkpoint,
                _checkpoint_payload(
                    step + 1,
                    max_steps,
                    messages,
                    model,
                    temperature,
                    max_tokens,
                    llm_output,
                    {"action": parsed.action, "action_input": parsed.action_input, "thought": parsed.thought},
                    tool_result,
                ),
            )

    yield _make_event("error", message=f"分析超过最大轮次({max_steps})，请点击继续执行或缩小分析范围后重试。", task_id=task_id)
    yield _make_event("done", task_id=task_id)
