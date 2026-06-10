"""应用配置读写服务。"""
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key

from backend.models.config_models import AppConfig

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
ROOT_DIR = DATA_DIR.parent
CONFIG_PATH = DATA_DIR / "config.json"
ENV_PATH = ROOT_DIR / ".env"
ENV_PROVIDER_NAME_KEYS = ("LLM_PROVIDER_NAME", "MODEL_PROVIDER_NAME", "OPENAI_PROVIDER_NAME")
ENV_BASE_URL_KEYS = ("LLM_BASE_URL", "MODEL_BASE_URL", "OPENAI_BASE_URL", "BASE_URL")
ENV_API_KEY_KEYS = ("LLM_API_KEY", "MODEL_API_KEY", "OPENAI_API_KEY", "API_KEY")
ENV_MODEL_KEYS = ("LLM_MODEL", "MODEL_NAME", "OPENAI_MODEL")
ENV_WEB_SEARCH_ENABLED_KEY = "WEB_SEARCH_ENABLED"
ENV_TAVILY_API_KEY = "TAVILY_API_KEY"
ENV_PLACEHOLDER_VALUES = {
    "https://your-provider.example.com/v1",
}


def load_persisted_config() -> AppConfig:
    """读取 data/config.json 中的非敏感持久化配置。"""
    if not CONFIG_PATH.exists():
        return AppConfig()
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    return AppConfig.model_validate_json(raw)


def load_env_overrides() -> dict[str, str]:
    """读取项目 .env 和进程环境变量中的模型连接配置。"""
    load_dotenv(ENV_PATH, override=True)
    return {
        "provider_name": _env_value(*ENV_PROVIDER_NAME_KEYS),
        "base_url": _env_value(*ENV_BASE_URL_KEYS),
        "api_key": _env_value(*ENV_API_KEY_KEYS),
        "model": _env_value(*ENV_MODEL_KEYS),
        "tavily_api_key": _env_value(ENV_TAVILY_API_KEY),
    }


def merge_config_with_env(config: AppConfig, env: dict[str, str]) -> AppConfig:
    """用环境变量覆盖本地 JSON 配置，保持当前覆盖规则不变。"""
    model = env["model"]
    normalized_base_url = env["base_url"].rstrip("/") if env["base_url"] else ""

    config.provider.name = env["provider_name"]
    config.provider.base_url = normalized_base_url
    config.provider.api_key = env["api_key"]
    config.selected_model = model
    config.web_search.tavily_api_key = env["tavily_api_key"]
    config.web_search.enabled = True
    if model:
        if "xiaomimimo.com" in normalized_base_url:
            model = model.lower()
            config.selected_model = model
        if model not in config.available_models:
            config.available_models = [*config.available_models, model]
    return config


def load_config() -> AppConfig:
    """读取合成后的完整应用配置。"""
    return merge_config_with_env(load_persisted_config(), load_env_overrides())


def save_public_config_and_secrets(config: AppConfig) -> None:
    """保存配置：敏感连接信息写 .env，非敏感配置写 JSON。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sync_config_to_env(
        config,
        update_api_key=bool(config.provider.api_key),
        update_tavily_api_key=bool(config.web_search.tavily_api_key),
    )
    persisted = config.model_copy(deep=True)
    persisted.provider.name = ""
    persisted.provider.base_url = ""
    persisted.provider.api_key = ""
    persisted.selected_model = ""
    persisted.web_search.tavily_api_key = ""
    CONFIG_PATH.write_text(
        persisted.model_dump_json(indent=2),
        encoding="utf-8",
    )


def save_config(config: AppConfig) -> None:
    """兼容旧函数名，保存应用配置。"""
    save_public_config_and_secrets(config)


def sync_config_to_env(
    config: AppConfig,
    *,
    update_api_key: bool = True,
    update_tavily_api_key: bool = True,
) -> None:
    """把模型配置同步写回 .env，保留 .env 中的其他变量。"""
    _write_env_value("LLM_PROVIDER_NAME", config.provider.name.strip())
    _write_env_value("LLM_BASE_URL", config.provider.base_url.strip().rstrip("/"))
    if update_api_key and config.provider.api_key:
        _write_env_value("LLM_API_KEY", config.provider.api_key.strip())
    _write_env_value("LLM_MODEL", config.selected_model.strip())
    _write_env_value(ENV_WEB_SEARCH_ENABLED_KEY, "true")
    if update_tavily_api_key and config.web_search.tavily_api_key:
        _write_env_value(ENV_TAVILY_API_KEY, config.web_search.tavily_api_key.strip())


def _env_value(*names: str) -> str:
    file_values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    for name in names:
        file_value = file_values.get(name)
        if file_value is not None and str(file_value).strip():
            value = str(file_value).strip()
            if value not in ENV_PLACEHOLDER_VALUES:
                return value
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            value = value.strip()
            if value not in ENV_PLACEHOLDER_VALUES:
                return value
    return ""


def _write_env_value(key: str, value: str) -> None:
    ENV_PATH.touch(exist_ok=True)
    set_key(str(ENV_PATH), key, value, quote_mode="always")
