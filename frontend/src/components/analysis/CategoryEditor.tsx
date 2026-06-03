import { useCallback, useState } from 'react'
import type { Category, StockItem } from '../../types/theme'
import StockEditor from './StockEditor'

/**
 * 单个分类编辑组件的属性接口
 */
interface CategoryEditorProps {
  /** 当前分类数据 */
  category: Category
  /** 分类数据变更回调 */
  onChange: (updated: Category) => void
  /** 删除该分类回调 */
  onDelete: () => void
}

/**
 * 单个分类编辑组件
 *
 * 功能：
 * - 编辑分类名称
 * - 展示分类下所有股票的StockEditor列表
 * - 提供"添加股票"按钮，新增空白StockItem
 * - 提供"删除分类"按钮，带确认提示
 *
 * @param category - 当前分类数据
 * @param onChange - 分类数据变更时的回调
 * @param onDelete - 删除分类时的回调
 */
export default function CategoryEditor({ category, onChange, onDelete }: CategoryEditorProps) {
  /** 删除确认状态：防止误操作 */
  const [confirmDelete, setConfirmDelete] = useState(false)

  /**
   * 更新分类名称
   * 同时同步更新分类下每只股票的 category_tag 字段
   */
  const handleNameChange = useCallback(
    (name: string) => {
      onChange({
        ...category,
        name,
        /* 同步修改所有股票的分类标签 */
        stocks: category.stocks.map((s) => ({ ...s, category_tag: name })),
      })
    },
    [category, onChange],
  )

  /**
   * 更新指定位置的股票数据
   * @param index - 股票在列表中的索引
   * @param updated - 更新后的股票对象
   */
  const handleStockChange = useCallback(
    (index: number, updated: StockItem) => {
      const stocks = [...category.stocks]
      stocks[index] = updated
      onChange({ ...category, stocks })
    },
    [category, onChange],
  )

  /**
   * 删除指定位置的股票
   * @param index - 股票在列表中的索引
   */
  const handleStockDelete = useCallback(
    (index: number) => {
      onChange({
        ...category,
        stocks: category.stocks.filter((_, i) => i !== index),
      })
    },
    [category, onChange],
  )

  /**
   * 添加一只空白股票到当前分类
   * 使用分类名称作为默认 category_tag
   */
  const handleAddStock = useCallback(() => {
    const newStock: StockItem = {
      code: '',
      name: '',
      name_en: '',
      percentage: 0,
      description: '',
      category_tag: category.name,
    }
    onChange({ ...category, stocks: [...category.stocks, newStock] })
  }, [category, onChange])

  /**
   * 处理删除分类点击
   * 第一次点击进入确认状态，第二次点击执行删除
   */
  const handleDeleteClick = useCallback(() => {
    if (confirmDelete) {
      onDelete()
    } else {
      setConfirmDelete(true)
      /* 3秒后自动取消确认状态 */
      setTimeout(() => setConfirmDelete(false), 3000)
    }
  }, [confirmDelete, onDelete])

  return (
    <div className="rounded-lg border p-4 bg-[#151c2c] border-[#1e293b]">
      {/* 分类头部：名称输入 + 删除按钮 */}
      <div className="flex items-center gap-3 mb-3">
        {/* 分类名称编辑输入框 */}
        <input
          type="text"
          value={category.name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="分类名称"
          className="flex-1 px-3 py-1.5 rounded-md text-sm font-medium outline-none
                     bg-[#0a0e17] text-[#e2e8f0] border border-[#1e293b]
                     focus:border-[#6366f1] transition-colors"
        />
        {/* 删除分类按钮 - 带确认机制 */}
        <button
          onClick={handleDeleteClick}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors
            ${confirmDelete
              ? 'bg-[#ef4444] text-white'
              : 'text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/10'
            }`}
        >
          {confirmDelete ? '确认删除' : '删除分类'}
        </button>
      </div>

      {/* 股票编辑列表 */}
      <div className="space-y-2">
        {category.stocks.map((stock, index) => (
          <StockEditor
            key={`${category.id}-stock-${index}`}
            stock={stock}
            onChange={(updated) => handleStockChange(index, updated)}
            onDelete={() => handleStockDelete(index)}
          />
        ))}
      </div>

      {/* 添加股票按钮 */}
      <button
        onClick={handleAddStock}
        className="mt-3 w-full py-2 rounded-md text-xs font-medium
                   border border-dashed border-[#1e293b] text-[#94a3b8]
                   hover:border-[#6366f1] hover:text-[#e2e8f0]
                   transition-colors"
      >
        + 添加股票
      </button>
    </div>
  )
}
