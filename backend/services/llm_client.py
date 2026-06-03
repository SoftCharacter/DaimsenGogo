"""
LLM客户端
OpenAI兼容的流式调用封装，支持任意兼容OpenAI API的供应商
提供流式和非流式两种聊天补全方法
"""
import asyncio
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI
from backend.models.config_models import AppConfig

logger = logging.getLogger(__name__)


class LLMTruncationError(Exception):
    """模型输出因达到 max_tokens 上限被截断时抛出。

    携带已生成的部分文本，便于上层记录诊断或触发兜底逻辑。
    截断重试无意义（相同 max_tokens 会再次截断），上层应快速失败或走兜底，
    不要按瞬时异常重试。
    """

    def __init__(self, partial_text: str, generated_chars: int):
        self.partial_text = partial_text
        self.generated_chars = generated_chars
        super().__init__(f"模型输出被max_tokens截断，已生成{generated_chars}字符")

# 客户端整体连接超时（秒）。设较大值兜底，真正的细粒度超时由上层空闲超时控制，
# 避免 AsyncOpenAI 默认 600s 与外层超时叠加导致行为不可控。
_CLIENT_TIMEOUT_SECONDS = 300
# 关闭 SDK 内部自动重试，重试策略统一由上层 _call_llm 控制，避免双重重试叠加放大延迟。
_CLIENT_MAX_RETRIES = 0


def create_client(config: AppConfig) -> AsyncOpenAI:
    """
    根据配置创建OpenAI兼容客户端
    使用供应商的base_url和api_key初始化异步客户端，
    并显式约束整体超时与内部重试次数，避免与上层超时/重试叠加。
    """
    return AsyncOpenAI(
        api_key=config.provider.api_key,
        base_url=config.provider.base_url,
        timeout=_CLIENT_TIMEOUT_SECONDS,
        max_retries=_CLIENT_MAX_RETRIES,
    )


async def chat_stream(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """
    流式聊天补全
    向LLM发起流式请求，逐块yield生成的文本内容
    适用于需要实时展示生成过程的场景
    """
    # 发起流式请求
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    # 逐块读取流式响应，仅提取文本增量
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def chat_complete(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """
    非流式聊天补全
    向LLM发起完整请求，返回完整的生成文本
    适用于不需要实时展示的后台处理场景
    """
    # 发起非流式请求，等待完整响应
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    # 提取助手回复内容，为空时返回空字符串
    return response.choices[0].message.content or ""


async def chat_complete_streaming(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    *,
    idle_timeout: float = 30.0,
) -> str:
    """
    流式聊天补全（带空闲超时），返回拼接后的完整文本。

    与 chat_complete 的区别：用「相邻 chunk 之间的空闲超时」替代「整段墙钟超时」。
    每收到一个增量就重置计时器，只有连续 idle_timeout 秒收不到任何新内容才判定为卡死。
    这样长输出（如结果分组的长JSON）只要持续吐字就不会被误判超时，
    同时仍能在连接真正停滞时快速中止。

    参数:
        idle_timeout: 相邻增量之间允许的最大空闲秒数，超过则抛 asyncio.TimeoutError。

    返回:
        拼接后的完整文本。

    异常:
        asyncio.TimeoutError: 连续空闲超过 idle_timeout 秒（视为连接停滞）。
        LLMTruncationError: 模型因达到 max_tokens 被截断（finish_reason=length）。
    """
    # 发起流式请求；首个增量到达前同样受 idle_timeout 约束（覆盖prefill/思考链耗时过久的情况）。
    stream = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        ),
        timeout=idle_timeout,
    )
    chunks: list[str] = []
    finish_reason: str | None = None
    # 取异步迭代器，逐个增量包裹独立的空闲超时；任一增量超时即视为连接停滞。
    iterator = stream.__aiter__()
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(iterator.__anext__(), timeout=idle_timeout)
            except StopAsyncIteration:
                break
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                chunks.append(choice.delta.content)
            # 记录最后一个非空的 finish_reason，流结束后据此判断是否被截断。
            if choice.finish_reason:
                finish_reason = choice.finish_reason
    finally:
        # 主动关闭底层流，避免超时中止后连接悬挂。
        await stream.close()

    text = "".join(chunks)
    # finish_reason=length 表示输出在 max_tokens 处被硬截断，结果通常是残缺JSON。
    # 抛专用异常让上层能够记录部分输出并走兜底，而不是把残缺文本当正常结果解析。
    if finish_reason == "length":
        logger.warning("LLM输出被max_tokens截断：已生成%d字符，建议提高max_tokens或减小输出规模", len(text))
        raise LLMTruncationError(partial_text=text, generated_chars=len(text))
    return text
