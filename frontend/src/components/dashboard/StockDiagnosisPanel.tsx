import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type {
  ChipDistribution,
  MacdPoint,
  MovingAveragePoint,
  NetProfitPoint,
  ShareholderPoint,
  StockDiagnosis,
} from '../../types/stock'
import type { StockItem } from '../../types/theme'

const CHART_WIDTH = 720
const CHART_HEIGHT = 220
const PAD_X = 42
const PAD_TOP = 18
const PAD_BOTTOM = 34

interface StockDiagnosisPanelProps {
  stock: StockItem
  diagnosis: StockDiagnosis | null
  loading: boolean
  enhancing: boolean
  enhanced: boolean
  error: string
  onEnhance: (stock: StockItem) => void
  onClose: () => void
}

function formatYi(value: number): string {
  return `${(value / 1e8).toFixed(2)}亿`
}

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(1)}万`
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function range(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1]
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const padding = (max - min) * 0.12
  return [min - padding, max + padding]
}

function scaleY(value: number, min: number, max: number): number {
  const innerHeight = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM
  return PAD_TOP + (1 - (value - min) / (max - min)) * innerHeight
}

function linePath<T>(
  data: T[],
  getValue: (item: T) => number,
  min: number,
  max: number,
  leftPad = PAD_X,
  rightPad = PAD_X,
): string {
  if (data.length === 0) return ''
  const innerWidth = CHART_WIDTH - leftPad - rightPad
  return data
    .map((item, index) => {
      const x = leftPad + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth)
      const y = scaleY(getValue(item), min, max)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

function smoothLinePath<T>(
  data: T[],
  getValue: (item: T) => number,
  min: number,
  max: number,
  leftPad = PAD_X,
  rightPad = PAD_X,
): string {
  if (data.length === 0) return ''
  const innerWidth = CHART_WIDTH - leftPad - rightPad
  const points = data.map((item, index) => ({
    x: leftPad + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth),
    y: scaleY(getValue(item), min, max),
  }))
  if (points.length === 1) return `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`
  const parts = [`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`]
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[Math.max(0, index - 1)]
    const p1 = points[index]
    const p2 = points[index + 1]
    const p3 = points[Math.min(points.length - 1, index + 2)]
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    parts.push(`C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`)
  }
  return parts.join(' ')
}

function sparseLinePath<T>(
  data: T[],
  getValue: (item: T) => number | null,
  min: number,
  max: number,
): string {
  const innerWidth = CHART_WIDTH - PAD_X * 2
  return data
    .map((item, index) => {
      const value = getValue(item)
      if (value === null) return ''
      const x = PAD_X + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth)
      return `${index === 0 || data.slice(0, index).every((point) => getValue(point) === null) ? 'M' : 'L'} ${x.toFixed(2)} ${scaleY(value, min, max).toFixed(2)}`
    })
    .filter(Boolean)
    .join(' ')
}

function axisLabel(data: { date?: string; report_name?: string }[], index: number): string {
  const item = data[index]
  if (!item) return ''
  return item.report_name || (item.date ? item.date.slice(5) : '')
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="h-[220px] flex items-center justify-center text-sm text-[#64748b]">
      {label}
    </div>
  )
}

function LegendDot({ color, label, shape = 'line' }: { color: string; label: string; shape?: 'line' | 'bar' }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {shape === 'bar' ? (
        <span className="inline-block h-3 w-2 rounded-sm" style={{ backgroundColor: color }} />
      ) : (
        <span className="inline-block h-0.5 w-4 rounded-full" style={{ backgroundColor: color }} />
      )}
      <span>{label}</span>
    </span>
  )
}

function MacdChart({ data }: { data: MacdPoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无MACD数据" />

  const values = data.flatMap((item) => [item.dif, item.dea, item.macd])
  const [min, max] = range(values)
  const baseline = scaleY(0, min, max)
  const innerWidth = CHART_WIDTH - PAD_X * 2
  const barWidth = Math.max(2, innerWidth / data.length * 0.58)
  const difPath = linePath(data, (item) => item.dif, min, max)
  const deaPath = linePath(data, (item) => item.dea, min, max)
  const ticks = [0, Math.floor(data.length / 2), data.length - 1]

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full h-[220px]">
      <line x1={PAD_X} y1={baseline} x2={CHART_WIDTH - PAD_X} y2={baseline} stroke="#334155" strokeDasharray="4 4" />
      {data.map((item, index) => {
        const x = PAD_X + (index / Math.max(1, data.length - 1)) * innerWidth
        const y = scaleY(item.macd, min, max)
        const barTop = Math.min(y, baseline)
        const height = Math.max(1, Math.abs(y - baseline))
        return (
          <rect
            key={`${item.date}-${index}`}
            x={x - barWidth / 2}
            y={barTop}
            width={barWidth}
            height={height}
            fill={item.macd >= 0 ? '#ef4444' : '#22c55e'}
            opacity={0.65}
          />
        )
      })}
      <path d={difPath} fill="none" stroke="#f97316" strokeWidth="2" />
      <path d={deaPath} fill="none" stroke="#38bdf8" strokeWidth="2" />
      {ticks.map((index) => (
        <text key={index} x={PAD_X + (index / Math.max(1, data.length - 1)) * innerWidth} y={CHART_HEIGHT - 10} textAnchor="middle" fill="#64748b" fontSize="11">
          {axisLabel(data, index)}
        </text>
      ))}
    </svg>
  )
}

function MovingAverageChart({ data }: { data: MovingAveragePoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无日线均线数据" />

  const values = data.flatMap((item) => [
    item.close,
    item.ma5,
    item.ma20,
    item.ma120,
    item.ma240,
  ]).filter((item): item is number => item !== null)
  const [min, max] = range(values)
  const innerWidth = CHART_WIDTH - PAD_X * 2
  const ticks = [0, Math.floor(data.length / 2), data.length - 1]
  const maPath = (key: 'ma5' | 'ma20' | 'ma120' | 'ma240') => sparseLinePath(data, (item) => item[key], min, max)

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full h-[220px]">
      {[0, 0.5, 1].map((ratio) => {
        const y = PAD_TOP + ratio * (CHART_HEIGHT - PAD_TOP - PAD_BOTTOM)
        return (
          <line key={ratio} x1={PAD_X} y1={y} x2={CHART_WIDTH - PAD_X} y2={y} stroke="#1f2937" />
        )
      })}
      <path d={smoothLinePath(data, (item) => item.close, min, max)} fill="none" stroke="#e5e7eb" strokeWidth="2.2" />
      <path d={maPath('ma5')} fill="none" stroke="#f97316" strokeWidth="1.5" />
      <path d={maPath('ma20')} fill="none" stroke="#38bdf8" strokeWidth="1.5" />
      <path d={maPath('ma120')} fill="none" stroke="#a78bfa" strokeWidth="1.5" />
      <path d={maPath('ma240')} fill="none" stroke="#22c55e" strokeWidth="1.5" />
      {ticks.map((index) => (
        <text key={index} x={PAD_X + (index / Math.max(1, data.length - 1)) * innerWidth} y={CHART_HEIGHT - 10} textAnchor="middle" fill="#64748b" fontSize="11">
          {axisLabel(data, index)}
        </text>
      ))}
      {[min, (min + max) / 2, max].map((value) => (
        <text key={value} x={PAD_X - 8} y={scaleY(value, min, max) + 4} textAnchor="end" fill="#94a3b8" fontSize="10">
          {value.toFixed(2)}
        </text>
      ))}
    </svg>
  )
}

function ShareholderChart({ data }: { data: ShareholderPoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无股东人数数据" />

  const [min, max] = range(data.map((item) => item.ashare_holder))
  const innerWidth = CHART_WIDTH - PAD_X * 2
  const barWidth = Math.max(20, innerWidth / data.length * 0.5)
  const y0 = scaleY(min, min, max)

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full h-[220px]">
      <line x1={PAD_X} y1={y0} x2={CHART_WIDTH - PAD_X} y2={y0} stroke="#334155" />
      {data.map((item, index) => {
        const x = PAD_X + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth)
        const y = scaleY(item.ashare_holder, min, max)
        return (
          <g key={item.timestamp}>
            <rect x={x - barWidth / 2} y={y} width={barWidth} height={Math.max(1, y0 - y)} fill="#8b5cf6" opacity={0.8} />
            <text x={x} y={y - 6} textAnchor="middle" fill="#c4b5fd" fontSize="11">
              {formatWan(item.ashare_holder)}
            </text>
            <text x={x} y={CHART_HEIGHT - 10} textAnchor="middle" fill="#64748b" fontSize="11">
              {item.date.slice(2, 7)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function ChipMetric({
  color,
  label,
  value,
}: {
  color: string
  label: string
  value: string
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
        <span className="text-[11px] text-[#94a3b8]">{label}</span>
      </div>
      <div className="text-base font-semibold text-[#e2e8f0] mt-1">{value}</div>
    </div>
  )
}

function ChipDistributionChart({ data }: { data: ChipDistribution | null }) {
  const snapshots = data?.snapshots || []
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, snapshots.length - 1))
  useEffect(() => {
    setSelectedIndex(Math.max(0, snapshots.length - 1))
  }, [snapshots.length])
  const safeIndex = Math.min(selectedIndex, Math.max(0, snapshots.length - 1))
  const selected = snapshots[safeIndex]
  const histogram = selected ? (data?.histograms[selected.date] || data?.histogram || []) : []

  const chart = useMemo(() => {
    if (!selected || histogram.length === 0) return null
    const width = CHART_WIDTH
    const height = 360
    const left = 58
    const right = 574
    const top = 24
    const bottom = 292
    const prices = histogram.map((item) => item.price)
    const minPrice = Math.min(...prices)
    const maxPrice = Math.max(...prices)
    const maxPercent = Math.max(...histogram.map((item) => item.percent), 0.1)
    const yFor = (price: number) => bottom - ((price - minPrice) / Math.max(0.01, maxPrice - minPrice)) * (bottom - top)
    const xFor = (percent: number) => left + (percent / maxPercent) * (right - left)
    return { width, height, left, right, top, bottom, minPrice, maxPrice, maxPercent, yFor, xFor }
  }, [histogram, selected])

  if (!data || snapshots.length === 0 || !selected || !chart) {
    return <EmptyChart label="暂无筹码分布数据" />
  }

  const markerRows: Array<{ label: string; value: number | null; color: string }> = [
    { label: '平均成本', value: selected.avg_cost, color: '#f59e0b' },
    { label: '支撑位', value: selected.support_price, color: '#3b82f6' },
    { label: '压力位', value: selected.pressure_price, color: '#a855f7' },
  ]

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 rounded-md bg-[#0f172a] border border-[#1e293b] p-3 mb-3">
        <ChipMetric color="#f59e0b" label="平均成本" value={selected.avg_cost.toFixed(2)} />
        <ChipMetric color="#3b82f6" label="支撑位" value={selected.support_price?.toFixed(2) || '--'} />
        <ChipMetric color="#a855f7" label="压力位" value={selected.pressure_price?.toFixed(2) || '--'} />
        <ChipMetric color="#ef4444" label="盈利比例" value={formatPercent(selected.benefit_ratio)} />
      </div>

      <div className="flex items-center justify-between gap-3 text-xs text-[#94a3b8] mb-2">
        <div className="flex items-center gap-4">
          <LegendDot color="#ef4444" label="获利持仓" shape="bar" />
          <LegendDot color="#10b981" label="套牢持仓" shape="bar" />
        </div>
        <span>日期：{selected.date}</span>
      </div>

      <svg viewBox={`0 0 ${chart.width} ${chart.height}`} className="w-full h-[360px]">
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const x = chart.left + tick * (chart.right - chart.left)
          return (
            <g key={tick}>
              <line x1={x} y1={chart.top} x2={x} y2={chart.bottom} stroke="#1f2937" />
              <text x={x} y={chart.bottom + 26} textAnchor="middle" fill="#94a3b8" fontSize="11">
                {(chart.maxPercent * tick).toFixed(1)}%
              </text>
            </g>
          )
        })}
        {[chart.minPrice, (chart.minPrice + chart.maxPrice) / 2, chart.maxPrice].map((price) => (
          <text key={price} x={chart.left - 10} y={chart.yFor(price) + 4} textAnchor="end" fill="#64748b" fontSize="11">
            {price.toFixed(2)}
          </text>
        ))}
        {histogram.map((item) => {
          const y = chart.yFor(item.price)
          const barWidth = Math.max(1, chart.xFor(item.percent) - chart.left)
          return (
            <rect
              key={`${selected.date}-${item.price}`}
              x={chart.left}
              y={y - 1}
              width={barWidth}
              height={2}
              fill={item.profitable ? '#ef4444' : '#10b981'}
              opacity={0.92}
            />
          )
        })}
        {markerRows.map((marker) => {
          if (marker.value === null) return null
          const y = chart.yFor(marker.value)
          return (
            <g key={marker.label}>
              <line x1={chart.left} y1={y} x2={chart.right + 110} y2={y} stroke="#64748b" strokeDasharray="5 5" opacity={0.55} />
              <text x={chart.right + 118} y={y + 4} fill={marker.color} fontSize="14" fontWeight="600">
                {marker.value.toFixed(2)}
              </text>
            </g>
          )
        })}
        <text x={chart.left} y={chart.height - 8} fill="#94a3b8" fontSize="12">
          {selected.interpretation}
        </text>
      </svg>

      <input
        type="range"
        min={0}
        max={Math.max(0, snapshots.length - 1)}
        value={safeIndex}
        onChange={(event) => setSelectedIndex(Number(event.target.value))}
        className="w-full accent-[#3b82f6]"
      />
      <div className="flex justify-between text-xs text-[#64748b] mt-1">
        <span>{snapshots[0]?.date}</span>
        <span>{selected.date}</span>
        <span>{snapshots[snapshots.length - 1]?.date}</span>
      </div>
    </div>
  )
}

function NetProfitChart({ data }: { data: NetProfitPoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无近五年归母净利润数据" />

  const leftPad = 58
  const rightPad = 58
  const profitValues = data.map((item) => item.net_profit_atsopc)
  const yoyData = data.filter((item) => item.yoy_percent !== null)
  const yoyValues = yoyData.map((item) => item.yoy_percent as number)
  const [profitMin, profitMax] = range([0, ...profitValues])
  const [yoyMin, yoyMax] = range([0, ...yoyValues])
  const innerWidth = CHART_WIDTH - leftPad - rightPad
  const groupWidth = innerWidth / data.length
  const barWidth = Math.min(46, groupWidth * 0.42)
  const profitZero = scaleY(0, profitMin, profitMax)
  const profitTicks = [profitMin, (profitMin + profitMax) / 2, profitMax]
  const yoyTicks = [yoyMin, (yoyMin + yoyMax) / 2, yoyMax]
  const plotBottom = CHART_HEIGHT - PAD_BOTTOM
  const labelTop = PAD_TOP + 10
  const labelBottom = plotBottom - 8
  const yoyPath = linePath(
    yoyData,
    (item) => item.yoy_percent as number,
    yoyMin,
    yoyMax,
    leftPad,
    rightPad,
  )

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full h-[220px]">
      <line x1={leftPad} y1={PAD_TOP} x2={leftPad} y2={CHART_HEIGHT - PAD_BOTTOM} stroke="#334155" />
      <line x1={CHART_WIDTH - rightPad} y1={PAD_TOP} x2={CHART_WIDTH - rightPad} y2={CHART_HEIGHT - PAD_BOTTOM} stroke="#334155" />
      <line x1={leftPad} y1={profitZero} x2={CHART_WIDTH - rightPad} y2={profitZero} stroke="#334155" strokeDasharray="4 4" />
      {profitTicks.map((tick) => (
        <g key={`profit-${tick}`}>
          <line x1={leftPad - 4} y1={scaleY(tick, profitMin, profitMax)} x2={leftPad} y2={scaleY(tick, profitMin, profitMax)} stroke="#334155" />
          <text x={leftPad - 8} y={scaleY(tick, profitMin, profitMax) + 4} textAnchor="end" fill="#94a3b8" fontSize="10">
            {(tick / 1e8).toFixed(0)}亿
          </text>
        </g>
      ))}
      {yoyTicks.map((tick) => (
        <g key={`yoy-${tick}`}>
          <line x1={CHART_WIDTH - rightPad} y1={scaleY(tick, yoyMin, yoyMax)} x2={CHART_WIDTH - rightPad + 4} y2={scaleY(tick, yoyMin, yoyMax)} stroke="#334155" />
          <text x={CHART_WIDTH - rightPad + 8} y={scaleY(tick, yoyMin, yoyMax) + 4} textAnchor="start" fill="#94a3b8" fontSize="10">
            {tick.toFixed(0)}%
          </text>
        </g>
      ))}
      {data.map((item, index) => {
        const centerX = leftPad + groupWidth * index + groupWidth / 2
        const profitY = scaleY(item.net_profit_atsopc, profitMin, profitMax)
        const yoyY = item.yoy_percent === null
          ? null
          : scaleY(item.yoy_percent as number, yoyMin, yoyMax)
        const baseProfitLabelY = item.net_profit_atsopc >= 0
          ? Math.min(profitY, profitZero) - 8
          : Math.max(profitY, profitZero) + 14
        const profitLabelY = clamp(
          yoyY !== null && Math.abs(baseProfitLabelY - (yoyY - 10)) < 18
            ? baseProfitLabelY - 18
            : baseProfitLabelY,
          labelTop,
          labelBottom,
        )
        return (
          <g key={item.report_name}>
            <rect
              x={centerX - barWidth / 2}
              y={Math.min(profitY, profitZero)}
              width={barWidth}
              height={Math.max(1, Math.abs(profitZero - profitY))}
              fill="#ef4444"
              opacity={0.78}
            />
            <text x={centerX} y={profitLabelY} textAnchor="middle" fill="#fecaca" fontSize="11">
              {formatYi(item.net_profit_atsopc)}
            </text>
            <text x={centerX} y={CHART_HEIGHT - 10} textAnchor="middle" fill="#64748b" fontSize="11">
              {item.report_name.replace('年报', '')}
            </text>
          </g>
        )
      })}
      {yoyPath && <path d={yoyPath} fill="none" stroke="#38bdf8" strokeWidth="2.2" />}
      {yoyData.map((item) => {
        const dataIndex = data.findIndex((point) => point.timestamp === item.timestamp)
        const centerX = leftPad + groupWidth * dataIndex + groupWidth / 2
        const y = scaleY(item.yoy_percent as number, yoyMin, yoyMax)
        const profitY = scaleY(item.net_profit_atsopc, profitMin, profitMax)
        const profitLabelY = clamp(
          item.net_profit_atsopc >= 0
            ? Math.min(profitY, profitZero) - 8
            : Math.max(profitY, profitZero) + 14,
          labelTop,
          labelBottom,
        )
        const aboveY = y - 10
        const belowY = y + 18
        const textY = clamp(
          Math.abs(aboveY - profitLabelY) < 18 ? belowY : aboveY,
          labelTop,
          labelBottom,
        )
        return (
          <g key={`${item.report_name}-yoy`}>
            <circle cx={centerX} cy={y} r="3.5" fill="#38bdf8" />
            <text x={centerX} y={textY} textAnchor="middle" fill="#bae6fd" fontSize="11">
              {(item.yoy_percent as number).toFixed(1)}%
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function ChartSection({
  title,
  subtitle,
  legend,
  children,
}: {
  title: string
  subtitle: string
  legend?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-[#1e293b] bg-[#111827] p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h4 className="text-sm font-semibold text-[#e2e8f0]">{title}</h4>
          <p className="text-xs text-[#64748b] mt-1">{subtitle}</p>
        </div>
        {legend && (
          <span className="flex items-center gap-3 text-xs text-[#94a3b8] shrink-0">
            {legend}
          </span>
        )}
      </div>
      {children}
    </section>
  )
}

function parseTable(lines: string[], startIndex: number): { rows: string[][]; nextIndex: number } {
  const rows: string[][] = []
  let index = startIndex
  while (index < lines.length && lines[index].trim().startsWith('|')) {
    const cells = lines[index]
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim())
    const isSeparator = cells.every((cell) => /^:?-{3,}:?$/.test(cell))
    if (!isSeparator) {
      rows.push(cells)
    }
    index += 1
  }
  return { rows, nextIndex: index }
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /\*\*([^*]+)\*\*/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    nodes.push(
      <strong key={`${match.index}-${match[1]}`} className="font-semibold text-[#e2e8f0]">
        {match[1]}
      </strong>,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }
  return nodes
}

function MarkdownReport({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let key = 0

  while (index < lines.length) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      continue
    }

    if (line.startsWith('## ')) {
      blocks.push(
        <h2 key={key} className="text-sm font-semibold text-[#e2e8f0] mt-5 first:mt-0 mb-2">
          {renderInlineMarkdown(line.replace(/^##\s+/, ''))}
        </h2>,
      )
      key += 1
      index += 1
      continue
    }

    if (line.startsWith('|')) {
      const { rows, nextIndex } = parseTable(lines, index)
      const [head, ...body] = rows
      if (head) {
        blocks.push(
          <div key={key} className="overflow-x-auto my-3 rounded-md border border-[#263244]">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-[#0f172a]">
                  {head.map((cell) => (
                    <th key={cell} className="px-3 py-2 text-left font-semibold text-[#cbd5e1] border-b border-[#263244]">
                      {renderInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, rowIndex) => (
                  <tr key={`${row.join('-')}-${rowIndex}`} className="odd:bg-[#111827] even:bg-[#0f172a]">
                    {row.map((cell, cellIndex) => (
                      <td key={`${cell}-${cellIndex}`} className="px-3 py-2 align-top text-[#94a3b8] border-t border-[#1e293b] leading-5">
                        {renderInlineMarkdown(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        key += 1
      }
      index = nextIndex
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={key} className="list-disc pl-5 my-2 space-y-1 text-sm text-[#cbd5e1] leading-6">
          {items.map((item) => (
            <li key={item}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      )
      key += 1
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (
      index < lines.length
      && lines[index].trim()
      && !lines[index].trim().startsWith('## ')
      && !lines[index].trim().startsWith('|')
      && !/^[-*]\s+/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(
      <p key={key} className="text-sm text-[#cbd5e1] leading-6 my-2">
        {renderInlineMarkdown(paragraph.join(' '))}
      </p>,
    )
    key += 1
  }

  return <div>{blocks}</div>
}

export default function StockDiagnosisPanel({
  stock,
  diagnosis,
  loading,
  enhancing,
  enhanced,
  error,
  onEnhance,
  onClose,
}: StockDiagnosisPanelProps) {
  const llmStatusText = diagnosis?.llm_status === 'ok'
    ? ''
    : diagnosis?.llm_status === 'error' || diagnosis?.llm_status === 'missing_config'
      ? '大模型调用失败，请配置 API'
      : ''

  return (
    <div className="fixed inset-x-4 top-20 bottom-4 z-50 rounded-lg border border-[#334155] bg-[#0a0e17] shadow-2xl overflow-hidden">
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-[#1e293b] bg-[#0f172a]">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-bold text-[#e2e8f0] truncate">
                {stock.name} 盘面洞察
              </h3>
              <span className="text-xs font-mono text-[#64748b]">{stock.code}</span>
            </div>
            <p className="text-xs text-[#94a3b8] mt-1">
              生成时间：{diagnosis?.generated_at || '等待生成'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-8 px-3 rounded border border-[#334155] text-sm text-[#cbd5e1] hover:border-[#64748b] hover:text-white"
          >
            关闭
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="h-full min-h-[420px] flex items-center justify-center">
              <div className="text-center">
                <div className="text-sm text-[#e2e8f0]">正在调取数据并计算诊断...</div>
                <div className="text-xs text-[#64748b] mt-2">历史收盘价、股东人数、财报和大事提醒会并行加载</div>
              </div>
            </div>
          ) : error ? (
            <div className="h-full min-h-[420px] flex items-center justify-center text-sm text-[#ef4444]">
              {error}
            </div>
          ) : diagnosis ? (
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)] gap-5">
              <div className="space-y-4">
                <ChartSection
                  title="日线均线"
                  subtitle="收盘价日线 / MA5 / MA20 / MA120 / MA240"
                  legend={(
                    <>
                      <LegendDot color="#e5e7eb" label="收盘价" />
                      <LegendDot color="#f97316" label="MA5" />
                      <LegendDot color="#38bdf8" label="MA20" />
                      <LegendDot color="#a78bfa" label="MA120" />
                      <LegendDot color="#22c55e" label="MA240" />
                    </>
                  )}
                >
                  <MovingAverageChart data={diagnosis.moving_averages} />
                </ChartSection>
                <ChartSection
                  title="指标看板"
                  subtitle="近一年日线收盘价本地计算"
                  legend={(
                    <>
                      <LegendDot color="#f97316" label="DIF" />
                      <LegendDot color="#38bdf8" label="DEA" />
                      <LegendDot color="#ef4444" label="MACD" shape="bar" />
                      <LegendDot color="#22c55e" label="MACD" shape="bar" />
                    </>
                  )}
                >
                  <MacdChart data={diagnosis.macd} />
                </ChartSection>
                <ChartSection title="股东人数变化" subtitle="近三年股东户数，反映筹码集中或分散趋势">
                  <ShareholderChart data={diagnosis.shareholders} />
                </ChartSection>
                <ChartSection
                  title="筹码分布"
                  subtitle="东方财富K线与换手率，本地CYQ算法估算"
                >
                  <ChipDistributionChart data={diagnosis.chip_distribution} />
                </ChartSection>
                <ChartSection
                  title="归母净利润与同比"
                  subtitle="近五年年报，左轴为归母净利润，右轴为同比增速"
                  legend={(
                    <>
                      <LegendDot color="#ef4444" label="归母净利润" shape="bar" />
                      <LegendDot color="#38bdf8" label="同比" />
                    </>
                  )}
                >
                  <NetProfitChart data={diagnosis.net_profit} />
                </ChartSection>
              </div>

              <aside className="rounded-lg border border-[#1e293b] bg-[#111827] p-4 h-fit">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <h4 className="text-sm font-semibold text-[#e2e8f0]">结构解读</h4>
                  <div className="flex items-center gap-2">
                    {llmStatusText && (
                      <span className="text-xs text-[#ef4444]">{llmStatusText}</span>
                    )}
                    <button
                      type="button"
                      onClick={() => onEnhance(stock)}
                      disabled={enhancing || loading}
                      className="h-8 px-3 rounded border border-[#475569] text-xs font-medium text-[#e2e8f0] hover:border-[#38bdf8] hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {enhancing ? '解盘中...' : enhanced ? '返回' : '智能解盘'}
                    </button>
                  </div>
                </div>

                <div className="mb-4">
                  <h5 className="text-xs font-semibold text-[#cbd5e1] mb-2">大事提醒</h5>
                  <p className="text-sm text-[#94a3b8] leading-6 whitespace-pre-wrap">
                    {diagnosis.event_summary}
                  </p>
                </div>

                <div>
                  <h5 className="text-xs font-semibold text-[#cbd5e1] mb-2">综合解读</h5>
                  <MarkdownReport content={diagnosis.diagnosis_report} />
                </div>
              </aside>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
