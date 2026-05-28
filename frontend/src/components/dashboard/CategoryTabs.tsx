import type { Category } from '../../types/theme'

/**
 * 分类标签切换组件的属性接口
 */
interface CategoryTabsProps {
  /** 分类列表 */
  categories: Category[]
  /** 当前选中的分类ID，null表示"全部" */
  activeId: string | null
  /** 切换分类的回调，传null表示选中"全部" */
  onSelect: (id: string | null) => void
}

/**
 * 分类标签切换组件
 * 横向排列的标签按钮组，支持"全部"和各分类之间切换
 * 选中标签使用强调色高亮，未选中标签为暗色背景
 */
export default function CategoryTabs({
  categories,
  activeId,
  onSelect,
}: CategoryTabsProps) {
  /**
   * 获取标签按钮的样式类名
   * 选中状态使用强调色背景和白色文字
   * 未选中状态使用透明背景和灰色文字
   * @param isActive - 是否为选中状态
   */
  const tabClass = (isActive: boolean) =>
    `px-4 py-1.5 rounded-md text-sm cursor-pointer transition-colors whitespace-nowrap ${
      isActive
        ? 'bg-[#6366f1] text-white font-medium'
        : 'bg-[#151c2c] text-[#94a3b8] hover:bg-[#1e293b]'
    }`

  return (
    /* 标签容器：横向滚动，适应不同屏幕宽度 */
    <div className="flex gap-2 overflow-x-auto pb-1">
      {/* 固定的"全部"标签，activeId为null时高亮 */}
      <button
        className={tabClass(activeId === null)}
        onClick={() => onSelect(null)}
      >
        全部
      </button>

      {/* 动态渲染各分类标签 */}
      {categories.map((cat) => (
        <button
          key={cat.id}
          className={tabClass(activeId === cat.id)}
          onClick={() => onSelect(cat.id)}
        >
          {cat.name}
        </button>
      ))}
    </div>
  )
}
