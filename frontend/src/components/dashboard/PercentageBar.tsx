import type { StockItem } from '../../types/theme'
import { PERCENTAGE_COLORS } from '../../utils/constants'

/**
 * 占比条形图组件的属性接口
 */
interface PercentageBarProps {
  /** 股票列表，包含每只股票的占比信息 */
  stocks: StockItem[]
}

/**
 * 占比条形图组件
 * 以水平堆叠条形图的方式展示分类下每只股票的占比
 * 每段使用不同颜色区分，鼠标悬停显示详细信息
 */
export default function PercentageBar({ stocks }: PercentageBarProps) {
  /* 没有股票数据时不渲染 */
  if (stocks.length === 0) return null

  /** 计算所有股票的百分比总和，用于归一化宽度 */
  const total = stocks.reduce((sum, s) => sum + s.percentage, 0)

  return (
    <div className="mb-4">
      {/* 条形图容器：圆角、固定高度、深色背景 */}
      <div className="flex h-8 rounded-md overflow-hidden bg-[#1e293b]">
        {stocks.map((stock, idx) => {
          /** 根据总值计算每段的宽度百分比 */
          const widthPercent = total > 0 ? (stock.percentage / total) * 100 : 0
          /** 从预定义颜色列表中循环取色 */
          const color = PERCENTAGE_COLORS[idx % PERCENTAGE_COLORS.length]

          return (
            <div
              key={stock.code}
              className="flex items-center justify-center text-xs text-white font-medium overflow-hidden transition-all"
              style={{
                width: `${widthPercent}%`,
                backgroundColor: color,
                minWidth: widthPercent > 0 ? '2rem' : 0,
              }}
              title={`${stock.name}: ${stock.percentage}%`}
            >
              {/* 宽度足够时显示股票名+百分比 */}
              {widthPercent > 8 && (
                <span className="truncate px-1">
                  {stock.name} {stock.percentage}%
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
