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

  const handleExampleClick = useCallback((text: string) => {
    if (disabled) return
    setQuery(text)
  }, [disabled])

  return (
    <div className="rounded-lg border p-5 bg-[#151c2c] border-[#1e293b]">
      <h3 className="text-sm font-medium mb-3 text-[#94a3b8]">
        描述产品、技术或事件，AI将分析其全供应链
      </h3>

      <div className="flex gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="例如：华为昇腾950芯片全供应链"
          className="flex-1 px-4 py-2.5 rounded-md text-sm outline-none
                     bg-[#0a0e17] text-[#e2e8f0] border border-[#1e293b]
                     placeholder-[#475569]
                     focus:border-[#6366f1] transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !query.trim()}
          className="px-5 py-2.5 rounded-md text-sm font-medium
                     bg-[#6366f1] text-white
                     hover:bg-[#5558e6] transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed
                     whitespace-nowrap"
        >
          {isRunning ? '分析中...' : '开始分析'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2 mt-3">
        <span className="text-xs text-[#64748b]">试试:</span>
        {EXAMPLE_QUERIES.map((text) => (
          <button
            key={text}
            onClick={() => handleExampleClick(text)}
            disabled={disabled}
            className="px-2.5 py-1 rounded text-xs
                       bg-[#0a0e17] text-[#94a3b8] border border-[#1e293b]
                       hover:border-[#6366f1] hover:text-[#e2e8f0]
                       transition-colors cursor-pointer
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}
