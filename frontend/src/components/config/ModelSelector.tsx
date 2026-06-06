import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * 可用模型列表（高保真重构）
 * .panel：圆点 + 标题 + 「N 个」计数；列表项 = 单选圆点 + 等宽模型名 +
 * 选中项「当前使用」徽标，选中行 accent-soft 底。
 */
export default function ModelSelector() {
  const { config, selectModel } = useConfigStore()
  const models = config?.available_models || []
  const selectedModel = config?.selected_model || ''

  const handleSelect = async (model: string) => {
    await selectModel(model)
    toast.success(`已选择模型: ${model}`)
  }

  return (
    <div className="panel fade-in" style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>可用模型</h2>
        </div>
        <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{models.length} 个</span>
      </div>

      {models.length === 0 ? (
        <p style={{ fontSize: 13, color: 'var(--text-faint)' }}>请先配置供应商并获取模型列表</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {models.map((model) => {
            const on = model === selectedModel
            return (
              <button
                key={model}
                onClick={() => void handleSelect(model)}
                className="card"
                style={{
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: '13px 15px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  background: on ? 'var(--accent-soft)' : 'var(--surface)',
                  borderColor: on ? 'var(--accent-line)' : 'var(--border)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 0 }}>
                  <span
                    style={{
                      width: 16,
                      height: 16,
                      flex: 'none',
                      borderRadius: 99,
                      border: `2px solid ${on ? 'var(--accent-bright)' : 'var(--border-strong)'}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {on && <span style={{ width: 7, height: 7, borderRadius: 99, background: 'var(--accent-bright)' }} />}
                  </span>
                  <span
                    className="mono"
                    style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    {model}
                  </span>
                </div>
                {on && (
                  <span
                    style={{
                      flex: 'none',
                      fontSize: 10.5,
                      fontWeight: 700,
                      color: '#fff',
                      background: 'var(--accent)',
                      padding: '3px 9px',
                      borderRadius: 99,
                    }}
                  >
                    当前使用
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
