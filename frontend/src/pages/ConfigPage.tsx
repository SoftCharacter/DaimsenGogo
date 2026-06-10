import { useEffect } from 'react'
import { useConfigStore } from '../stores/configStore'
import ProviderForm from '../components/config/ProviderForm'
import ModelSelector from '../components/config/ModelSelector'
import WebSearchForm from '../components/config/WebSearchForm'

/**
 * 模型配置页面（高保真重构）
 * 居中 max-width 980，双栏 grid：左「供应商配置」表单 + 右「可用模型」单选列表。
 * 页面挂载时加载配置。
 */
export default function ConfigPage() {
  const { loadConfig, loading, error } = useConfigStore()
  const config = useConfigStore((s) => s.config)

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '36px 0' }}>
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '0 32px' }}>
        {/* 标题 */}
        <div className="fade-in" style={{ marginBottom: 24 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.22em', color: 'var(--accent-bright)' }}>
            SETTINGS
          </span>
          <h1 style={{ fontSize: 26, fontWeight: 700, margin: '8px 0 4px' }}>模型配置</h1>
          <p style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>
            配置 AI 供应商接入信息，并选择用于盘面洞察与供应链拆解的模型。
          </p>
        </div>

        {error && (
          <div
            style={{
              marginBottom: 16,
              padding: '12px 14px',
              borderRadius: 'var(--r-sm)',
              fontSize: 13,
              background: 'var(--up-soft)',
              color: 'var(--up)',
              border: '1px solid var(--up)',
            }}
          >
            {error}
          </div>
        )}

        {loading && !config ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-faint)' }}>加载配置中...</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start' }}>
            <div style={{ display: 'grid', gap: 18 }}>
              <ProviderForm />
              <WebSearchForm />
            </div>
            <ModelSelector />
          </div>
        )}
      </div>
    </div>
  )
}
