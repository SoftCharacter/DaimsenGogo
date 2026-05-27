"""
文件服务
负责data/目录下JSON文件的读写操作
所有数据持久化通过本模块完成
"""
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from backend.models.config_models import AppConfig
from backend.models.theme_models import Theme, ThemeSummary

# 数据目录：项目根目录下的data/
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
ROOT_DIR = DATA_DIR.parent
# 配置文件路径
CONFIG_PATH = DATA_DIR / "config.json"
# 主题文件夹路径
THEMES_DIR = DATA_DIR / "themes"
TASK_CACHE_DIR = DATA_DIR / "task_cache"
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ENV_PATH = ROOT_DIR / ".env"


def _load_local_env() -> None:
    """加载项目根目录.env，支持任意OpenAI兼容大模型供应商。"""
    load_dotenv(ENV_PATH, override=True)


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def _apply_env_config(config: AppConfig) -> AppConfig:
    """用.env覆盖本地JSON配置，兼容多种大模型环境变量命名。"""
    _load_local_env()
    provider_name = _env_value("LLM_PROVIDER_NAME", "MODEL_PROVIDER_NAME", "OPENAI_PROVIDER_NAME")
    base_url = _env_value("LLM_BASE_URL", "MODEL_BASE_URL", "OPENAI_BASE_URL", "BASE_URL")
    api_key = _env_value("LLM_API_KEY", "MODEL_API_KEY", "OPENAI_API_KEY", "API_KEY")
    model = _env_value("LLM_MODEL", "MODEL_NAME", "OPENAI_MODEL")
    normalized_base_url = base_url.rstrip("/") if base_url else ""

    if provider_name:
        config.provider.name = provider_name
    if base_url:
        config.provider.base_url = normalized_base_url
    if api_key:
        config.provider.api_key = api_key
    if model:
        if "xiaomimimo.com" in (normalized_base_url or config.provider.base_url):
            model = model.lower()
        config.selected_model = model
        if model not in config.available_models:
            config.available_models = [*config.available_models, model]
    return config


def _safe_json_path(base_dir: Path, item_id: str) -> Path:
    """校验资源ID并返回限定在目录内的JSON路径"""
    if not _SAFE_ID_PATTERN.fullmatch(item_id):
        raise ValueError("资源ID格式不合法")
    path = (base_dir / f"{item_id}.json").resolve()
    base = base_dir.resolve()
    if path.parent != base:
        raise ValueError("资源路径越界")
    return path


def _safe_task_cache_path(task_id: str) -> Path:
    """校验任务ID并返回限定在任务缓存目录内的路径"""
    if not _SAFE_ID_PATTERN.fullmatch(task_id):
        raise ValueError("任务ID格式不合法")
    path = (TASK_CACHE_DIR / task_id).resolve()
    base = TASK_CACHE_DIR.resolve()
    if path.parent != base:
        raise ValueError("任务缓存路径越界")
    return path


def ensure_dirs() -> None:
    """确保数据目录结构存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THEMES_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """
    读取应用配置
    如果配置文件不存在则返回默认配置
    """
    if not CONFIG_PATH.exists():
        return _apply_env_config(AppConfig())
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    return _apply_env_config(AppConfig.model_validate_json(raw))


def save_config(config: AppConfig) -> None:
    """保存应用配置到config.json"""
    ensure_dirs()
    persisted = config.model_copy(deep=True)
    if _env_value("LLM_API_KEY", "MODEL_API_KEY", "OPENAI_API_KEY", "API_KEY"):
        persisted.provider.api_key = ""
    CONFIG_PATH.write_text(
        persisted.model_dump_json(indent=2),
        encoding="utf-8",
    )


def load_theme(theme_id: str) -> Optional[Theme]:
    """
    读取指定主题
    返回None表示主题不存在
    """
    path = _safe_json_path(THEMES_DIR, theme_id)
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    return Theme.model_validate_json(raw)


def save_theme(theme: Theme) -> None:
    """保存主题到JSON文件"""
    ensure_dirs()
    path = _safe_json_path(THEMES_DIR, theme.id)
    path.write_text(
        theme.model_dump_json(indent=2),
        encoding="utf-8",
    )


def delete_theme(theme_id: str) -> bool:
    """
    删除主题文件和来源任务缓存目录
    返回True表示删除成功，False表示文件不存在
    """
    theme = load_theme(theme_id)
    path = _safe_json_path(THEMES_DIR, theme_id)
    if not path.exists():
        return False
    path.unlink()
    if theme and theme.source_task_id:
        cache_path = _safe_task_cache_path(theme.source_task_id)
        if cache_path.exists():
            shutil.rmtree(cache_path)
    return True


def list_themes() -> list[ThemeSummary]:
    """
    列出所有主题的摘要信息
    按更新时间倒序排列
    """
    ensure_dirs()
    summaries: list[ThemeSummary] = []
    # 遍历主题目录下所有JSON文件
    for path in THEMES_DIR.glob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            # 仅提取摘要字段，避免加载完整数据
            summaries.append(ThemeSummary(
                id=data.get("id", path.stem),
                name=data.get("name", ""),
                description=data.get("description", ""),
                updated_at=data.get("updated_at", ""),
            ))
        except (json.JSONDecodeError, KeyError):
            continue  # 跳过损坏的文件
    # 按更新时间倒序排列
    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries
