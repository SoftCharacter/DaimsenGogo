"""
文件服务
负责data/目录下JSON文件的读写操作
所有数据持久化通过本模块完成
"""
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from backend.models.config_models import AppConfig
from backend.models.theme_models import Theme, ThemeSummary
from backend.services import config_service

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


@dataclass(frozen=True)
class DeleteThemeResult:
    deleted: bool
    source_task_id: str
    task_cache_removed: bool

def _sync_config_service_paths() -> None:
    """同步兼容入口路径到配置服务，支持测试替换临时目录。"""
    config_service.DATA_DIR = DATA_DIR
    config_service.ROOT_DIR = ROOT_DIR
    config_service.CONFIG_PATH = CONFIG_PATH
    config_service.ENV_PATH = ENV_PATH


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
    """兼容旧入口，读取合成后的完整应用配置。"""
    _sync_config_service_paths()
    return config_service.load_config()


def save_config(config: AppConfig) -> None:
    """兼容旧入口，保存应用配置到 .env 和 config.json。"""
    _sync_config_service_paths()
    config_service.save_config(config)


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


def delete_theme_with_cache_result(theme_id: str) -> DeleteThemeResult:
    """删除主题文件，并返回来源任务缓存目录是否被清理。"""
    theme = load_theme(theme_id)
    path = _safe_json_path(THEMES_DIR, theme_id)
    if not path.exists():
        return DeleteThemeResult(False, "", False)
    path.unlink()
    source_task_id = theme.source_task_id if theme and theme.source_task_id else ""
    cache_removed = False
    if source_task_id:
        cache_path = _safe_task_cache_path(source_task_id)
        if cache_path.exists():
            shutil.rmtree(cache_path)
            cache_removed = True
    return DeleteThemeResult(True, source_task_id, cache_removed)


def delete_theme(theme_id: str) -> bool:
    """
    删除主题文件和来源任务缓存目录
    返回True表示删除成功，False表示文件不存在
    """
    return delete_theme_with_cache_result(theme_id).deleted


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
