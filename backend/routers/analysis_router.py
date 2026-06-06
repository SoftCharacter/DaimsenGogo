"""
AI分析路由
提供ReAct Agent供应链分析的SSE流式接口。
前端通过POST请求发起分析，后端以SSE（Server-Sent Events）
方式实时推送分析进度、工具调用结果和最终Theme。
"""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.services.file_service import load_config
from backend.agent.hybrid_loop import plan_execute_react_loop

# 日志记录器
logger = logging.getLogger(__name__)

# 创建路由实例，所有接口挂载在 /analysis 前缀下
router = APIRouter()
_MAX_QUERY_LENGTH = 120


class AnalysisRequest(BaseModel):
    """分析请求体"""
    query: str  # 用户输入的分析查询，如 "华为昇腾供应链"


async def _event_generator(query: str):
    """
    SSE事件生成器

    包装 react_loop 的输出，将每个事件字典转换为
    SSE协议要求的格式（event + data）。

    参数:
        query: 用户输入的分析查询

    生成:
        符合SSE协议的事件字典，包含 event 和 data 字段
    """
    # 加载当前配置
    config = load_config()

    task_id = f"analysis_{uuid.uuid4().hex[:12]}"

    try:
        # 遍历ReAct循环产生的所有事件
        async for event in plan_execute_react_loop(query, config, task_id=task_id):
            # 提取事件类型和数据
            event_type = event.get("event", "message")
            event_data = event.get("data", {})
            # 按SSE协议格式yield
            yield {
                "event": event_type,
                "data": json.dumps(event_data, ensure_ascii=False),
            }
    except Exception as e:
        # 捕获未预期的异常，推送错误事件
        logger.error("分析流程异常: %s", e, exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"分析过程发生异常: {e}"},
                ensure_ascii=False,
            ),
        }
        yield {
            "event": "done",
            "data": json.dumps({}, ensure_ascii=False),
        }


@router.post("/run")
async def run_analysis(body: AnalysisRequest):
    """
    启动ReAct供应链分析

    接收用户的分析查询，验证配置完整性后，
    返回SSE事件流。前端通过EventSource监听实时进度。

    请求体:
        query: 分析主题描述，如 "华为昇腾供应链"

    返回:
        EventSourceResponse - SSE事件流

    异常:
        422: query为空
        400: 配置不完整（缺少API密钥或未选择模型）
    """
    # 验证查询不为空
    query = body.query.strip() if body.query else ""
    if not query:
        raise HTTPException(
            status_code=422,
            detail="分析查询不能为空",
        )
    if len(query) > _MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"分析查询不能超过{_MAX_QUERY_LENGTH}个字符",
        )

    # 验证配置完整性
    config = load_config()

    # 检查API密钥是否配置
    if not config.provider.api_key:
        raise HTTPException(
            status_code=400,
            detail="请先在配置页面设置API密钥",
        )

    # 检查是否已选择模型
    if not config.selected_model:
        raise HTTPException(
            status_code=400,
            detail="请先在配置页面选择一个AI模型",
        )

    # 检查base_url是否配置
    if not config.provider.base_url:
        raise HTTPException(
            status_code=400,
            detail="请先在配置页面设置API地址",
        )
    if not config.web_search.enabled or not config.web_search.tavily_api_key:
        raise HTTPException(
            status_code=400,
            detail="DG 分析必须先配置并启用 web_search 的 Tavily API Key",
        )

    logger.info("启动供应链分析: %s", query)

    # 返回SSE事件流
    return EventSourceResponse(
        _event_generator(query),
    )
