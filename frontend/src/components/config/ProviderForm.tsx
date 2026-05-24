import { useState, useEffect } from 'react'
import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * AI模型供应商配置表单组件
 * 用于输入和保存供应商名称、API地址和密钥
 * 支持测试连接并获取可用模型列表
 */
export default function ProviderForm() {
  /* ---------- Store状态与操作 ---------- */
  const { config, updateProvider, fetchModels, fetchingModels } = useConfigStore()

  /* ---------- 本地表单状态 ---------- */
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')

  /**
   * 当远程配置加载完成后，同步供应商信息到本地表单
   */
  useEffect(() => {
    if (config?.provider) {
      setName(config.provider.name)
      setBaseUrl(config.provider.base_url)
      setApiKey('')
    }
  }, [config?.provider])

  /**
   * 保存供应商配置到后端
   * 校验必填字段后调用store方法提交
   */
  const handleSave = async () => {
    if (!baseUrl || (!apiKey && !config?.provider.has_api_key)) {
      toast.error('请填写API地址和密钥')
      return
    }
    await updateProvider({ name, base_url: baseUrl, api_key: apiKey })
    toast.success('供应商配置已保存')
  }

  /**
   * 测试连接并获取模型列表
   * 使用当前表单中的地址和密钥发起查询
   */
  const handleFetchModels = async () => {
    if (!baseUrl || !apiKey) {
      toast.error('请先填写API地址和密钥')
      return
    }
    try {
      const models = await fetchModels(baseUrl, apiKey)
      if (models.length > 0) {
        toast.success(`成功获取 ${models.length} 个模型`)
      } else {
        toast.error('未获取到可用模型')
      }
    } catch {
      toast.error('获取模型列表失败')
    }
  }

  /** 输入框通用内联样式 */
  const inputStyle = {
    backgroundColor: 'var(--color-bg-primary)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  }

  return (
    <div
      className="rounded-lg p-6 border"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* 卡片标题 */}
      <h3
        className="text-lg font-semibold mb-4"
        style={{ color: 'var(--color-text-primary)' }}
      >
        供应商配置
      </h3>

      {/* 供应商名称输入 */}
      <div className="mb-4">
        <label
          className="block text-sm mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          供应商名称
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="如：DeepSeek、OpenAI、通义千问"
          className="w-full px-3 py-2 rounded-md border text-sm"
          style={inputStyle}
        />
      </div>

      {/* API基础地址输入 */}
      <div className="mb-4">
        <label
          className="block text-sm mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Base URL
        </label>
        <input
          type="text"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.deepseek.com/v1"
          className="w-full px-3 py-2 rounded-md border text-sm"
          style={inputStyle}
        />
      </div>

      {/* API密钥输入（密码类型） */}
      <div className="mb-4">
        <label
          className="block text-sm mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          API Key
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={config?.provider.has_api_key ? '已保存，留空则不修改' : 'sk-...'}
          className="w-full px-3 py-2 rounded-md border text-sm"
          style={inputStyle}
        />
      </div>

      {/* 操作按钮区域 */}
      <div className="flex gap-3">
        {/* 保存按钮 */}
        <button
          onClick={handleSave}
          className="px-4 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--color-accent)' }}
        >
          保存配置
        </button>
        {/* 获取模型列表按钮 */}
        <button
          onClick={handleFetchModels}
          disabled={fetchingModels}
          className="px-4 py-2 rounded-md text-sm font-medium border"
          style={{
            borderColor: 'var(--color-accent)',
            color: 'var(--color-accent)',
            opacity: fetchingModels ? 0.5 : 1,
          }}
        >
          {fetchingModels ? '获取中...' : '获取模型列表'}
        </button>
      </div>
    </div>
  )
}
