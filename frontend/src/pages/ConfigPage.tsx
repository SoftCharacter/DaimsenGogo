import { useEffect } from 'react'
import { useConfigStore } from '../stores/configStore'
import ProviderForm from '../components/config/ProviderForm'
import ModelSelector from '../components/config/ModelSelector'

export default function ConfigPage() {
  const { loadConfig, loading, error } = useConfigStore()

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  /* ---------- 加载中占位 ---------- */
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p style={{ color: 'var(--color-text-muted)' }}>加载配置中...</p>
      </div>
    )
  }

  /* ---------- 页面主体 ---------- */
  return (
    <div className="max-w-2xl mx-auto p-6">
      {/* 页面标题 */}
      <h2
        className="text-xl font-bold mb-6"
        style={{ color: 'var(--color-text-primary)' }}
      >
        模型配置
      </h2>

      {/* 错误提示横幅 - 仅在有错误时显示 */}
      {error && (
        <div
          className="mb-4 p-3 rounded-md text-sm"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: 'var(--color-stock-up)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          {error}
        </div>
      )}

      {/* 配置区块容器：供应商表单 + 模型选择器 */}
      <div className="space-y-6">
        <ProviderForm />
        <ModelSelector />
      </div>
    </div>
  )
}
