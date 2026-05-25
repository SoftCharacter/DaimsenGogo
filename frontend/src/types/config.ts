/**
 * AI模型供应商配置接口
 */
export interface Provider {
  name: string;        // 供应商名称，如 DeepSeek
  base_url: string;    // API基础地址
  api_key?: string;    // 仅提交时使用，后端不会回显
  has_api_key?: boolean; // 后端是否已保存密钥
}

/**
 * 应用全局设置
 */
export interface Settings {
  temperature: number;                    // LLM温度参数
  max_tokens: number;                     // 最大输出token数
  stock_refresh_interval_seconds: number; // 行情刷新间隔
}

/**
 * 完整应用配置
 */
export interface AppConfig {
  provider: Provider;
  selected_model: string;
  available_models: string[];
  settings: Settings;
}
