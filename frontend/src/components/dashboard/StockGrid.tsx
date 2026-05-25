import type { StockItem } from '../../types/theme'
import type { StockQuote } from '../../types/stock'
import StockCard from './StockCard'
import PercentageBar from './PercentageBar'

/**
 * 股票卡片网格组件的属性接口
 */
interface StockGridProps {
  /** 股票列表 */
  stocks: StockItem[]
  /** 行情数据映射表（code → StockQuote） */
  quotes: Record<string, StockQuote>
  /** 是否显示占比条形图（默认true） */
  showPercentageBar?: boolean
}

/**
 * 股票卡片网格组件
 * 将StockCard以响应式网格布局排列
 * 可选在顶部展示PercentageBar占比条形图
 */
export default function StockGrid({
  stocks,
  quotes,
  showPercentageBar = true,
}: StockGridProps) {
  /* 无股票数据时显示空状态 */
  if (stocks.length === 0) {
    return (
      <div className="text-center py-8 text-[#64748b] text-sm">
        暂无股票数据
      </div>
    )
  }

  return (
    <div>
      {/* 可选：占比条形图 */}
      {showPercentageBar && <PercentageBar stocks={stocks} />}

      {/* 响应式网格：小屏1列、中屏2列、大屏3列、超大屏4列 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {stocks.map((stock) => (
          <StockCard
            key={stock.code}
            stock={stock}
            quote={quotes[stock.code]}
          />
        ))}
      </div>
    </div>
  )
}
