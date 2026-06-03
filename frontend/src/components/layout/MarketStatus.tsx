import { useEffect, useState } from 'react'

/**
 * 实时时钟 + A股休市状态指示
 * 移植自设计交接包 components.jsx 的 MarketStatus（原型固定「休市」，
 * 此处按交易时段实时判定）。每秒更新，作为独立组件避免触发全局重渲染。
 */

/** 判断当前是否处于 A 股交易时段（周一至周五 09:30-11:30 / 13:00-15:00） */
function isTradingNow(now: Date): boolean {
  const day = now.getDay()
  if (day === 0 || day === 6) return false
  const minutes = now.getHours() * 60 + now.getMinutes()
  const morning = minutes >= 9 * 60 + 30 && minutes <= 11 * 60 + 30
  const afternoon = minutes >= 13 * 60 && minutes <= 15 * 60
  return morning || afternoon
}

export default function MarketStatus() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  const trading = isTradingNow(now)
  const dotColor = trading ? 'var(--up)' : 'var(--down)'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, color: 'var(--text-dim)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: 99,
            background: dotColor,
            boxShadow: `0 0 0 4px ${trading ? 'var(--up-soft)' : 'var(--down-soft)'}`,
            animation: 'pulse 2s infinite',
          }}
        />
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{trading ? '交易中' : '休市'}</span>
      </div>
      <span style={{ fontSize: 13, opacity: 0.3 }}>·</span>
      <span className="mono" style={{ fontSize: 13.5, letterSpacing: '0.02em' }}>
        {hh}:{mm}
        <span style={{ opacity: 0.5 }}>:{ss}</span>
      </span>
    </div>
  )
}
