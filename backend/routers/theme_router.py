"""
主题管理路由
提供分析主题的完整CRUD接口
路由前缀在main.py中配置为 /api/themes
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.models.theme_models import Theme, ThemeSummary
from backend.services.analysis_task_service import set_task_saved_theme
from backend.services.file_service import (
    load_theme,
    save_theme,
    delete_theme_with_cache_result,
    list_themes,
)

# 创建路由器实例
router = APIRouter()


@router.get("/", response_model=list[ThemeSummary])
async def get_themes():
    """
    列出所有主题摘要
    返回按更新时间倒序排列的主题列表
    仅包含摘要信息(id/name/description/updated_at)
    """
    return list_themes()


@router.get("/{theme_id}", response_model=Theme)
async def get_theme(theme_id: str):
    """
    获取指定主题的完整详情
    参数:
      theme_id - 主题唯一标识
    异常:
      404 - 主题不存在
    """
    theme = load_theme(theme_id)
    if not theme:
        raise HTTPException(
            status_code=404,
            detail=f"主题 {theme_id} 不存在",
        )
    return theme


@router.post("/", response_model=Theme, status_code=201)
async def create_theme(body: Theme):
    """
    创建新主题
    自动生成以下字段:
      - id: UUID格式的唯一标识
      - created_at: 当前UTC时间
      - updated_at: 当前UTC时间
    请求体中传入的id/created_at/updated_at会被覆盖
    """
    # 生成唯一ID和时间戳
    now = datetime.now(timezone.utc).isoformat()
    body.id = uuid.uuid4().hex[:12]
    body.created_at = now
    body.updated_at = now
    # 持久化到文件
    save_theme(body)
    if body.source_task_id:
        set_task_saved_theme(body.source_task_id, body.id)
    return body


@router.put("/{theme_id}", response_model=Theme)
async def update_theme(theme_id: str, body: Theme):
    """
    更新已有主题
    参数:
      theme_id - 要更新的主题ID
      body     - 新的主题数据
    逻辑:
      - 先检查主题是否存在
      - 保留原始的id和created_at
      - 自动更新updated_at为当前时间
    异常:
      404 - 目标主题不存在
    """
    existing = load_theme(theme_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"主题 {theme_id} 不存在",
        )
    # 保持原始ID和创建时间不变
    body.id = theme_id
    body.created_at = existing.created_at
    # 更新时间设为当前UTC时间
    body.updated_at = datetime.now(timezone.utc).isoformat()
    # 持久化更新后的数据
    save_theme(body)
    return body


@router.delete("/{theme_id}")
async def remove_theme(theme_id: str):
    """
    删除指定主题
    参数:
      theme_id - 要删除的主题ID
    返回:
      删除成功的确认消息
    异常:
      404 - 目标主题不存在
    """
    result = delete_theme_with_cache_result(theme_id)
    if not result.deleted:
        raise HTTPException(
            status_code=404,
            detail=f"主题 {theme_id} 不存在",
        )
    return {
        "message": f"主题 {theme_id} 已删除",
        "source_task_id": result.source_task_id,
        "task_cache_removed": result.task_cache_removed,
    }
