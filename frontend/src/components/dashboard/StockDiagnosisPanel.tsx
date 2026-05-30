import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type {
  ChipDistribution,
  NetProfitPoint,
  ShareholderPoint,
  StockDiagnosis,
} from '../../types/stock'
import type { StockItem } from '../../types/theme'
import MALineChart from '../charts/MALineChart'
import MACDChart from '../charts/MACDChart'

/**
 * 个股洞察弹窗（高保真重构）
 * 全屏遮罩(bg 55% + blur6, 点遮罩关闭) + modalIn 入场；面板 min(1240px,96vw)×max 92vh。
 * 头部：股票名 + 盘面洞察 + 代码 + 价格(按涨跌上色) ··· 生成时间 + 关闭✕。
 * Body 双栏 1.6fr/1fr：左图表区(日线均线 + MACD + 股东人数 + 筹码分布 + 归母净利润)，
 * 右结构解读(✦智能解盘 + 大事提醒 + 综合解读)。涨=红 跌=绿。
 */

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

function EmptyChart({ label }: { label: string }) {
  return (
    <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: 'var(--text-faint)' }}>
      {label}
    </div>
  )
}

function LegendDot({ color, label, shape = 'line' }: { color: string; label: string; shape?: 'line' | 'bar' }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-dim)' }}>
      {shape === 'bar' ? (
        <span style={{ display: 'inline-block', height: 11, width: 7, borderRadius: 2, background: color }} />
      ) : (
        <span style={{ display: 'inline-block', height: 2.5, width: 12, borderRadius: 2, background: color }} />
      )}
      {label}
    </span>
  )
}

function ShareholderChart({ data }: { data: ShareholderPoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无股东人数数据" />
  const [min, max] = range(data.map((item) => item.ashare_holder))
  const innerWidth = CHART_WIDTH - PAD_X * 2
  const barWidth = Math.max(20, (innerWidth / data.length) * 0.5)
  const y0 = scaleY(min, min, max)
  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} style={{ width: '100%', height: 220 }}>
      <line x1={PAD_X} y1={y0} x2={CHART_WIDTH - PAD_X} y2={y0} stroke="var(--grid)" />
      {data.map((item, index) => {
        const x = PAD_X + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth)
        const y = scaleY(item.ashare_holder, min, max)
        return (
          <g key={item.timestamp}>
            <rect x={x - barWidth / 2} y={y} width={barWidth} height={Math.max(1, y0 - y)} fill="var(--ma120)" opacity={0.8} />
            <text x={x} y={y - 6} textAnchor="middle" fill="var(--text-dim)" fontSize="11">{formatWan(item.ashare_holder)}</text>
            <text x={x} y={CHART_HEIGHT - 10} textAnchor="middle" fill="var(--text-faint)" fontSize="11">{item.date.slice(2, 7)}</text>
          </g>
        )
      })}
    </svg>
  )
}

function ChipMetric({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ height: 8, width: 8, borderRadius: 2, background: color }} />
        <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginTop: 4 }} className="num">{value}</div>
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
  const histogram = selected ? data?.histograms[selected.date] || data?.histogram || [] : []

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

  if (!data || snapshots.length === 0 || !selected || !chart) return <EmptyChart label="暂无筹码分布数据" />

  const markerRows: Array<{ label: string; value: number | null; color: string }> = [
    { label: '平均成本', value: selected.avg_cost, color: 'var(--ma5)' },
    { label: '支撑位', value: selected.support_price, color: 'var(--ma20)' },
    { label: '压力位', value: selected.pressure_price, color: 'var(--ma120)' },
  ]

  /**
   * 标记价位标签去重叠：当平均成本/支撑位/压力位价位接近时，右侧文字会碰撞。
   * 先按真实 y 排序，自上而下强制最小间距错开标签位置；若整体超出底部则向上平移，
   * 最后 clamp 在绘图区内。价位虚线仍画在真实位置，并用引导线连回标签。
   */
  const MARKER_GAP = 17
  const markerLabels = markerRows
    .filter((m): m is { label: string; value: number; color: string } => m.value !== null)
    .map((m) => ({ ...m, y: chart.yFor(m.value), labelY: chart.yFor(m.value) }))
    .sort((a, b) => a.y - b.y)
  for (let i = 1; i < markerLabels.length; i += 1) {
    if (markerLabels[i].labelY - markerLabels[i - 1].labelY < MARKER_GAP) {
      markerLabels[i].labelY = markerLabels[i - 1].labelY + MARKER_GAP
    }
  }
  const maxLabelY = chart.height - 8
  const overflow = markerLabels.length ? markerLabels[markerLabels.length - 1].labelY - maxLabelY : 0
  if (overflow > 0) markerLabels.forEach((m) => (m.labelY -= overflow))
  const minLabelY = chart.top + 6
  markerLabels.forEach((m) => {
    if (m.labelY < minLabelY) m.labelY = minLabelY
  })

  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          borderRadius: 'var(--r-sm)',
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          padding: 12,
          marginBottom: 12,
        }}
      >
        <ChipMetric color="var(--ma5)" label="平均成本" value={selected.avg_cost.toFixed(2)} />
        <ChipMetric color="var(--ma20)" label="支撑位" value={selected.support_price?.toFixed(2) || '--'} />
        <ChipMetric color="var(--ma120)" label="压力位" value={selected.pressure_price?.toFixed(2) || '--'} />
        <ChipMetric color="var(--up)" label="盈利比例" value={formatPercent(selected.benefit_ratio)} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, fontSize: 11, color: 'var(--text-dim)', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <LegendDot color="var(--up)" label="获利持仓" shape="bar" />
          <LegendDot color="var(--down)" label="套牢持仓" shape="bar" />
        </div>
        <span>日期：{selected.date}</span>
      </div>

      <svg viewBox={`0 0 ${chart.width + 60} ${chart.height}`} style={{ width: '100%', height: 360 }}>
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const x = chart.left + tick * (chart.right - chart.left)
          return (
            <g key={tick}>
              <line x1={x} y1={chart.top} x2={x} y2={chart.bottom} stroke="var(--grid)" />
              <text x={x} y={chart.bottom + 26} textAnchor="middle" fill="var(--text-dim)" fontSize="11">{(chart.maxPercent * tick).toFixed(1)}%</text>
            </g>
          )
        })}
        {[chart.minPrice, (chart.minPrice + chart.maxPrice) / 2, chart.maxPrice].map((price) => (
          <text key={price} x={chart.left - 10} y={chart.yFor(price) + 4} textAnchor="end" fill="var(--text-faint)" fontSize="11">{price.toFixed(2)}</text>
        ))}
        {histogram.map((item) => {
          const y = chart.yFor(item.price)
          const barWidth = Math.max(1, chart.xFor(item.percent) - chart.left)
          return <rect key={`${selected.date}-${item.price}`} x={chart.left} y={y - 1} width={barWidth} height={2} fill={item.profitable ? 'var(--up)' : 'var(--down)'} opacity={0.92} />
        })}
        {markerLabels.map((marker) => (
          <g key={marker.label}>
            {/* 真实价位虚线 */}
            <line x1={chart.left} y1={marker.y} x2={chart.right} y2={marker.y} stroke="var(--text-faint)" strokeDasharray="5 5" opacity={0.55} />
            {/* 引导线：真实价位 → 错开后的标签 */}
            <line x1={chart.right} y1={marker.y} x2={chart.right + 110} y2={marker.labelY} stroke={marker.color} strokeDasharray="4 4" opacity={0.4} />
            <text x={chart.right + 118} y={marker.labelY + 4} fill={marker.color} fontSize="14" fontWeight="600">{marker.value.toFixed(2)}</text>
          </g>
        ))}
        <text x={chart.left} y={chart.height - 8} fill="var(--text-dim)" fontSize="12">{selected.interpretation}</text>
      </svg>

      <input
        type="range"
        min={0}
        max={Math.max(0, snapshots.length - 1)}
        value={safeIndex}
        onChange={(event) => setSelectedIndex(Number(event.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent)' }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-faint)', marginTop: 4 }}>
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
  const yoyPath = linePath(yoyData, (item) => item.yoy_percent as number, yoyMin, yoyMax, leftPad, rightPad)

  /**
   * 预计算每根柱子两个标签（归母净利润 / 同比）的纵向位置，避免在同一个 x 上
   * 因价位接近而文字重叠：先放各自的自然位置，若间距 < minGap 则把同比标签移到
   * 数据点另一侧，仍冲突则与利润标签错开堆叠，最后整体 clamp 在绘图区内。
   */
  const LABEL_GAP = 13
  const layout = data.map((item) => {
    const centerX = leftPad + groupWidth * data.indexOf(item) + groupWidth / 2
    const profitY = scaleY(item.net_profit_atsopc, profitMin, profitMax)
    let profitLabelY =
      item.net_profit_atsopc >= 0 ? Math.min(profitY, profitZero) - 8 : Math.max(profitY, profitZero) + 14
    const hasYoy = item.yoy_percent !== null
    const yoyY = hasYoy ? scaleY(item.yoy_percent as number, yoyMin, yoyMax) : null
    let yoyLabelY = yoyY !== null ? yoyY - 10 : null
    if (yoyY !== null && yoyLabelY !== null && Math.abs(yoyLabelY - profitLabelY) < LABEL_GAP) {
      const below = yoyY + 17
      if (Math.abs(below - profitLabelY) >= LABEL_GAP) {
        yoyLabelY = below
      } else {
        yoyLabelY = profitLabelY <= yoyLabelY ? profitLabelY + LABEL_GAP + 2 : profitLabelY - LABEL_GAP - 2
      }
    }
    profitLabelY = clamp(profitLabelY, labelTop, labelBottom)
    yoyLabelY = yoyLabelY !== null ? clamp(yoyLabelY, labelTop, labelBottom) : null
    // clamp 后再校正一次，避免双双被夹到边界后重叠
    if (yoyLabelY !== null && Math.abs(yoyLabelY - profitLabelY) < LABEL_GAP) {
      yoyLabelY = clamp(profitLabelY + LABEL_GAP + 2, labelTop, labelBottom)
      if (Math.abs(yoyLabelY - profitLabelY) < LABEL_GAP) yoyLabelY = clamp(profitLabelY - LABEL_GAP - 2, labelTop, labelBottom)
    }
    return { centerX, profitY, profitLabelY, yoyY, yoyLabelY }
  })

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} style={{ width: '100%', height: 220 }}>
      <line x1={leftPad} y1={PAD_TOP} x2={leftPad} y2={CHART_HEIGHT - PAD_BOTTOM} stroke="var(--grid)" />
      <line x1={CHART_WIDTH - rightPad} y1={PAD_TOP} x2={CHART_WIDTH - rightPad} y2={CHART_HEIGHT - PAD_BOTTOM} stroke="var(--grid)" />
      <line x1={leftPad} y1={profitZero} x2={CHART_WIDTH - rightPad} y2={profitZero} stroke="var(--grid)" strokeDasharray="4 4" />
      {profitTicks.map((tick) => (
        <text key={`profit-${tick}`} x={leftPad - 8} y={scaleY(tick, profitMin, profitMax) + 4} textAnchor="end" fill="var(--text-dim)" fontSize="10">{(tick / 1e8).toFixed(0)}亿</text>
      ))}
      {yoyTicks.map((tick) => (
        <text key={`yoy-${tick}`} x={CHART_WIDTH - rightPad + 8} y={scaleY(tick, yoyMin, yoyMax) + 4} textAnchor="start" fill="var(--text-dim)" fontSize="10">{tick.toFixed(0)}%</text>
      ))}
      {data.map((item, index) => {
        const { centerX, profitY, profitLabelY } = layout[index]
        return (
          <g key={item.report_name}>
            <rect x={centerX - barWidth / 2} y={Math.min(profitY, profitZero)} width={barWidth} height={Math.max(1, Math.abs(profitZero - profitY))} fill="var(--up)" opacity={0.78} />
            <text x={centerX} y={profitLabelY} textAnchor="middle" fill="var(--up)" fontSize="11">{formatYi(item.net_profit_atsopc)}</text>
            <text x={centerX} y={CHART_HEIGHT - 10} textAnchor="middle" fill="var(--text-faint)" fontSize="11">{item.report_name.replace('年报', '')}</text>
          </g>
        )
      })}
      {yoyPath && <path d={yoyPath} fill="none" stroke="var(--ma20)" strokeWidth="2.2" />}
      {data.map((item, index) => {
        const { centerX, yoyY, yoyLabelY } = layout[index]
        if (yoyY === null || yoyLabelY === null) return null
        return (
          <g key={`${item.report_name}-yoy`}>
            <circle cx={centerX} cy={yoyY} r="3.5" fill="var(--ma20)" />
            <text x={centerX} y={yoyLabelY} textAnchor="middle" fill="var(--ma20)" fontSize="11">{(item.yoy_percent as number).toFixed(1)}%</text>
          </g>
        )
      })}
    </svg>
  )
}

function ChartBlock({
  title,
  sub,
  legend,
  height,
  children,
}: {
  title: string
  sub: string
  legend?: ReactNode
  height?: number
  children: ReactNode
}) {
  return (
    <div className="card" style={{ background: 'var(--surface-2)', padding: '14px 16px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 700 }}>{title}</div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{sub}</div>
        </div>
        {legend && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end' }}>{legend}</div>}
      </div>
      <div style={height ? { height } : undefined}>{children}</div>
    </div>
  )
}

/* ---------------- Markdown report ---------------- */
function parseTable(lines: string[], startIndex: number): { rows: string[][]; nextIndex: number } {
  const rows: string[][] = []
  let index = startIndex
  while (index < lines.length && lines[index].trim().startsWith('|')) {
    const cells = lines[index].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
    const isSeparator = cells.every((cell) => /^:?-{3,}:?$/.test(cell))
    if (!isSeparator) rows.push(cells)
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
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))
    nodes.push(
      <strong key={`${match.index}-${match[1]}`} style={{ fontWeight: 600, color: 'var(--text)' }}>{match[1]}</strong>,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
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
        <h2 key={key} style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text)', marginTop: key === 0 ? 0 : 18, marginBottom: 8 }}>
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
          <div key={key} style={{ overflowX: 'auto', margin: '12px 0', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)' }}>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {head.map((cell) => (
                    <th key={cell} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)', borderBottom: '1px solid var(--border)' }}>
                      {renderInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, rowIndex) => (
                  <tr key={`${row.join('-')}-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td key={`${cell}-${cellIndex}`} style={{ padding: '8px 12px', verticalAlign: 'top', color: 'var(--text-dim)', borderTop: '1px solid var(--border)', lineHeight: 1.5 }}>
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
        <ul key={key} style={{ listStyle: 'disc', paddingLeft: 20, margin: '8px 0', display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.6 }}>
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
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith('## ') &&
      !lines[index].trim().startsWith('|') &&
      !/^[-*]\s+/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(
      <p key={key} style={{ fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.65, margin: '8px 0' }}>
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
  const llmStatusText =
    diagnosis?.llm_status === 'error' || diagnosis?.llm_status === 'missing_config'
      ? '大模型调用失败，请配置 API'
      : ''

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 40,
        background: 'color-mix(in oklab, var(--bg) 55%, rgba(0,0,0,0.6))',
        backdropFilter: 'blur(6px)',
        WebkitBackdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 28,
        animation: 'fadeIn 0.25s var(--ease)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="panel"
        style={{
          width: 'min(1240px, 96vw)',
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'modalIn 0.32s var(--ease)',
          background: 'var(--surface)',
        }}
      >
        {/* 头部 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '18px 24px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, minWidth: 0, flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: 20, fontWeight: 700 }}>{stock.name}</h2>
            <span style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>盘面洞察</span>
            <span className="ticker" style={{ fontSize: 12, color: 'var(--text-faint)' }}>{stock.code}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flex: 'none' }}>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)' }}>
              生成 {diagnosis?.generated_at || '等待生成'}
            </span>
            <button
              onClick={onClose}
              className="card"
              style={{ cursor: 'pointer', borderRadius: 'var(--r-sm)', padding: '8px 16px', fontFamily: 'var(--font-cjk)', fontSize: 13, fontWeight: 600, color: 'var(--text-dim)', background: 'transparent' }}
            >
              关闭 ✕
            </button>
          </div>
        </div>

        {/* Body */}
        {loading ? (
          <div style={{ flex: 1, minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
            <div>
              <div style={{ fontSize: 14, color: 'var(--text)' }}>正在调取数据并计算诊断...</div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>历史收盘价、股东人数、财报和大事提醒会并行加载</div>
            </div>
          </div>
        ) : error ? (
          <div style={{ flex: 1, minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: 'var(--up)' }}>
            {error}
          </div>
        ) : diagnosis ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.6fr) minmax(0, 1fr)', flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {/* 左：图表区 */}
            <div style={{ minWidth: 0, overflowY: 'auto', padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 16, borderRight: '1px solid var(--border)' }}>
              <ChartBlock
                title="日线均线"
                sub="收盘价 · MA5 / MA20 / MA120 / MA240"
                height={300}
                legend={
                  <>
                    <LegendDot color="var(--price-line)" label="收盘" />
                    <LegendDot color="var(--ma5)" label="MA5" />
                    <LegendDot color="var(--ma20)" label="MA20" />
                    <LegendDot color="var(--ma120)" label="MA120" />
                    <LegendDot color="var(--ma240)" label="MA240" />
                  </>
                }
              >
                <MALineChart data={diagnosis.moving_averages} />
              </ChartBlock>

              <ChartBlock
                title="指标看板"
                sub="MACD · DIF / DEA / 柱状"
                height={196}
                legend={
                  <>
                    <LegendDot color="var(--ma5)" label="DIF" />
                    <LegendDot color="var(--ma20)" label="DEA" />
                    <LegendDot color="var(--up)" label="MACD" shape="bar" />
                  </>
                }
              >
                <MACDChart data={diagnosis.macd} />
              </ChartBlock>

              <ChartBlock title="股东人数变化" sub="近三年股东户数，反映筹码集中或分散趋势">
                <ShareholderChart data={diagnosis.shareholders} />
              </ChartBlock>

              <ChartBlock title="筹码分布" sub="东方财富K线与换手率，本地CYQ算法估算">
                <ChipDistributionChart data={diagnosis.chip_distribution} />
              </ChartBlock>

              <ChartBlock
                title="归母净利润与同比"
                sub="近五年年报，左轴归母净利润，右轴同比增速"
                legend={
                  <>
                    <LegendDot color="var(--up)" label="归母净利润" shape="bar" />
                    <LegendDot color="var(--ma20)" label="同比" />
                  </>
                }
              >
                <NetProfitChart data={diagnosis.net_profit} />
              </ChartBlock>
            </div>

            {/* 右：结构解读 */}
            <div style={{ minWidth: 0, overflowY: 'auto', padding: '20px 22px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 16 }}>
                <h3 style={{ fontSize: 15, fontWeight: 700 }}>结构解读</h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {llmStatusText && <span style={{ fontSize: 11, color: 'var(--up)' }}>{llmStatusText}</span>}
                  <button
                    onClick={() => onEnhance(stock)}
                    disabled={enhancing || loading}
                    style={{
                      cursor: enhancing || loading ? 'not-allowed' : 'pointer',
                      border: 'none',
                      borderRadius: 'var(--r-sm)',
                      padding: '7px 15px',
                      fontFamily: 'var(--font-cjk)',
                      fontWeight: 700,
                      fontSize: 12.5,
                      color: '#fff',
                      background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
                      boxShadow: '0 8px 18px -10px var(--accent)',
                      opacity: enhancing || loading ? 0.6 : 1,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {enhancing ? '解盘中...' : enhanced ? '返回' : '✦ 智能解盘'}
                  </button>
                </div>
              </div>

              <div style={{ background: 'var(--accent-soft)', border: '1px solid var(--accent-line)', borderRadius: 'var(--r-sm)', padding: '12px 14px', marginBottom: 18 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-bright)', letterSpacing: '0.08em', marginBottom: 5 }}>大事提醒</div>
                <div style={{ fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{diagnosis.event_summary}</div>
              </div>

              <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-faint)', letterSpacing: '0.1em', marginBottom: 12 }}>综合解读</div>
              <MarkdownReport content={diagnosis.diagnosis_report} />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
