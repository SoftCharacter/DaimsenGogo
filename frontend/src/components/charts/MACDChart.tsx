import { useMemo } from 'react'
import type { MacdPoint } from '../../types/stock'

/**
 * 自绘 SVG MACD 指标图（个股洞察弹窗用）
 * DIF/DEA 折线 + 红涨绿跌柱，底部加日期刻度（含浅色竖向网格线），便于知道波动发生的时间。
 * DIF 取 --ma5(橙)、DEA 取 --ma20(蓝)、柱 --up(红)/--down(绿)。
 */

/** "2026-05-29" → "05-29" */
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

export default function MACDChart({ data }: { data: MacdPoint[] }) {
  const W = 900
  const H = 200
  const padL = 4
  const padR = 8
  const padT = 14
  const padB = 30 // 预留底部日期行

  const model = useMemo(() => {
    if (data.length === 0) return null
    const all = data.flatMap((d) => [d.dif, d.dea, d.macd])
    const hi = Math.max(...all)
    const lo = Math.min(...all)
    const span = Math.max(hi, -lo) * 2.1 || 1
    const mid = padT + (H - padT - padB) / 2
    const innerW = W - padL - padR
    const innerH = H - padT - padB
    const n = data.length
    const x = (i: number) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW)
    const y = (v: number) => mid - (v / span) * innerH
    const bw = Math.max(0.8, (innerW / n) * 0.6)
    const poly = (key: 'dif' | 'dea') => data.map((d, i) => `${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(' ')
    const ticks = tickIndices(n, 6).map((i) => ({ i, date: shortDate(data[i].date) }))
    return { mid, x, y, bw, poly, ticks }
  }, [data])

  if (!model) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
        暂无 MACD 数据
      </div>
    )
  }

  const axisY = H - padB
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
      {/* 竖向日期网格 */}
      {model.ticks.map((t, idx) => (
        <line key={`v${idx}`} x1={model.x(t.i)} x2={model.x(t.i)} y1={padT} y2={axisY} stroke="var(--grid)" strokeWidth="1" />
      ))}

      {/* 零轴 */}
      <line x1={padL} x2={W - padR} y1={model.mid} y2={model.mid} stroke="var(--grid)" strokeWidth="1" />

      {data.map((d, i) => {
        const up = d.macd >= 0
        const yv = model.y(d.macd)
        const hgt = Math.abs(yv - model.mid)
        return (
          <rect
            key={i}
            x={model.x(i) - model.bw / 2}
            y={up ? yv : model.mid}
            width={model.bw}
            height={Math.max(0.5, hgt)}
            fill={up ? 'var(--up)' : 'var(--down)'}
            opacity="0.85"
          />
        )
      })}
      <polyline points={model.poly('dif')} fill="none" stroke="var(--ma5)" strokeWidth="1.5" />
      <polyline points={model.poly('dea')} fill="none" stroke="var(--ma20)" strokeWidth="1.5" />

      {/* 底部日期刻度 */}
      {model.ticks.map((t, idx) => {
        const anchor = idx === 0 ? 'start' : idx === model.ticks.length - 1 ? 'end' : 'middle'
        return (
          <text
            key={`d${idx}`}
            x={model.x(t.i)}
            y={H - 10}
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
