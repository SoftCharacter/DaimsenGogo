"""
股票供应链大屏 - FastAPI后端入口
提供AI分析、行情代理、主题管理等API服务
支持前端心跳检测，浏览器关闭后自动退出释放端口
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.services.file_service import ensure_dirs
from backend.routers import config_router, analysis_router, theme_router, stock_router, analysis_task_router

logger = logging.getLogger(__name__)
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

# 最后一次心跳时间戳，用于健康记录，不再触发自动退出
_last_heartbeat: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时创建数据目录，并根据环境变量决定是否启动心跳监控。
    """
    global _last_heartbeat
    ensure_dirs()
    # 复位上次异常退出/连接中断遗留的孤儿分析任务（running → paused），可继续执行
    try:
        from backend.services.analysis_task_service import reconcile_running_tasks
        recovered = reconcile_running_tasks()
        if recovered:
            logger.info("启动复位中断的分析任务：%d 个", recovered)
    except Exception as exc:
        logger.warning("复位中断分析任务失败：%s", exc)
    _last_heartbeat = time.time()

    # 功能可用优先：不再因心跳超时自动关闭后端，避免浏览器后台节流导致误杀进程。
    # 进程清理由scripts/launcher.py在Ctrl+C或前端进程退出时统一处理。
    yield


# 创建FastAPI应用实例
app = FastAPI(
    title="股票供应链大屏",
    description="基于ReAct Agent的股票供应链分析和可视化平台",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置CORS - 默认仅允许本地前端，可通过环境变量覆盖
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/heartbeat")
async def heartbeat():
    """
    心跳端点 - 前端定期调用以保持后端存活
    每次调用刷新最后心跳时间戳
    """
    global _last_heartbeat
    _last_heartbeat = time.time()
    return {"status": "ok"}


# 注册路由模块
app.include_router(config_router.router, prefix="/api/config", tags=["配置管理"])
app.include_router(analysis_router.router, prefix="/api/analysis", tags=["AI分析"])
app.include_router(analysis_task_router.router, prefix="/api/analysis-tasks", tags=["分析任务"])
app.include_router(theme_router.router, prefix="/api/themes", tags=["主题管理"])
app.include_router(stock_router.router, prefix="/api/stocks", tags=["行情数据"])
