import client from './client'
import type { AppConfig } from '../types/config'

/**
 * 配置管理API模块
 * 提供应用配置的增删改查接口
 */

/**
 * 获取当前应用配置
 * @returns 完整的应用配置对象
 */
export async function getConfig(): Promise<AppConfig> {
  const res = await client.get<AppConfig>('/config')
  return res.data
}

/**
 * 更新应用配置（供应商和设置）
 * @param config - 需要更新的完整配置对象
 * @returns 更新后的配置对象
 */
export async function updateConfig(config: AppConfig): Promise<AppConfig> {
  const res = await client.put<AppConfig>('/config', config)
  return res.data
}

/**
 * 获取供应商可用的模型列表
 * 通过传入供应商地址和密钥，向后端发起模型列表查询
 * @param baseUrl - 供应商API基础地址
 * @param apiKey - 供应商API密钥
 * @returns 可用模型名称数组
 */
export async function fetchModels(baseUrl: string, apiKey: string): Promise<string[]> {
  const res = await client.post<{ models: string[] }>('/config/fetch-models', {
    base_url: baseUrl,
    api_key: apiKey,
  })
  return res.data.models
}

/**
 * 选择要使用的模型
 * @param model - 模型名称标识
 */
export async function selectModel(model: string): Promise<void> {
  await client.put('/config/select-model', { model })
}
