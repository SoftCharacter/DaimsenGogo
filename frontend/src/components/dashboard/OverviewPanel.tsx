import { useMemo } from 'react'
import type { StockItem } from '../../types/theme'
import type { StockQuote } from '../../types/stock'

/**
 * 板块概览面板（高保真重构）
 * 标题 + 均涨跌幅；涨跌广度条(红/灰/绿三段)；上涨/平盘/下跌计数 + 领涨股。
 * 仅统计已拿到实时行情的成分股；涨=红 跌=绿。
 */
export default function OverviewPanel({
  stocks,
  quotes,
}: {
  stocks: StockItem[]
  quotes: Record<string, StockQuote>
}) {
  const stats = useMemo(() => {
    const quoted = stocks
      .map((s) => quotes[s.code])
      .filter((q): q is StockQuote => Boolean(q))
    const count = quoted.length
    const up = quoted.filter((q) => q.change_percent > 0).length
    const down = quoted.filter((q) => q.change_percent < 0).length
    const flat = count - up - down
    const avg = count > 0 ? quoted.reduce((a, q) => a + q.change_percent, 0) / count : 0
    let top: StockQuote | null = null
    for (const q of quoted) {
      if (!top || q.change_percent > top.change_percent) top = q
    }
    return { count, up, down, flat, avg, top }
  }, [stocks, quotes])

  const { count, up, down, flat, avg, top } = stats
  const upPct = count > 0 ? (up / count) * 100 : 0
  const flatPct = count > 0 ? (flat / count) * 100 : 0
  const avgUp = avg >= 0

  return (
    <div
      className="panel fade-in"
      style={{ flex: 'none', width: 340, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.16em', color: 'var(--text-faint)' }}>
          板块概览
        </span>
        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: avgUp ? 'var(--up)' : 'var(--down)' }}>
          均 {avgUp ? '+' : ''}
          {avg.toFixed(2)}%
        </span>
      </div>

      {/* 广度条 */}
      <div style={{ display: 'flex', height: 8, borderRadius: 99, overflow: 'hidden', background: 'var(--surface-3)' }}>
        <div style={{ width: `${upPct}%`, background: 'var(--up)' }} />
        <div style={{ width: `${flatPct}%`, background: 'var(--text-faint)' }} />
        <div style={{ flex: 1, background: 'var(--down)' }} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        {([
          ['上涨', up, 'var(--up)'],
          ['平盘', flat, 'var(--text-dim)'],
          ['下跌', down, 'var(--down)'],
        ] as const).map(([label, value, color]) => (
          <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span className="num" style={{ fontSize: 20, fontWeight: 700, color }}>
              {value}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{label}</span>
          </div>
        ))}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            alignItems: 'flex-end',
            borderLeft: '1px solid var(--border)',
            paddingLeft: 16,
          }}
        >
          <span className="num" style={{ fontSize: 13, fontWeight: 700, color: top && top.change_percent >= 0 ? 'var(--up)' : 'var(--down)' }}>
            {top ? `${top.change_percent >= 0 ? '+' : ''}${top.change_percent.toFixed(2)}%` : '--'}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
            领涨 {top ? top.name : '--'}
          </span>
        </div>
      </div>
    </div>
  )
}
