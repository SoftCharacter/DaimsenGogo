import { useMemo } from 'react'
import type { KLinePoint } from '../../types/stock'

/**
 * 自绘 SVG 蜡烛迷你图（个股卡片用）
 * 移植自设计交接包 charts.jsx 的 CandleChart：含首日开盘价虚线参考线，
 * 涨蜡烛 --up(红) / 跌蜡烛 --down(绿)。
 */
interface CandleChartProps {
  data: KLinePoint[]
  height?: number
  showRef?: boolean
}

export default function CandleChart({ data, height = 132, showRef = true }: CandleChartProps) {
  const W = 600
  const H = height
  const padX = 10
  const padTop = 10
  const padBot = 10

  const { bars, refY } = useMemo(() => {
    if (data.length === 0) return { bars: [], refY: 0 }
    const hi = Math.max(...data.map((c) => c.high))
    const lo = Math.min(...data.map((c) => c.low))
    const span = hi - lo || 1
    const innerW = W - padX * 2
    const innerH = H - padTop - padBot
    const step = innerW / data.length
    const bw = Math.max(3, step * 0.62)
    const y = (v: number) => padTop + (1 - (v - lo) / span) * innerH
    const computed = data.map((c, i) => {
      const cx = padX + step * i + step / 2
      const up = c.close >= c.open
      return {
        cx,
        up,
        wickTop: y(c.high),
        wickBot: y(c.low),
        bodyTop: y(Math.max(c.open, c.close)),
        bodyBot: y(Math.min(c.open, c.close)),
        bw,
      }
    })
    return { bars: computed, refY: y(data[0].open) }
  }, [data, H])

  if (data.length === 0) return null

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: '100%', height: H, display: 'block' }}
    >
      {showRef && (
        <line
          x1={padX}
          x2={W - padX}
          y1={refY}
          y2={refY}
          stroke="var(--text-faint)"
          strokeWidth="1"
          strokeDasharray="3 5"
          opacity="0.5"
        />
      )}
      {bars.map((b, i) => {
        const col = b.up ? 'var(--up)' : 'var(--down)'
        const bodyH = Math.max(1.5, b.bodyBot - b.bodyTop)
        return (
          <g key={i}>
            <line x1={b.cx} x2={b.cx} y1={b.wickTop} y2={b.wickBot} stroke={col} strokeWidth="1.4" />
            <rect x={b.cx - b.bw / 2} y={b.bodyTop} width={b.bw} height={bodyH} fill={col} rx="0.5" />
          </g>
        )
      })}
    </svg>
  )
}
