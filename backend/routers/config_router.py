"""
配置管理路由
提供AI模型供应商配置的CRUD接口，包括：
- 读取/更新应用配置
- 远端获取可用模型列表
- 选择当前使用的模型
"""
from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
import httpx

from backend.services.file_service import load_config, save_config
from backend.models.config_models import (
    AppConfig,
    FetchModelsRequest,
    PublicAppConfig,
    PublicProvider,
    SelectModelRequest,
)

# 创建路由实例，所有接口挂载在 /config 前缀下
router = APIRouter()

# httpx请求超时时间（秒）
_REQUEST_TIMEOUT = 30


def _public_config(config: AppConfig) -> PublicAppConfig:
    """转换为前端可见配置，隐藏api_key明文。"""
    return PublicAppConfig(
        provider=PublicProvider(
            name=config.provider.name,
            base_url=config.provider.base_url,
            has_api_key=bool(config.provider.api_key),
        ),
        selected_model=config.selected_model,
        available_models=config.available_models,
        settings=config.settings,
    )


def _validate_external_base_url(base_url: str) -> str:
    """限制模型列表请求目标，避免访问本机或内网地址。"""
    parsed = urlparse(base_url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=400, detail="base_url必须是https地址")
    try:
        host_ip = ip_address(parsed.hostname)
        if host_ip.is_private or host_ip.is_loopback or host_ip.is_link_local or host_ip.is_multicast:
            raise HTTPException(status_code=400, detail="base_url不能指向内网或本机地址")
    except ValueError:
        localhost_names = {"localhost", "localhost.localdomain"}
        if parsed.hostname.lower() in localhost_names or parsed.hostname.lower().endswith(".local"):
            raise HTTPException(status_code=400, detail="base_url不能指向本机地址")
    return base_url.rstrip("/")


@router.get("/", response_model=PublicAppConfig)
async def get_config() -> PublicAppConfig:
    """
    读取当前配置
    从本地config.json加载并返回完整的AppConfig
    """
    return _public_config(load_config())


@router.put("/", response_model=PublicAppConfig)
async def update_config(body: AppConfig) -> PublicAppConfig:
    """
    更新配置（仅更新provider和settings）
    保留现有的selected_model和available_models，
    防止前端意外覆盖模型选择状态
    """
    current = load_config()
    current.provider.name = body.provider.name.strip()
    current.provider.base_url = body.provider.base_url.strip().rstrip("/")
    current.provider.api_key = body.provider.api_key.strip() if body.provider.api_key else current.provider.api_key
    current.settings = body.settings
    save_config(current)
    return _public_config(load_config())


@router.post("/fetch-models")
async def fetch_models(body: FetchModelsRequest) -> dict:
    """
    获取远端可用模型列表
    向供应商的 /models 接口发起请求，
    解析OpenAI兼容格式的响应，提取模型ID列表
    成功后同步更新本地配置中的available_models
    """
    # 构造请求URL，去掉尾部斜杠避免双斜杠
    safe_base_url = _validate_external_base_url(body.base_url)
    url = f"{safe_base_url}/models"
    # 构造认证请求头
    headers = {"Authorization": f"Bearer {body.api_key}"}

    try:
        # 使用httpx异步客户端发起GET请求
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        # 连接或读取超时
        raise HTTPException(
            status_code=504,
            detail="请求模型列表超时，请检查base_url是否可达",
        )
    except httpx.ConnectError:
        # 无法建立连接
        raise HTTPException(
            status_code=502,
            detail="无法连接到供应商服务，请检查base_url",
        )
    except httpx.RequestError as exc:
        # 其他请求级别错误
        raise HTTPException(
            status_code=502,
            detail=f"请求失败: {exc}",
        )

    # 处理HTTP错误状态码
    if resp.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="认证失败，请检查api_key是否正确",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"供应商返回错误: {resp.text[:200]}",
        )

    # 解析响应JSON，提取模型ID列表
    try:
        data = resp.json()
        # OpenAI兼容格式: {"data": [{"id": "model-name"}, ...]}
        models = [item["id"] for item in data.get("data", [])]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="无法解析供应商返回的模型列表",
        )

    # 将获取到的模型列表同步更新到本地配置
    config = load_config()
    config.available_models = models
    save_config(config)

    return {"models": models}


@router.put("/select-model", response_model=PublicAppConfig)
async def select_model(body: SelectModelRequest) -> PublicAppConfig:
    """
    选择一个模型作为当前使用的模型
    将model id写入配置的selected_model字段并持久化
    """
    config = load_config()
    # 更新选中的模型
    config.selected_model = body.model
    # 持久化到文件
    save_config(config)
    return _public_config(config)
