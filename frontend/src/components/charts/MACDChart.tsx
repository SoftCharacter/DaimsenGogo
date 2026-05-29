import { useMemo } from 'react'
import type { MacdPoint } from '../../types/stock'

/**
 * 自绘 SVG MACD 指标图（个股洞察弹窗用）
 * 移植自设计交接包 charts.jsx 的 MACDChart：DIF/DEA 折线 + 红涨绿跌柱。
 * DIF 取 --ma5(橙)、DEA 取 --ma20(蓝)、柱 --up(红)/--down(绿)。
 */
export default function MACDChart({ data }: { data: MacdPoint[] }) {
  const W = 900
  const H = 200
  const padL = 4
  const padR = 8
  const padT = 14
  const padB = 22

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
    return { mid, x, y, bw, poly }
  }, [data])

  if (!model) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
        暂无 MACD 数据
      </div>
    )
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
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
    </svg>
  )
}
