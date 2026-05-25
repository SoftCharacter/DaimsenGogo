"""
LLM客户端
OpenAI兼容的流式调用封装，支持任意兼容OpenAI API的供应商
提供流式和非流式两种聊天补全方法
"""
from typing import AsyncGenerator

from openai import AsyncOpenAI
from backend.models.config_models import AppConfig


def create_client(config: AppConfig) -> AsyncOpenAI:
    """
    根据配置创建OpenAI兼容客户端
    使用供应商的base_url和api_key初始化异步客户端
    """
    return AsyncOpenAI(
        api_key=config.provider.api_key,
        base_url=config.provider.base_url,
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
