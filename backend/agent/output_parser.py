"""
输出解析器
使用正则表达式从LLM的文本输出中解析ReAct格式的内容，
识别 Thought / Action / Action Input / Step Result / Final Answer 等标签，
将其转换为结构化的数据对象供主循环使用。
"""
import json
import re
from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class ParsedAction:
    """
    解析出的工具调用动作
    当LLM决定调用某个工具时，输出中会包含Action和Action Input
    """
    thought: str       # LLM的思考过程
    action: str        # 工具名称，如 search_stocks
    action_input: str  # 工具参数，如 "华为"


@dataclass
class ParsedFinalAnswer:
    """
    解析出的最终答案
    当LLM认为分析已完成时，输出 Final Answer 及JSON结果
    """
    thought: str  # LLM的最终思考
    answer: str   # 最终答案的JSON字符串


@dataclass
class ParsedStepResult:
    """解析出的单个SOP步骤结果。"""
    thought: str
    result: str


_LABEL_PATTERN = re.compile(
    r"^\s*(Thought|Action|Action Input|Observation|Step Result|Final Answer)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _extract_json_from_answer(raw: str) -> str:
    """
    从Final Answer文本中提取纯JSON字符串
    LLM可能用markdown代码块包裹JSON，需要剥离

    参数:
        raw: Final Answer后面的原始文本

    返回:
        清理后的JSON字符串
    """
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    return raw.strip()


def _strip_code_block(raw: str) -> str:
    """剥离Action Input外层代码块，保留内部文本。"""
    cleaned = raw.strip()
    code_block = re.fullmatch(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    return cleaned


def _extract_action_input(raw: str) -> str:
    """从Action Input中提取可执行参数，只兼容明确的单字段JSON包装。"""
    cleaned = _strip_code_block(raw)
    cleaned = re.split(r"\bObservation\s*:", cleaned, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned

        if isinstance(payload, dict):
            for key in ("keyword", "code", "codes"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    return ",".join(item.strip() for item in value if item.strip())
        return cleaned

    return cleaned


def _parse_sections(text: str) -> dict[str, str]:
    """按行首标签解析ReAct输出，避免从正文或工具结果中误抓标签。"""
    sections: dict[str, list[str]] = {}
    current_label: str | None = None

    for line in text.splitlines():
        match = _LABEL_PATTERN.match(line)
        if match:
            label = match.group(1).lower()
            value = match.group(2)
            current_label = label
            sections.setdefault(label, []).append(value)
            continue

        if current_label:
            sections[current_label].append(line)

    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _clean_action_name(raw: str) -> str:
    """清理工具名称，只保留函数名主体。"""
    cleaned = raw.strip().strip("` ")
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", cleaned)
    return match.group(1) if match else cleaned


def parse_llm_output(text: str) -> Optional[Union[ParsedAction, ParsedFinalAnswer, ParsedStepResult]]:
    """
    解析LLM的单次输出文本，识别其中的Action或Final Answer

    解析优先级：
    1. 先检查是否包含 Final Answer（分析结束）
    2. 再检查是否包含 Step Result（单个SOP步骤结束）
    3. 再检查是否包含 Action + Action Input（工具调用）
    4. 都没有则返回 None（输出格式异常）

    参数:
        text: LLM的原始输出文本

    返回:
        ParsedAction    - 需要调用工具
        ParsedFinalAnswer - 分析完成，包含最终JSON
        None            - 无法解析（格式不符合ReAct规范）
    """
    sections = _parse_sections(text)
    thought = sections.get("thought", "")

    if "final answer" in sections:
        json_str = _extract_json_from_answer(sections["final answer"])
        return ParsedFinalAnswer(thought=thought, answer=json_str)

    if "step result" in sections:
        json_str = _extract_json_from_answer(sections["step result"])
        return ParsedStepResult(thought=thought, result=json_str)

    action = sections.get("action", "")
    if action:
        raw_input = sections.get("action input", "")
        return ParsedAction(
            thought=thought,
            action=_clean_action_name(action),
            action_input=_extract_action_input(raw_input),
        )

    return None
