import { useEffect, useState } from 'react'
import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * 网页搜索配置表单
 * 控制供应链分析流程是否允许调用 Tavily 网页搜索。
 */
export default function WebSearchForm() {
  const { config, updateWebSearch } = useConfigStore()
  const [enabled, setEnabled] = useState(false)
  const [tavilyApiKey, setTavilyApiKey] = useState('')

  /**
   * 后端不会回显密钥明文，只同步开关状态并清空输入框。
   */
  useEffect(() => {
    if (config?.web_search) {
      setEnabled(config.web_search.enabled)
      setTavilyApiKey('')
    }
  }, [config?.web_search])

  /**
   * 保存开关和可选的新 Tavily Key。
   */
  const handleSave = async () => {
    if (enabled && !tavilyApiKey && !config?.web_search.has_tavily_api_key) {
      toast.error('开启网页搜索时请填写 Tavily API Key')
      return
    }
    await updateWebSearch({ enabled, tavily_api_key: tavilyApiKey })
    toast.success(enabled ? '网页搜索已开启' : '网页搜索已关闭')
  }

  return (
    <div className="panel fade-in" style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 18 }}>
        <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>网页搜索</h2>
      </div>

      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginBottom: 15 }}>
        <span>
          <span style={{ display: 'block', fontSize: 13.5, fontWeight: 700, color: 'var(--text)' }}>启用 web_search</span>
          <span style={{ display: 'block', fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>
            在线索捕获、业务确证和递归补搜步骤作为公开网页证据补强，关闭后即使 .env 有 Key 也不会使用。
          </span>
        </span>
        <input
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          type="checkbox"
          style={{ width: 18, height: 18, accentColor: 'var(--accent)' }}
        />
      </label>

      <label style={{ display: 'block', marginBottom: 15 }}>
        <span style={{ display: 'block', fontSize: 11.5, fontWeight: 600, color: 'var(--text-faint)', marginBottom: 7, letterSpacing: '0.04em' }}>
          Tavily API Key
        </span>
        <input
          value={tavilyApiKey}
          onChange={(e) => setTavilyApiKey(e.target.value)}
          type="password"
          placeholder={config?.web_search.has_tavily_api_key ? '已保存，留空则不修改' : 'tvly-...'}
          style={{
            width: '100%',
            border: '1px solid var(--border)',
            background: enabled ? 'var(--surface-2)' : 'var(--surface)',
            borderRadius: 'var(--r-sm)',
            padding: '11px 13px',
            color: 'var(--text)',
            fontSize: 13.5,
            fontFamily: 'var(--font-mono)',
            outline: 'none',
            opacity: enabled ? 1 : 0.65,
          }}
        />
      </label>

      <button
        onClick={handleSave}
        style={{
          cursor: 'pointer',
          border: 'none',
          borderRadius: 'var(--r-sm)',
          padding: '10px 22px',
          fontFamily: 'var(--font-cjk)',
          fontWeight: 700,
          fontSize: 13.5,
          color: '#fff',
          background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
          boxShadow: '0 10px 22px -12px var(--accent)',
        }}
      >
        保存网页搜索配置
      </button>
    </div>
  )
}
