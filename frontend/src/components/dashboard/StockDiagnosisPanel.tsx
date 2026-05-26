import type { ReactNode } from 'react'
import type {
  MacdPoint,
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
  error: string
  onClose: () => void
}

function formatYi(value: number): string {
  return `${(value / 1e8).toFixed(2)}亿`
}

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(1)}万`
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
): string {
  if (data.length === 0) return ''
  const innerWidth = CHART_WIDTH - PAD_X * 2
  return data
    .map((item, index) => {
      const x = PAD_X + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth)
      const y = scaleY(getValue(item), min, max)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
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

function NetProfitChart({ data }: { data: NetProfitPoint[] }) {
  if (data.length === 0) return <EmptyChart label="暂无近五年归母净利润数据" />

  const profitValues = data.map((item) => item.net_profit_atsopc)
  const yoyValues = data.map((item) => item.yoy_percent ?? 0)
  const [profitMin, profitMax] = range([0, ...profitValues])
  const [yoyMin, yoyMax] = range([0, ...yoyValues])
  const innerWidth = CHART_WIDTH - PAD_X * 2
  const groupWidth = innerWidth / data.length
  const barWidth = Math.min(34, groupWidth * 0.26)
  const profitZero = scaleY(0, profitMin, profitMax)
  const yoyZero = scaleY(0, yoyMin, yoyMax)

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full h-[220px]">
      <line x1={PAD_X} y1={profitZero} x2={CHART_WIDTH - PAD_X} y2={profitZero} stroke="#334155" />
      {data.map((item, index) => {
        const centerX = PAD_X + groupWidth * index + groupWidth / 2
        const profitY = scaleY(item.net_profit_atsopc, profitMin, profitMax)
        const yoy = item.yoy_percent ?? 0
        const yoyY = scaleY(yoy, yoyMin, yoyMax)
        return (
          <g key={item.report_name}>
            <rect
              x={centerX - barWidth - 3}
              y={Math.min(profitY, profitZero)}
              width={barWidth}
              height={Math.max(1, Math.abs(profitZero - profitY))}
              fill="#ef4444"
              opacity={0.78}
            />
            <rect
              x={centerX + 3}
              y={Math.min(yoyY, yoyZero)}
              width={barWidth}
              height={Math.max(1, Math.abs(yoyZero - yoyY))}
              fill="#38bdf8"
              opacity={0.78}
            />
            <text x={centerX - barWidth / 2 - 3} y={Math.min(profitY, profitZero) - 6} textAnchor="middle" fill="#fecaca" fontSize="11">
              {formatYi(item.net_profit_atsopc)}
            </text>
            <text x={centerX + barWidth / 2 + 3} y={Math.min(yoyY, yoyZero) - 6} textAnchor="middle" fill="#bae6fd" fontSize="11">
              {item.yoy_percent === null ? '--' : `${item.yoy_percent.toFixed(1)}%`}
            </text>
            <text x={centerX} y={CHART_HEIGHT - 10} textAnchor="middle" fill="#64748b" fontSize="11">
              {item.report_name.replace('年报', '')}
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
  legend?: string
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
          <span className="text-xs text-[#94a3b8] shrink-0">
            {legend}
          </span>
        )}
      </div>
      {children}
    </section>
  )
}

export default function StockDiagnosisPanel({
  stock,
  diagnosis,
  loading,
  error,
  onClose,
}: StockDiagnosisPanelProps) {
  const llmStatusText = diagnosis?.llm_status === 'ok'
    ? '大模型已生成'
    : diagnosis?.llm_status === 'error'
      ? '大模型调用失败，显示本地摘要'
      : '未配置大模型，显示本地摘要'

  return (
    <div className="fixed inset-x-4 top-20 bottom-4 z-50 rounded-lg border border-[#334155] bg-[#0a0e17] shadow-2xl overflow-hidden">
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-[#1e293b] bg-[#0f172a]">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-bold text-[#e2e8f0] truncate">
                {stock.name} 个股诊断
              </h3>
              <span className="text-xs font-mono text-[#64748b]">{stock.code}</span>
            </div>
            <p className="text-xs text-[#94a3b8] mt-1">
              点击触发实时取数，生成时间：{diagnosis?.generated_at || '等待生成'}
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
                <ChartSection title="DIF / DEA / MACD" subtitle="近一年日线收盘价本地计算，参数 12 / 26 / 9" legend="橙 DIF · 蓝 DEA · 红绿 MACD">
                  <MacdChart data={diagnosis.macd} />
                </ChartSection>
                <ChartSection title="股东人数变化" subtitle="近三年股东户数，反映筹码集中或分散趋势">
                  <ShareholderChart data={diagnosis.shareholders} />
                </ChartSection>
                <ChartSection title="归母净利润与同比" subtitle="近五年年报，红柱为归母净利润，蓝柱为同比增速" legend="红 净利润 · 蓝 同比">
                  <NetProfitChart data={diagnosis.net_profit} />
                </ChartSection>
              </div>

              <aside className="rounded-lg border border-[#1e293b] bg-[#111827] p-4 h-fit">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <h4 className="text-sm font-semibold text-[#e2e8f0]">诊断报告</h4>
                  <span className="text-xs text-[#64748b]">{llmStatusText}</span>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-4">
                  <div className="border border-[#1e293b] rounded p-2">
                    <div className="text-xs text-[#64748b]">MACD点数</div>
                    <div className="text-sm text-[#e2e8f0] mt-1">{diagnosis.macd.length}</div>
                  </div>
                  <div className="border border-[#1e293b] rounded p-2">
                    <div className="text-xs text-[#64748b]">大事提醒</div>
                    <div className="text-sm text-[#e2e8f0] mt-1">{diagnosis.events.length}</div>
                  </div>
                  <div className="border border-[#1e293b] rounded p-2">
                    <div className="text-xs text-[#64748b]">股东样本</div>
                    <div className="text-sm text-[#e2e8f0] mt-1">{diagnosis.shareholders.length}</div>
                  </div>
                  <div className="border border-[#1e293b] rounded p-2">
                    <div className="text-xs text-[#64748b]">财报样本</div>
                    <div className="text-sm text-[#e2e8f0] mt-1">{diagnosis.net_profit.length}</div>
                  </div>
                </div>

                <div className="mb-4">
                  <h5 className="text-xs font-semibold text-[#cbd5e1] mb-2">大事提醒摘要</h5>
                  <p className="text-sm text-[#94a3b8] leading-6 whitespace-pre-wrap">
                    {diagnosis.event_summary}
                  </p>
                </div>

                <div>
                  <h5 className="text-xs font-semibold text-[#cbd5e1] mb-2">综合诊断</h5>
                  <p className="text-sm text-[#cbd5e1] leading-6 whitespace-pre-wrap">
                    {diagnosis.diagnosis_report}
                  </p>
                </div>
              </aside>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
