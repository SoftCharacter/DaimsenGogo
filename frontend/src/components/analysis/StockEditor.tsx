import { useCallback } from 'react'
import type { StockItem } from '../../types/theme'

/**
 * 单只股票编辑组件的属性接口
 */
interface StockEditorProps {
  /** 当前股票数据 */
  stock: StockItem
  /** 字段变更回调 */
  onChange: (updated: StockItem) => void
  /** 删除该股票回调 */
  onDelete: () => void
}

/**
 * 编辑表单字段配置
 * 定义每个字段的label、key、placeholder和输入类型
 */
const FIELD_CONFIG: Array<{
  label: string
  key: keyof StockItem
  placeholder: string
  type: 'text' | 'number'
}> = [
  { label: '股票代码', key: 'code', placeholder: '如 SZ:002049', type: 'text' },
  { label: '中文名称', key: 'name', placeholder: '公司中文名', type: 'text' },
  { label: '英文名称', key: 'name_en', placeholder: '公司英文名', type: 'text' },
  { label: '占比(%)', key: 'percentage', placeholder: '0-100', type: 'number' },
  { label: '业务描述', key: 'description', placeholder: '业务描述信息', type: 'text' },
  { label: '分类标签', key: 'category_tag', placeholder: '所属分类名称', type: 'text' },
]

/**
 * 单只股票编辑表单组件
 *
 * 功能：
 * - 展示并编辑StockItem的全部字段（name/code/name_en/percentage/description/category_tag）
 * - 右上角提供红色删除按钮
 * - 每个字段使用 label + input 单行布局
 *
 * @param stock - 当前股票数据
 * @param onChange - 字段值变更时的回调
 * @param onDelete - 点击删除按钮的回调
 */
export default function StockEditor({ stock, onChange, onDelete }: StockEditorProps) {
  /**
   * 处理字段值变更
   * 根据字段类型（text/number）自动转换值的类型
   */
  const handleFieldChange = useCallback(
    (key: keyof StockItem, value: string, type: 'text' | 'number') => {
      onChange({
        ...stock,
        /* 数字类型字段需转为number，限制范围0-100 */
        [key]: type === 'number'
          ? Math.max(0, Math.min(100, Number(value) || 0))
          : value,
      })
    },
    [stock, onChange],
  )

  return (
    <div className="relative rounded-md border p-3 bg-[#0a0e17] border-[#1e293b]">
      {/* 右上角删除按钮 */}
      <button
        onClick={onDelete}
        title="删除此股票"
        className="absolute top-2 right-2 w-6 h-6 flex items-center justify-center
                   rounded text-xs font-bold
                   text-[#ef4444] hover:bg-[#ef4444]/10
                   transition-colors"
      >
        X
      </button>

      {/* 表单字段列表 - 使用grid两列布局 */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 pr-8">
        {FIELD_CONFIG.map(({ label, key, placeholder, type }) => (
          <label key={key} className="flex items-center gap-2 text-xs">
            {/* 字段标签 */}
            <span className="w-16 shrink-0 text-[#94a3b8]">{label}</span>
            {/* 输入框 */}
            <input
              type={type}
              value={stock[key]}
              onChange={(e) => handleFieldChange(key, e.target.value, type)}
              placeholder={placeholder}
              className="flex-1 px-2 py-1 rounded text-xs outline-none
                         bg-[#151c2c] text-[#e2e8f0] border border-[#1e293b]
                         placeholder-[#475569]
                         focus:border-[#6366f1] transition-colors"
            />
          </label>
        ))}
      </div>
    </div>
  )
}
