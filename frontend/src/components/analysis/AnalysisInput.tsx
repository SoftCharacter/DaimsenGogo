import { useState, useCallback, useEffect } from 'react'

interface AnalysisInputProps {
  onSubmit: (query: string) => void
  isRunning: boolean
}

const EXAMPLE_QUERIES = [
  '华为昇腾芯片供应链',
  '苹果Vision Pro产业链',
  '宁德时代电池供应链',
  '比亚迪智能驾驶产业链',
]

/**
 * AI 分析输入条（高保真重构）
 * .panel 容器 + ✦ 前缀 + 占位输入框 + 渐变「开始分析」按钮；下方「试试：」推荐 chip。
 */
export default function AnalysisInput({ onSubmit, isRunning }: AnalysisInputProps) {
  const [query, setQuery] = useState('')
  const [submitLocked, setSubmitLocked] = useState(false)
  const disabled = isRunning || submitLocked

  useEffect(() => {
    if (!isRunning) setSubmitLocked(false)
  }, [isRunning])

  const handleSubmit = useCallback(() => {
    const trimmed = query.trim()
    if (!trimmed || disabled) return
    setSubmitLocked(true)
    onSubmit(trimmed)
  }, [query, disabled, onSubmit])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit],
  )

  return (
    <div>
      <div
        className="panel fade-in"
        style={{
          padding: 10,
          display: 'flex',
          gap: 10,
          alignItems: 'center',
          maxWidth: 760,
          margin: '0 auto',
        }}
      >
        <span style={{ paddingLeft: 10, color: 'var(--text-faint)', fontSize: 18 }}>✦</span>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="例如：华为昇腾 950 芯片全供应链"
          style={{
            flex: 1,
            border: 'none',
            background: 'transparent',
            outline: 'none',
            color: 'var(--text)',
            fontFamily: 'var(--font-cjk)',
            fontSize: 15,
            padding: '10px 0',
            opacity: disabled ? 0.6 : 1,
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !query.trim()}
          style={{
            cursor: disabled || !query.trim() ? 'not-allowed' : 'pointer',
            border: 'none',
            borderRadius: 'var(--r-sm)',
            padding: '12px 24px',
            fontFamily: 'var(--font-cjk)',
            fontWeight: 700,
            fontSize: 14,
            color: '#fff',
            background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
            boxShadow: '0 10px 24px -12px var(--accent)',
            opacity: disabled || !query.trim() ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {isRunning ? '分析中...' : '开始分析'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', justifyContent: 'center', marginTop: 16 }}>
        <span style={{ fontSize: 12.5, color: 'var(--text-faint)', alignSelf: 'center' }}>试试：</span>
        {EXAMPLE_QUERIES.map((text) => (
          <button
            key={text}
            onClick={() => !disabled && setQuery(text)}
            disabled={disabled}
            className="card"
            style={{
              cursor: disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-cjk)',
              fontSize: 12.5,
              color: 'var(--text-dim)',
              background: 'var(--surface)',
              padding: '7px 13px',
              opacity: disabled ? 0.5 : 1,
            }}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}
