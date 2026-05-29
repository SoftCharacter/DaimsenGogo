import { useMemo } from 'react'
import type { MovingAveragePoint } from '../../types/stock'

/**
 * 自绘 SVG 日线均线图（个股洞察弹窗用）
 * 移植自设计交接包 charts.jsx 的 MALineChart：收盘价 + MA5/20/120/240，
 * 3 条网格线带价标。颜色取自 --price-line / --ma5 / --ma20 / --ma120 / --ma240。
 */
export default function MALineChart({ data }: { data: MovingAveragePoint[] }) {
  const W = 900
  const H = 320
  const padL = 4
  const padR = 8
  const padT = 18
  const padB = 26

  const model = useMemo(() => {
    if (data.length === 0) return null
    const values = data.flatMap((d) => [d.close, d.ma5, d.ma20, d.ma120, d.ma240])
      .filter((v): v is number => v !== null && Number.isFinite(v))
    const hi = Math.max(...values)
    const lo = Math.min(...values)
    const span = (hi - lo) * 1.04 || 1
    const innerW = W - padL - padR
    const innerH = H - padT - padB
    const n = data.length
    const x = (i: number) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW)
    const y = (v: number) => padT + (1 - (v - lo) / span) * innerH
    const line = (key: 'close' | 'ma5' | 'ma20' | 'ma120' | 'ma240') =>
      data
        .map((d, i) => {
          const v = d[key]
          return v == null || !Number.isFinite(v) ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`
        })
        .filter(Boolean)
        .join(' ')
    const gridVals = [lo, lo + span * 0.5, hi]
    return { y, line, gridVals }
  }, [data])

  if (!model) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
        暂无日线均线数据
      </div>
    )
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
      {model.gridVals.map((v, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={model.y(v)} y2={model.y(v)} stroke="var(--grid)" strokeWidth="1" />
          <text x={padL + 4} y={model.y(v) - 5} fill="var(--text-faint)" fontSize="13" fontFamily="var(--font-mono)">
            {v.toFixed(2)}
          </text>
        </g>
      ))}
      <polyline points={model.line('close')} fill="none" stroke="var(--price-line)" strokeWidth="1.4" opacity="0.85" />
      <polyline points={model.line('ma5')} fill="none" stroke="var(--ma5)" strokeWidth="1.6" />
      <polyline points={model.line('ma20')} fill="none" stroke="var(--ma20)" strokeWidth="1.6" />
      <polyline points={model.line('ma120')} fill="none" stroke="var(--ma120)" strokeWidth="1.6" />
      <polyline points={model.line('ma240')} fill="none" stroke="var(--ma240)" strokeWidth="1.6" />
    </svg>
  )
}
