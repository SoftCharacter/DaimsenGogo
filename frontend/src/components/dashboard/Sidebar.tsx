import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useThemeStore } from '../../stores/themeStore'

/**
 * 主题侧栏（高保真重构）
 * 标题「主题列表」+ 计数徽标；主题卡片（选中态 accent-soft 底 + accent-line 边 +
 * 左侧亮色圆点，名称/2 行描述省略/更新时间）；底部「+ 新建分析」渐变按钮。
 * 悬停显示删除。
 */
interface SidebarProps {
  currentThemeId?: string
  onSelect: (id: string) => void
}

/** 截取日期部分（YYYY-MM-DD） */
function shortDate(value?: string): string {
  if (!value) return ''
  return value.slice(0, 10)
}

export default function Sidebar({ currentThemeId, onSelect }: SidebarProps) {
  const navigate = useNavigate()
  const themes = useThemeStore((s) => s.themes)
  const loading = useThemeStore((s) => s.loading)
  const fetchThemes = useThemeStore((s) => s.fetchThemes)
  const deleteTheme = useThemeStore((s) => s.deleteTheme)

  useEffect(() => {
    fetchThemes()
  }, [fetchThemes])

  const handleDelete = async (e: React.MouseEvent, themeId: string) => {
    e.stopPropagation()
    if (!window.confirm('确定删除这个主题吗？')) return
    await deleteTheme(themeId)
    if (themeId === currentThemeId) navigate('/dashboard')
  }

  return (
    <aside
      style={{
        width: 'var(--sidebar-w)',
        flex: 'none',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'color-mix(in oklab, var(--surface) 40%, transparent)',
      }}
    >
      {/* 标题 + 计数 */}
      <div style={{ padding: '18px 18px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.18em', color: 'var(--text-faint)', textTransform: 'uppercase' }}>
          主题列表
        </span>
        <span
          className="mono"
          style={{ fontSize: 11, color: 'var(--text-faint)', background: 'var(--surface-2)', padding: '2px 8px', borderRadius: 99 }}
        >
          {themes.length}
        </span>
      </div>

      {/* 列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && themes.length === 0 && (
          <p style={{ fontSize: 11.5, color: 'var(--text-faint)', padding: '8px 4px' }}>加载中...</p>
        )}
        {!loading && themes.length === 0 && (
          <p style={{ fontSize: 11.5, color: 'var(--text-faint)', padding: '8px 4px' }}>暂无主题，请先进行分析</p>
        )}

        {themes.map((t) => {
          const on = t.id === currentThemeId
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              className="card group"
              style={{
                textAlign: 'left',
                cursor: 'pointer',
                padding: '13px 14px',
                background: on ? 'var(--accent-soft)' : 'var(--surface)',
                borderColor: on ? 'var(--accent-line)' : 'var(--border)',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ width: 6, height: 6, borderRadius: 99, flex: 'none', background: on ? 'var(--accent-bright)' : 'var(--text-faint)' }} />
                  <span style={{ fontWeight: 600, fontSize: 13.5, color: on ? 'var(--text)' : 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.name}
                  </span>
                </span>
                <span
                  onClick={(e) => handleDelete(e, t.id)}
                  className="opacity-0 group-hover:opacity-100"
                  style={{ fontSize: 10.5, color: 'var(--text-faint)', transition: 'opacity 0.2s', flex: 'none' }}
                >
                  删除
                </span>
              </div>
              <span
                style={{
                  fontSize: 11.5,
                  color: 'var(--text-faint)',
                  lineHeight: 1.5,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {t.description}
              </span>
              <div style={{ display: 'flex', gap: 12, marginTop: 2 }}>
                <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>· 更新 {shortDate(t.updated_at)}</span>
              </div>
            </button>
          )
        })}
      </div>

      {/* 底部新建 */}
      <div style={{ padding: 14 }}>
        <button
          onClick={() => navigate('/analysis')}
          style={{
            width: '100%',
            cursor: 'pointer',
            border: 'none',
            borderRadius: 'var(--r-sm)',
            padding: 12,
            fontFamily: 'var(--font-cjk)',
            fontWeight: 600,
            fontSize: 13.5,
            color: '#fff',
            background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
            boxShadow: '0 10px 26px -12px var(--accent)',
          }}
        >
          + 新建分析
        </button>
      </div>
    </aside>
  )
}
