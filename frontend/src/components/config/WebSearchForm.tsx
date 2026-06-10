import { useState } from 'react'
import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * 网页搜索配置表单
 * 控制供应链分析流程是否允许调用 Tavily 网页搜索。
 */
export default function WebSearchForm() {
  const { config, updateWebSearch } = useConfigStore()
  const [tavilyApiKey, setTavilyApiKey] = useState('')

  /**
   * 保存开关和可选的新 Tavily Key。
   */
  const handleSave = async () => {
    if (!tavilyApiKey && !config?.web_search.has_tavily_api_key) {
      toast.error('DG 分析必须填写 Tavily API Key')
      return
    }
    await updateWebSearch({ enabled: true, tavily_api_key: tavilyApiKey })
    setTavilyApiKey('')
    toast.success('网页搜索配置已保存')
  }

  return (
    <div className="panel fade-in" style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 18 }}>
        <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>网页搜索</h2>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginBottom: 15 }}>
        <span>
          <span style={{ display: 'block', fontSize: 13.5, fontWeight: 700, color: 'var(--text)' }}>web_search 必需</span>
          <span style={{ display: 'block', fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>
            DG 分析会在线索捕获、业务确证和递归补搜步骤使用公开网页证据；未配置 Key 时无法开始分析。
          </span>
        </span>
        <span
          style={{
            flex: 'none',
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--accent-bright)',
            background: 'var(--accent-soft)',
            padding: '4px 9px',
            borderRadius: 'var(--r-sm)',
            whiteSpace: 'nowrap',
          }}
        >
          必选
        </span>
      </div>

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
            background: 'var(--surface-2)',
            borderRadius: 'var(--r-sm)',
            padding: '11px 13px',
            color: 'var(--text)',
            fontSize: 13.5,
            fontFamily: 'var(--font-mono)',
            outline: 'none',
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
