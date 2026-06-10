import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import {
  useUISettings,
  ACCENTS,
  CARD_DENSITIES,
  type Direction,
  type AppearanceMode,
  type AccentKey,
} from '../../stores/uiSettingsStore'

/**
 * 外观设置菜单（产品化自设计环境的 Tweaks 面板）
 * 暴露：场景背景 / 界面样式 / 深浅主题 / 强调色 / 卡片密度。
 * 全部走 uiSettingsStore，持久化到 localStorage。
 */

function SectionLabel({ children }: { children: string }) {
  return (
    <div
      style={{
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: '0.16em',
        color: 'var(--text-faint)',
        textTransform: 'uppercase',
        margin: '14px 0 8px',
      }}
    >
      {children}
    </div>
  )
}

function SegMenu<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { label: string; value: T }[]
  onChange: (v: T) => void
}) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 4,
        background: 'var(--surface-2)',
        padding: 4,
        borderRadius: 'var(--r-sm)',
        border: '1px solid var(--border)',
      }}
    >
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={String(o.value)}
            onClick={() => onChange(o.value)}
            style={{
              flex: 1,
              cursor: 'pointer',
              border: 'none',
              borderRadius: 'var(--r-sm)',
              padding: '7px 10px',
              fontFamily: 'var(--font-cjk)',
              fontSize: 12.5,
              fontWeight: 600,
              color: on ? '#fff' : 'var(--text-dim)',
              background: on ? 'var(--accent)' : 'transparent',
              transition: 'all 0.2s var(--ease)',
            }}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export default function SettingsMenu() {
  const { dir, mode, accent, cardMin, scene, setDir, setMode, setAccent, setCardMin, setScene } =
    useUISettings()

  return (
    <Popover style={{ position: 'relative' }}>
      <PopoverButton
        aria-label="外观设置"
        style={{
          cursor: 'pointer',
          width: 34,
          height: 34,
          borderRadius: 'var(--r-pill)',
          border: '1px solid var(--border)',
          background: 'var(--surface-2)',
          color: 'var(--text-dim)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 15,
        }}
      >
        ⚙
      </PopoverButton>
      <PopoverPanel
        anchor="bottom end"
        className="panel"
        style={{
          width: 280,
          marginTop: 10,
          padding: '14px 16px 16px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow)',
          zIndex: 50,
        }}
      >
        <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text)' }}>外观设置</div>

        <SectionLabel>场景背景</SectionLabel>
        <SegMenu<'on' | 'off'>
          value={scene ? 'on' : 'off'}
          options={[
            { label: '开启', value: 'on' },
            { label: '关闭', value: 'off' },
          ]}
          onChange={(v) => setScene(v === 'on')}
        />

        <SectionLabel>界面样式</SectionLabel>
        <SegMenu<Direction>
          value={dir}
          options={[
            { label: 'Aurora 大屏', value: 'aurora' },
            { label: 'Terminal 终端', value: 'terminal' },
          ]}
          onChange={setDir}
        />

        <SectionLabel>主题</SectionLabel>
        <SegMenu<AppearanceMode>
          value={mode}
          options={[
            { label: '深色', value: 'dark' },
            { label: '浅色', value: 'light' },
          ]}
          onChange={setMode}
        />

        <SectionLabel>强调色</SectionLabel>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(Object.entries(ACCENTS) as [AccentKey, (typeof ACCENTS)[AccentKey]][]).map(
            ([name, a]) => {
              const on = accent === name
              return (
                <button
                  key={name}
                  title={name}
                  onClick={() => setAccent(name)}
                  style={{
                    cursor: 'pointer',
                    width: 30,
                    height: 30,
                    borderRadius: 8,
                    background: a.hex,
                    border: on ? '2px solid #fff' : '2px solid transparent',
                    boxShadow: on ? `0 0 0 2px ${a.hex}` : 'none',
                    transition: 'all 0.15s',
                  }}
                />
              )
            },
          )}
        </div>

        <SectionLabel>卡片密度</SectionLabel>
        <SegMenu<number>
          value={cardMin}
          options={CARD_DENSITIES.map((d) => ({ label: d.label, value: d.value }))}
          onChange={setCardMin}
        />
      </PopoverPanel>
    </Popover>
  )
}
