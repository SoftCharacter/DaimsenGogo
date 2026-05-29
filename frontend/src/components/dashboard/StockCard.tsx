import type { StockItem } from '../../types/theme'
import type { StockQuote } from '../../types/stock'
import CardKline from './CardKline'

/**
 * 个股卡片（高保真重构）
 * 头部：股票名 + 代码；价格行：价格(按涨跌上色) + 涨跌药丸；
 * 自绘 SVG 迷你 K 线；底部：● 环节名 + 盘面洞察 →。
 * 涨=红 跌=绿（A股惯例）。点击打开个股洞察。
 */
interface StockCardProps {
  stock: StockItem
  quote?: StockQuote
  taskId?: string
  delay?: number
  onClick?: (stock: StockItem) => void
}

export default function StockCard({ stock, quote, taskId, delay = 0, onClick }: StockCardProps) {
  const hasQuote = Boolean(quote)
  const up = hasQuote ? quote!.change_percent >= 0 : true
  const priceColor = hasQuote ? (up ? 'var(--up)' : 'var(--down)') : 'var(--text-faint)'

  return (
    <button
      type="button"
      onClick={() => onClick?.(stock)}
      className="card fade-in"
      style={{
        animationDelay: `${delay}ms`,
        cursor: 'pointer',
        textAlign: 'left',
        background: 'var(--surface)',
        padding: 0,
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
      }}
    >
      {/* 头部 + 价格 */}
      <div style={{ padding: '14px 16px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <span
            className="card-name"
            style={{ fontWeight: 600, fontSize: 15.5, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
          >
            {stock.name}
          </span>
          <span className="ticker" style={{ fontSize: 11, color: 'var(--text-faint)', flex: 'none', marginTop: 3 }}>
            {stock.code}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="num" style={{ fontSize: 26, fontWeight: 600, lineHeight: 1, color: priceColor }}>
            {hasQuote ? quote!.current_price.toFixed(2) : '--'}
          </span>
          {hasQuote && (
            <span
              className="num"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 3,
                padding: '3px 8px',
                borderRadius: 'var(--r-sm)',
                background: up ? 'var(--up-soft)' : 'var(--down-soft)',
                color: up ? 'var(--up)' : 'var(--down)',
                fontSize: 12.5,
                fontWeight: 700,
              }}
            >
              <span style={{ fontSize: 10 }}>{up ? '▲' : '▼'}</span>
              {up ? '+' : ''}
              {quote!.change_percent.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      {/* 自绘迷你 K 线 */}
      <div style={{ padding: '0 6px' }}>
        <CardKline code={stock.code} height={132} taskId={taskId} />
      </div>

      {/* 底部 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '9px 16px 13px',
          borderTop: '1px solid var(--border)',
          marginTop: 4,
        }}
      >
        <span style={{ fontSize: 11, color: 'var(--text-faint)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 5, height: 5, borderRadius: 99, background: 'var(--accent-bright)' }} />
          {stock.category_tag}
        </span>
        <span style={{ fontSize: 11, color: 'var(--accent-bright)', fontWeight: 600, opacity: 0.9 }}>盘面洞察 →</span>
      </div>
    </button>
  )
}
