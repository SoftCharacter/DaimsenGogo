import { useState, useCallback, useEffect } from 'react'
import type { Theme, Category } from '../../types/theme'
import CategoryEditor from './CategoryEditor'

/**
 * 完整结果编辑器组件的属性接口
 */
interface ResultEditorProps {
  /** 待编辑的主题数据 */
  theme: Theme
  /** 保存回调，传入更新后的完整主题 */
  onSave: (updated: Theme) => void
  /** 保存操作是否正在进行中 */
  saving?: boolean
}

/**
 * 完整分析结果编辑器组件
 *
 * 功能：
 * - 顶部可编辑主题名称（input）和描述（textarea）
 * - 中部展示CategoryEditor列表
 * - 提供"添加分类"按钮，新增空白分类
 * - 底部"保存"按钮，调用onSave回调提交更新
 *
 * @param theme - 待编辑的主题对象
 * @param onSave - 保存回调函数
 * @param saving - 是否正在保存中（控制按钮状态）
 */
export default function ResultEditor({ theme, onSave, saving = false }: ResultEditorProps) {
  /** 本地编辑副本，避免直接修改外部数据 */
  const [draft, setDraft] = useState<Theme>(() => structuredClone(theme))

  /** 外部主题切换时同步本地草稿 */
  useEffect(() => {
    setDraft(structuredClone(theme))
  }, [theme])

  /**
   * 更新主题名称
   */
  const handleNameChange = useCallback((name: string) => {
    setDraft((prev) => ({ ...prev, name }))
  }, [])

  /**
   * 更新主题描述
   */
  const handleDescChange = useCallback((description: string) => {
    setDraft((prev) => ({ ...prev, description }))
  }, [])

  /**
   * 更新指定位置的分类数据
   * @param index - 分类在列表中的索引
   * @param updated - 更新后的分类对象
   */
  const handleCategoryChange = useCallback((index: number, updated: Category) => {
    setDraft((prev) => {
      const categories = [...prev.categories]
      categories[index] = updated
      return { ...prev, categories }
    })
  }, [])

  /**
   * 删除指定位置的分类
   * @param index - 分类在列表中的索引
   */
  const handleCategoryDelete = useCallback((index: number) => {
    setDraft((prev) => ({
      ...prev,
      categories: prev.categories.filter((_, i) => i !== index),
    }))
  }, [])

  /**
   * 添加一个空白分类
   * 自动生成唯一ID和递增排序号
   */
  const handleAddCategory = useCallback(() => {
    const newCategory: Category = {
      id: `cat_${Date.now()}`,
      name: '新分类',
      order: draft.categories.length + 1,
      stocks: [],
    }
    setDraft((prev) => ({
      ...prev,
      categories: [...prev.categories, newCategory],
    }))
  }, [draft.categories.length])

  /**
   * 提交保存，将编辑后的主题数据传递给父组件
   */
  const handleSave = useCallback(() => {
    onSave(draft)
  }, [draft, onSave])

  return (
    <div className="space-y-5">
      {/* 主题基本信息编辑区 */}
      <div className="rounded-lg border p-4 bg-[#151c2c] border-[#1e293b] space-y-3">
        {/* 主题名称 */}
        <label className="block">
          <span className="text-xs text-[#94a3b8] mb-1 block">主题名称</span>
          <input
            type="text"
            value={draft.name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="输入主题名称"
            className="w-full px-3 py-2 rounded-md text-sm font-medium outline-none
                       bg-[#0a0e17] text-[#e2e8f0] border border-[#1e293b]
                       placeholder-[#475569]
                       focus:border-[#6366f1] transition-colors"
          />
        </label>
        {/* 主题描述 */}
        <label className="block">
          <span className="text-xs text-[#94a3b8] mb-1 block">主题描述</span>
          <textarea
            value={draft.description}
            onChange={(e) => handleDescChange(e.target.value)}
            placeholder="输入主题描述"
            rows={3}
            className="w-full px-3 py-2 rounded-md text-sm outline-none resize-y
                       bg-[#0a0e17] text-[#e2e8f0] border border-[#1e293b]
                       placeholder-[#475569]
                       focus:border-[#6366f1] transition-colors"
          />
        </label>
      </div>

      {/* 分类编辑列表 */}
      <div className="space-y-4">
        {draft.categories.map((category, index) => (
          <CategoryEditor
            key={category.id}
            category={category}
            onChange={(updated) => handleCategoryChange(index, updated)}
            onDelete={() => handleCategoryDelete(index)}
          />
        ))}
      </div>

      {/* 添加分类按钮 */}
      <button
        onClick={handleAddCategory}
        className="w-full py-3 rounded-lg text-sm font-medium
                   border border-dashed border-[#1e293b] text-[#94a3b8]
                   hover:border-[#6366f1] hover:text-[#e2e8f0]
                   transition-colors"
      >
        + 添加分类
      </button>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2.5 rounded-md text-sm font-medium
                     bg-[#6366f1] text-white
                     hover:bg-[#5558e6] transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '保存中...' : '保存修改'}
        </button>
      </div>
    </div>
  )
}
