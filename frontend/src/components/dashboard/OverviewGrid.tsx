import type { StockItem } from '../../types/theme'
import type { StockQuote } from '../../types/stock'
import { formatPrice, formatChangePercent } from '../../utils/formatters'
import MiniChart from './MiniChart'

/**
 * OverviewGrid组件属性接口
 */
interface OverviewGridProps {
  /** 股票列表（来自所有分类） */
  stocks: StockItem[]
  /** 行情数据映射表（code → StockQuote） */
  quotes: Record<string, StockQuote>
  /** 来源分析任务ID，用于隔离K线缓存 */
  taskId?: string
}

/**
 * 根据涨跌幅返回对应颜色样式
 * A股惯例：红涨绿跌
 * @param changePercent - 涨跌幅百分比
 * @returns 颜色十六进制值
 */
function getChangeColor(changePercent: number): string {
  if (changePercent > 0) return '#ef4444'  // 涨 - 红色
  if (changePercent < 0) return '#22c55e'  // 跌 - 绿色
  return '#94a3b8'                         // 平 - 灰色
}

/**
 * K线图总览网格组件
 * 将所有股票以响应式网格展示，每个格子包含：
 * - 股票名称和代码
 * - 当前价格和涨跌幅
 * - 迷你K线蜡烛图（MiniChart）
 *
 * 响应式布局：
 * - 小屏（<768px）：1列
 * - 中屏（768px~1024px）：2列
 * - 大屏（>1024px）：3列
 */
export default function OverviewGrid({ stocks, quotes, taskId }: OverviewGridProps) {
  /* 无数据时展示空状态 */
  if (stocks.length === 0) {
    return (
      <div className="flex items-center justify-center h-40">
        <p className="text-sm text-[#64748b]">暂无股票数据</p>
      </div>
    )
  }

  return (
    /* 响应式网格容器 */
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {stocks.map((stock) => {
        /* 从行情映射表中取出对应行情 */
        const quote = quotes[stock.code]
        const hasQuote = Boolean(quote)
        const color = hasQuote ? getChangeColor(quote.change_percent) : '#94a3b8'

        return (
          <div
            key={stock.code}
            className="rounded-lg border bg-[#151c2c] border-[#1e293b]
                       hover:border-[#6366f1]/50 transition-colors
                       overflow-hidden"
          >
            {/* 上半部分：股票信息 */}
            <div className="p-4 pb-2">
              {/* 名称和代码 */}
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-[#e2e8f0] truncate">
                  {stock.name}
                </h4>
                <span className="text-xs text-[#64748b] font-mono ml-2 shrink-0">
                  {stock.code}
                </span>
              </div>

              {/* 价格和涨跌幅 */}
              <div className="flex items-baseline gap-3">
                <span className="text-lg font-bold" style={{ color }}>
                  {hasQuote ? formatPrice(quote.current_price) : '--'}
                </span>
                <span className="text-sm font-medium" style={{ color }}>
                  {hasQuote ? formatChangePercent(quote.change_percent) : '--'}
                </span>
              </div>
            </div>

            {/* 下半部分：迷你K线图 */}
            <div className="px-1">
              <MiniChart code={stock.code} height={100} taskId={taskId} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
