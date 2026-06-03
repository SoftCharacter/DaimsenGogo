import { useState, useEffect, type CSSProperties } from 'react'
import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * 供应商配置表单（高保真重构）
 * .panel：圆点 + 标题；字段 供应商名称 / Base URL(等宽) / API Key(password)；
 * 按钮 保存配置(渐变) / 获取模型列表(描边)。逻辑与原实现一致。
 */

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
  mono,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  mono?: boolean
}) {
  const [focused, setFocused] = useState(false)
  const inputStyle: CSSProperties = {
    width: '100%',
    border: `1px solid ${focused ? 'var(--accent-line)' : 'var(--border)'}`,
    background: 'var(--surface-2)',
    borderRadius: 'var(--r-sm)',
    padding: '11px 13px',
    color: 'var(--text)',
    fontSize: 13.5,
    fontFamily: mono ? 'var(--font-mono)' : 'var(--font-cjk)',
    outline: 'none',
    transition: 'border-color 0.2s',
  }
  return (
    <label style={{ display: 'block', marginBottom: 15 }}>
      <span style={{ display: 'block', fontSize: 11.5, fontWeight: 600, color: 'var(--text-faint)', marginBottom: 7, letterSpacing: '0.04em' }}>
        {label}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        type={type}
        style={inputStyle}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
    </label>
  )
}

export default function ProviderForm() {
  const { config, updateProvider, fetchModels, fetchingModels } = useConfigStore()

  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    if (config?.provider) {
      setName(config.provider.name)
      setBaseUrl(config.provider.base_url)
      setApiKey('')
    }
  }, [config?.provider])

  const handleSave = async () => {
    if (!baseUrl || (!apiKey && !config?.provider.has_api_key)) {
      toast.error('请填写API地址和密钥')
      return
    }
    await updateProvider({ name, base_url: baseUrl, api_key: apiKey })
    toast.success('供应商配置已保存')
  }

  const handleFetchModels = async () => {
    if (!baseUrl || !apiKey) {
      toast.error('请先填写API地址和密钥')
      return
    }
    try {
      const models = await fetchModels(baseUrl, apiKey)
      if (models.length > 0) toast.success(`成功获取 ${models.length} 个模型`)
      else toast.error('未获取到可用模型')
    } catch {
      toast.error('获取模型列表失败')
    }
  }

  return (
    <div className="panel fade-in" style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 18 }}>
        <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>供应商配置</h2>
      </div>

      <Field label="供应商名称" value={name} onChange={setName} placeholder="如：DeepSeek、OpenAI、通义千问" />
      <Field label="Base URL" value={baseUrl} onChange={setBaseUrl} placeholder="https://api.deepseek.com/v1" mono />
      <Field
        label="API Key"
        value={apiKey}
        onChange={setApiKey}
        type="password"
        mono
        placeholder={config?.provider.has_api_key ? '已保存，留空则不修改' : 'sk-...'}
      />

      <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
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
          保存配置
        </button>
        <button
          onClick={handleFetchModels}
          disabled={fetchingModels}
          className="card"
          style={{
            cursor: fetchingModels ? 'not-allowed' : 'pointer',
            borderRadius: 'var(--r-sm)',
            padding: '10px 20px',
            fontFamily: 'var(--font-cjk)',
            fontWeight: 600,
            fontSize: 13.5,
            color: 'var(--accent-bright)',
            background: 'transparent',
            borderColor: 'var(--accent-line)',
            opacity: fetchingModels ? 0.6 : 1,
          }}
        >
          {fetchingModels ? '获取中...' : '获取模型列表'}
        </button>
      </div>
    </div>
  )
}
