import { Outlet, NavLink } from 'react-router-dom'
import { useThemeStore } from '../../stores/themeStore'

/**
 * 导航链接配置
 */
const NAV_ITEMS = [
  { key: 'dashboard', to: '/dashboard', label: '供应链看板' },
  { key: 'analysis', to: '/analysis', label: 'AI分析' },
  { key: 'config', to: '/config', label: '模型配置' },
]

/**
 * 全局布局组件
 * 包含顶部导航栏和页面内容区域
 */
export default function AppLayout() {
  const currentThemeId = useThemeStore((s) => s.currentTheme?.id)

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-bg-primary)' }}>
      {/* 顶部导航栏 */}
      <nav
        className="h-14 flex items-center px-6 border-b"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          borderColor: 'var(--color-border)',
        }}
      >
        {/* 应用标题 */}
        <h1
          className="text-lg font-bold mr-8"
          style={{ color: 'var(--color-accent)' }}
        >
          供应链股票大屏
        </h1>
        {/* 导航链接列表 */}
        <div className="flex gap-1">
          {NAV_ITEMS.map((item) => {
            const to = item.key === 'dashboard' && currentThemeId
              ? `/dashboard/${currentThemeId}`
              : item.to

            return (
              <NavLink
                key={item.key}
                to={to}
                className={({ isActive }) =>
                  `px-4 py-2 rounded-md text-sm transition-colors ${
                    isActive ? 'font-medium' : ''
                  }`
                }
                style={({ isActive }) => ({
                  backgroundColor: isActive ? 'var(--color-accent)' : 'transparent',
                  color: isActive ? '#ffffff' : 'var(--color-text-secondary)',
                })}
              >
                {item.label}
              </NavLink>
            )
          })}
        </div>
      </nav>
      {/* 页面主内容区域 - 各页面自行控制内边距 */}
      <main>
        <Outlet />
      </main>
    </div>
  )
}
