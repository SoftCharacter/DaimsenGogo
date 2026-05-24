"""
配置数据模型
定义AI模型供应商、应用设置等配置结构
"""
from pydantic import BaseModel, Field


class Provider(BaseModel):
    """AI模型供应商配置"""
    name: str = ""           # 供应商名称，如 DeepSeek、OpenAI
    base_url: str = ""       # API基础地址，如 https://api.deepseek.com/v1
    api_key: str = ""        # API密钥


class Settings(BaseModel):
    """应用全局设置"""
    temperature: float = 0.3           # LLM温度参数，越低越确定
    max_tokens: int = 4096             # LLM最大输出token数
    stock_refresh_interval_seconds: int = 30  # 行情刷新间隔（秒）


class AppConfig(BaseModel):
    """完整的应用配置"""
    provider: Provider = Provider()           # AI供应商信息
    selected_model: str = ""                  # 当前选中的模型ID
    available_models: list[str] = []          # 可用模型列表
    settings: Settings = Settings()           # 全局设置


class PublicProvider(BaseModel):
    """返回给前端的供应商配置，隐藏密钥明文。"""
    name: str = ""
    base_url: str = ""
    api_key: str = Field(default="", exclude=True)
    has_api_key: bool = False


class PublicAppConfig(BaseModel):
    """返回给前端的应用配置，避免泄露api_key。"""
    provider: PublicProvider = PublicProvider()
    selected_model: str = ""
    available_models: list[str] = []
    settings: Settings = Settings()


class FetchModelsRequest(BaseModel):
    """获取模型列表请求"""
    base_url: str    # API基础地址
    api_key: str     # API密钥


class SelectModelRequest(BaseModel):
    """选择模型请求"""
    model: str       # 要选择的模型ID
