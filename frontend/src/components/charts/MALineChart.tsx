import { useMemo } from 'react'
import type { MovingAveragePoint } from '../../types/stock'

/**
 * 自绘 SVG 日线均线图（个股洞察弹窗用）
 * 收盘价 + MA5/20/120/240，左侧价标横网格 + 底部日期刻度（含浅色竖向网格线，
 * 便于把均线波动对到具体日期）。颜色取自 --price-line / --ma5 / --ma20 / --ma120 / --ma240。
 */

/** "2026-05-29" → "05-29"，便于在 X 轴显示 */
function shortDate(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date || '')
  return m ? `${m[2]}-${m[3]}` : date || ''
}

/** 在 n 个点上取 count 个均匀分布的刻度下标（去重） */
function tickIndices(n: number, count: number): number[] {
  if (n <= 1) return [0]
  const k = Math.min(count, n)
  const out: number[] = []
  for (let i = 0; i < k; i += 1) {
    const idx = Math.round((i / (k - 1)) * (n - 1))
    if (out[out.length - 1] !== idx) out.push(idx)
  }
  return out
}

export default function MALineChart({ data }: { data: MovingAveragePoint[] }) {
  const W = 900
  const H = 320
  const padL = 4
  const padR = 8
  const padT = 18
  const padB = 36 // 预留底部日期行

  const model = useMemo(() => {
    if (data.length === 0) return null
    const values = data
      .flatMap((d) => [d.close, d.ma5, d.ma20, d.ma120, d.ma240])
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
    const ticks = tickIndices(n, 6).map((i) => ({ i, date: shortDate(data[i].date) }))
    return { x, y, line, gridVals, ticks }
  }, [data])

  if (!model) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
        暂无日线均线数据
      </div>
    )
  }

  const axisY = H - padB
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
      {/* 横向价标网格 */}
      {model.gridVals.map((v, i) => (
        <g key={`h${i}`}>
          <line x1={padL} x2={W - padR} y1={model.y(v)} y2={model.y(v)} stroke="var(--grid)" strokeWidth="1" />
          <text x={padL + 4} y={model.y(v) - 5} fill="var(--text-faint)" fontSize="13" fontFamily="var(--font-mono)">
            {v.toFixed(2)}
          </text>
        </g>
      ))}

      {/* 竖向日期网格 */}
      {model.ticks.map((t, idx) => (
        <line key={`v${idx}`} x1={model.x(t.i)} x2={model.x(t.i)} y1={padT} y2={axisY} stroke="var(--grid)" strokeWidth="1" />
      ))}

      <polyline points={model.line('close')} fill="none" stroke="var(--price-line)" strokeWidth="1.4" opacity="0.85" />
      <polyline points={model.line('ma5')} fill="none" stroke="var(--ma5)" strokeWidth="1.6" />
      <polyline points={model.line('ma20')} fill="none" stroke="var(--ma20)" strokeWidth="1.6" />
      <polyline points={model.line('ma120')} fill="none" stroke="var(--ma120)" strokeWidth="1.6" />
      <polyline points={model.line('ma240')} fill="none" stroke="var(--ma240)" strokeWidth="1.6" />

      {/* 底部日期刻度 */}
      {model.ticks.map((t, idx) => {
        const anchor = idx === 0 ? 'start' : idx === model.ticks.length - 1 ? 'end' : 'middle'
        return (
          <text
            key={`d${idx}`}
            x={model.x(t.i)}
            y={H - 12}
            textAnchor={anchor}
            fill="var(--text-faint)"
            fontSize="13"
            fontFamily="var(--font-mono)"
          >
            {t.date}
          </text>
        )
      })}
    </svg>
  )
}
