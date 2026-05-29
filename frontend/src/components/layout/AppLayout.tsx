import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useThemeStore } from '../../stores/themeStore'
import { useUISettings, selectCosmosOn, selectDayOn } from '../../stores/uiSettingsStore'
import CosmosBackground from './CosmosBackground'
import DayScene from './DayScene'
import Logo from './Logo'
import MarketStatus from './MarketStatus'
import SettingsMenu from './SettingsMenu'

/**
 * 顶部导航配置
 */
const NAV_ITEMS = [
  { key: 'dashboard', to: '/dashboard', label: '供应链看板' },
  { key: 'analysis', to: '/analysis', label: 'AI 分析' },
  { key: 'config', to: '/config', label: '模型配置' },
]

/**
 * 全局布局组件（高保真重构）
 * - 满屏 app-shell（flex 纵向，内部区域各自滚动）
 * - 动态场景背景：深色星空 / 浅色沙丘，随外观设置切换
 * - 顶部导航：品牌 + 实时时钟休市状态 + 胶囊分段 tab + 外观设置
 */
export default function AppLayout() {
  const currentThemeId = useThemeStore((s) => s.currentTheme?.id)
  const cosmosOn = useUISettings(selectCosmosOn)
  const dayOn = useUISettings(selectDayOn)
  const location = useLocation()

  return (
    <>
      {cosmosOn && <CosmosBackground />}
      {dayOn && <DayScene />}

      <div id="app-shell" style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* 顶部导航栏 */}
        <header
          style={{
            height: 'var(--nav-h)',
            flex: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 22px',
            borderBottom: '1px solid var(--border)',
            position: 'relative',
            zIndex: 20,
            background: 'color-mix(in oklab, var(--bg) 70%, transparent)',
            backdropFilter: 'blur(14px)',
            WebkitBackdropFilter: 'blur(14px)',
          }}
        >
          {/* 左：品牌 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 240 }}>
            <Logo size={24} />
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
              <span
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontWeight: 700,
                  fontSize: 17,
                  letterSpacing: '-0.01em',
                }}
              >
                Daimsen<span style={{ color: 'var(--accent-bright)' }}>Gogo</span>
              </span>
              <span style={{ fontSize: 10.5, color: 'var(--text-faint)', letterSpacing: '0.32em', marginTop: 1 }}>
                供应链股票大屏
              </span>
            </div>
          </div>

          {/* 中：实时时钟 + 休市状态 */}
          <MarketStatus />

          {/* 右：胶囊分段 tab + 外观设置 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 240, justifyContent: 'flex-end' }}>
            <nav
              style={{
                display: 'flex',
                gap: 4,
                background: 'var(--surface-2)',
                padding: 4,
                borderRadius: 'var(--r-pill)',
                border: '1px solid var(--border)',
              }}
            >
              {NAV_ITEMS.map((item) => {
                const to =
                  item.key === 'dashboard' && currentThemeId ? `/dashboard/${currentThemeId}` : item.to
                const active = location.pathname.startsWith(item.to)
                return (
                  <NavLink
                    key={item.key}
                    to={to}
                    style={{
                      border: 'none',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-cjk)',
                      fontWeight: 600,
                      fontSize: 13.5,
                      padding: '8px 16px',
                      borderRadius: 'var(--r-pill)',
                      transition: 'all 0.2s var(--ease)',
                      textDecoration: 'none',
                      color: active ? '#fff' : 'var(--text-dim)',
                      background: active ? 'var(--accent)' : 'transparent',
                      boxShadow: active ? '0 6px 18px -8px var(--accent)' : 'none',
                    }}
                  >
                    {item.label}
                  </NavLink>
                )
              })}
            </nav>
            <SettingsMenu />
          </div>
        </header>

        {/* 主内容区域 */}
        <main style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <Outlet />
        </main>
      </div>
    </>
  )
}
