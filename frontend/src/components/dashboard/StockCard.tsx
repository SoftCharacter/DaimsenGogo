import type { StockItem } from '../../types/theme'
import type { StockQuote } from '../../types/stock'
import { formatPrice, formatChangePercent } from '../../utils/formatters'

/**
 * 股票行情卡片组件的属性接口
 */
interface StockCardProps {
  /** 股票基础信息（来自主题数据） */
  stock: StockItem
  /** 实时行情数据（可能尚未加载） */
  quote?: StockQuote
}

/**
 * 根据涨跌幅返回对应颜色
 * 红涨绿跌是A股惯例
 */
function changeColor(changePercent: number): string {
  if (changePercent > 0) return '#ef4444'  // 涨 - 红色
  if (changePercent < 0) return '#22c55e'  // 跌 - 绿色
  return '#94a3b8'                         // 平 - 灰色
}

/**
 * 股票行情卡片组件
 * 深色风格卡片，展示单只股票的基础信息和实时行情
 * 包含：名称代码、当前价格、涨跌幅、业务描述、占比标签
 */
export default function StockCard({ stock, quote }: StockCardProps) {
  /** 判断行情数据是否已加载 */
  const hasQuote = Boolean(quote)
  /** 涨跌幅颜色 */
  const color = hasQuote ? changeColor(quote!.change_percent) : '#94a3b8'

  return (
    <div className="rounded-lg border p-4 bg-[#151c2c] border-[#1e293b]
                    hover:border-[#6366f1]/50 transition-colors">
      {/* 上方：股票名称 + 代码 */}
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-[#e2e8f0] truncate">
          {stock.name}
        </h4>
        <span className="text-xs text-[#64748b] font-mono ml-2 shrink-0">
          {stock.code}
        </span>
      </div>

      {/* 中间：当前价格 + 涨跌幅 */}
      <div className="flex items-baseline gap-3 mb-3">
        {/* 当前价格（大字体） */}
        <span className="text-xl font-bold" style={{ color }}>
          {hasQuote ? formatPrice(quote!.current_price) : '--'}
        </span>
        {/* 涨跌幅标签 */}
        <span className="text-sm font-medium" style={{ color }}>
          {hasQuote ? formatChangePercent(quote!.change_percent) : '--'}
        </span>
      </div>

      {/* 下方：业务描述 + 占比标签 */}
      <p className="text-xs text-[#94a3b8] leading-relaxed mb-2 whitespace-pre-wrap break-words">
        {stock.description}
      </p>
      <div className="flex items-center justify-between">
        {/* 分类标签 */}
        <span className="text-[10px] text-[#64748b]">
          {stock.category_tag}
        </span>
        {/* 占比标签 */}
        <span className="inline-block px-2 py-0.5 rounded text-[10px]
                         font-medium bg-[#6366f1]/20 text-[#a5b4fc]">
          {stock.percentage}%
        </span>
      </div>
    </div>
  )
}
