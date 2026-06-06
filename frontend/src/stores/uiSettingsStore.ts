import { create } from 'zustand'

/**
 * 视觉设置 Store
 * ----------------------------------------------------------------
 * 管理设计交接包定义的可配置项：设计方向 / 深浅主题 / 强调色 / 卡片密度 / 场景背景。
 * 这些设置写入 <html data-theme data-dir> 与 --accent-* / --card-min CSS 变量，
 * 并通过 body class（cosmos-on / day-on）切换毛玻璃场景背景。
 *
 * 注意：本 store 与 themeStore 不同——themeStore 管理「供应链分析主题」业务数据，
 * 本 store 仅负责界面外观偏好，持久化到 localStorage。
 */

export type Direction = 'aurora' | 'terminal'
export type ThemeMode = 'dark' | 'light'
export type AccentKey = '靛蓝' | '科技蓝' | '青碧' | '琥珀' | '品红'

/** 强调色预设（oklch 色相/彩度，hex 仅用于设置面板色块预览） */
export const ACCENTS: Record<AccentKey, { h: number; c: number; hex: string }> = {
  靛蓝: { h: 278, c: 0.17, hex: '#7b6bf0' },
  科技蓝: { h: 232, c: 0.15, hex: '#3a92e6' },
  青碧: { h: 196, c: 0.13, hex: '#27b6c9' },
  琥珀: { h: 70, c: 0.15, hex: '#c79a2a' },
  品红: { h: 350, c: 0.16, hex: '#e0578f' },
}

/** 卡片密度预设（对应 --card-min，紧凑/标准/宽松） */
export const CARD_DENSITIES = [
  { label: '紧凑', value: 290 },
  { label: '标准', value: 330 },
  { label: '宽松', value: 390 },
] as const

interface UISettings {
  dir: Direction
  theme: ThemeMode
  accent: AccentKey
  cardMin: number
  scene: boolean // 场景背景总开关（深色→星空，浅色→沙丘）
}

interface UISettingsState extends UISettings {
  setDir: (dir: Direction) => void
  setTheme: (theme: ThemeMode) => void
  setAccent: (accent: AccentKey) => void
  setCardMin: (cardMin: number) => void
  setScene: (scene: boolean) => void
}

const STORAGE_KEY = 'dg.ui-settings'

const DEFAULTS: UISettings = {
  dir: 'aurora',
  theme: 'dark',
  accent: '靛蓝',
  cardMin: 330,
  scene: true,
}

/** 从 localStorage 读取并与默认值合并 */
function loadSettings(): UISettings {
  if (typeof window === 'undefined') return DEFAULTS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw) as Partial<UISettings>
    const accent = parsed.accent && parsed.accent in ACCENTS ? parsed.accent : DEFAULTS.accent
    return { ...DEFAULTS, ...parsed, accent }
  } catch {
    return DEFAULTS
  }
}

/** 将设置应用到文档根元素与 body class，并持久化 */
function applySettings(s: UISettings): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.setAttribute('data-theme', s.theme)
  root.setAttribute('data-dir', s.dir)
  const a = ACCENTS[s.accent] ?? ACCENTS['靛蓝']
  root.style.setProperty('--accent-h', String(a.h))
  root.style.setProperty('--accent-c', String(a.c))
  root.style.setProperty('--card-min', `${s.cardMin}px`)
  document.body.classList.toggle('cosmos-on', s.scene && s.theme === 'dark')
  document.body.classList.toggle('day-on', s.scene && s.theme === 'light')
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
  } catch {
    /* 忽略存储失败（隐私模式等） */
  }
}

const initial = loadSettings()
// 首屏即应用，避免主题闪烁
applySettings(initial)

export const useUISettings = create<UISettingsState>((set, get) => {
  const update = (patch: Partial<UISettings>) => {
    const next = { ...get(), ...patch } as UISettings
    applySettings(next)
    set(patch)
  }
  return {
    ...initial,
    setDir: (dir) => update({ dir }),
    setTheme: (theme) => update({ theme }),
    setAccent: (accent) => update({ accent }),
    setCardMin: (cardMin) => update({ cardMin }),
    setScene: (scene) => update({ scene }),
  }
})

/** 当前是否展示深色星空背景 */
export const selectCosmosOn = (s: UISettingsState) => s.scene && s.theme === 'dark'
/** 当前是否展示浅色沙丘背景 */
export const selectDayOn = (s: UISettingsState) => s.scene && s.theme === 'light'
