import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useThemeStore } from '../../stores/themeStore'

/**
 * 主题侧栏组件的属性接口
 */
interface SidebarProps {
  /** 当前选中的主题ID */
  currentThemeId?: string
  /** 切换主题的回调 */
  onSelect: (id: string) => void
}

/**
 * 主题侧栏组件
 * 固定在大屏页面左侧，展示已保存的主题列表
 * 支持切换主题和跳转到分析页创建新主题
 */
export default function Sidebar({ currentThemeId, onSelect }: SidebarProps) {
  const navigate = useNavigate()
  /** 从store获取主题列表和加载方法 */
  const themes = useThemeStore((s) => s.themes)
  const loading = useThemeStore((s) => s.loading)
  const fetchThemes = useThemeStore((s) => s.fetchThemes)
  const deleteTheme = useThemeStore((s) => s.deleteTheme)

  /** 组件挂载时加载主题列表 */
  useEffect(() => {
    fetchThemes()
  }, [fetchThemes])

  /** 删除主题并在删除当前主题后回到空看板 */
  const handleDelete = async (themeId: string) => {
    if (!window.confirm('确定删除这个主题吗？')) return
    await deleteTheme(themeId)
    if (themeId === currentThemeId) {
      navigate('/dashboard')
    }
  }

  return (
    <div className="w-60 shrink-0 h-full flex flex-col
                    bg-[#0d1117] border-r border-[#1e293b]">
      {/* 侧栏标题 */}
      <div className="px-4 py-4 border-b border-[#1e293b]">
        <h3 className="text-sm font-medium text-[#e2e8f0]">主题列表</h3>
      </div>

      {/* 主题列表区域（可滚动） */}
      <div className="flex-1 overflow-y-auto py-2">
        {loading && themes.length === 0 && (
          <p className="text-xs text-[#64748b] px-4 py-2">加载中...</p>
        )}

        {!loading && themes.length === 0 && (
          <p className="text-xs text-[#64748b] px-4 py-2">
            暂无主题，请先进行分析
          </p>
        )}

        {/* 逐条渲染主题摘要 */}
        {themes.map((theme) => {
          const isActive = theme.id === currentThemeId
          return (
            <div
              key={theme.id}
              className={`group flex items-start gap-2 px-4 py-3 text-sm transition-colors
                ${isActive
                  ? 'bg-[#6366f1]/15 text-[#a5b4fc] border-r-2 border-[#6366f1]'
                  : 'text-[#94a3b8] hover:bg-[#151c2c] hover:text-[#e2e8f0]'
                }`}
            >
              <button
                onClick={() => onSelect(theme.id)}
                className="min-w-0 flex-1 text-left"
              >
                {/* 主题名称 */}
                <div className="font-medium truncate">{theme.name}</div>
                {/* 主题描述（截断） */}
                <div className="text-xs mt-0.5 opacity-70 truncate">
                  {theme.description}
                </div>
              </button>
              <button
                onClick={() => handleDelete(theme.id)}
                className="shrink-0 text-xs text-[#64748b] opacity-0 group-hover:opacity-100 hover:text-[#ef4444] transition-opacity"
              >
                删除
              </button>
            </div>
          )
        })}
      </div>

      {/* 底部：新建分析按钮 */}
      <div className="p-3 border-t border-[#1e293b]">
        <button
          onClick={() => navigate('/analysis')}
          className="w-full py-2 rounded-md text-sm font-medium
                     bg-[#6366f1] text-white hover:bg-[#5558e6]
                     transition-colors"
        >
          + 新建分析
        </button>
      </div>
    </div>
  )
}
