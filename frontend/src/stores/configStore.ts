import { create } from 'zustand'
import type { AppConfig, Provider, Settings } from '../types/config'
import * as configApi from '../api/configApi'

/**
 * 配置Store状态接口
 * 定义配置管理相关的状态和操作方法
 */
interface ConfigState {
  config: AppConfig | null    // 当前应用配置
  loading: boolean            // 是否正在加载配置
  fetchingModels: boolean     // 是否正在获取模型列表
  error: string | null        // 错误信息

  /** 加载远程配置 */
  loadConfig: () => Promise<void>
  /** 更新供应商信息 */
  updateProvider: (provider: Provider) => Promise<void>
  /** 更新应用设置 */
  updateSettings: (settings: Settings) => Promise<void>
  /** 获取可用模型列表 */
  fetchModels: (baseUrl: string, apiKey: string) => Promise<string[]>
  /** 选择指定模型 */
  selectModel: (model: string) => Promise<void>
}

/**
 * 配置状态管理Store
 * 使用zustand管理全局配置状态，包含供应商、模型和设置
 */
export const useConfigStore = create<ConfigState>((set, get) => ({
  /* ---------- 初始状态 ---------- */
  config: null,
  loading: false,
  fetchingModels: false,
  error: null,

  /**
   * 从后端加载完整配置
   * 设置loading状态，失败时记录错误信息
   */
  loadConfig: async () => {
    set({ loading: true, error: null })
    try {
      const config = await configApi.getConfig()
      set({ config, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  /**
   * 更新供应商配置
   * 合并当前配置与新供应商信息后提交到后端
   * @param provider - 新的供应商配置
   */
  updateProvider: async (provider: Provider) => {
    const current = get().config
    if (!current) return
    const updated = { ...current, provider }
    try {
      const result = await configApi.updateConfig(updated)
      set({ config: result })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  /**
   * 更新应用设置（温度、token数、刷新间隔等）
   * @param settings - 新的设置参数
   */
  updateSettings: async (settings: Settings) => {
    const current = get().config
    if (!current) return
    const updated = { ...current, settings }
    try {
      const result = await configApi.updateConfig(updated)
      set({ config: result })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  /**
   * 获取供应商可用模型列表
   * 同时更新本地的available_models字段
   * @param baseUrl - API基础地址
   * @param apiKey - API密钥
   * @returns 模型名称数组
   */
  fetchModels: async (baseUrl: string, apiKey: string) => {
    set({ fetchingModels: true, error: null })
    try {
      const models = await configApi.fetchModels(baseUrl, apiKey)
      // 将获取到的模型列表同步到本地配置状态
      const current = get().config
      if (current) {
        set({ config: { ...current, available_models: models } })
      }
      return models
    } catch (e: any) {
      set({ error: e.message })
      return []
    } finally {
      // 无论成功失败，重置获取状态
      set({ fetchingModels: false })
    }
  },

  /**
   * 选择要使用的模型
   * 更新后端选中模型并同步本地状态
   * @param model - 模型名称
   */
  selectModel: async (model: string) => {
    try {
      await configApi.selectModel(model)
      // 同步本地配置中的选中模型
      const current = get().config
      if (current) {
        set({ config: { ...current, selected_model: model } })
      }
    } catch (e: any) {
      set({ error: e.message })
    }
  },
}))
