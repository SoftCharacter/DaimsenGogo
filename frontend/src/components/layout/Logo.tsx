/**
 * 品牌菱形 logo（内联 SVG）：外菱形描边 + 内框 + 中心圆点，颜色随强调色变化。
 * 移植自设计交接包 components.jsx 的 Logo。
 */
export default function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ flex: 'none' }}>
      <rect
        x="16"
        y="2"
        width="19.8"
        height="19.8"
        rx="4"
        transform="rotate(45 16 2)"
        fill="var(--accent)"
        opacity="0.18"
      />
      <rect
        x="16"
        y="7.2"
        width="12.4"
        height="12.4"
        rx="3"
        transform="rotate(45 16 7.2)"
        fill="none"
        stroke="var(--accent-bright)"
        strokeWidth="2"
      />
      <circle cx="16" cy="16" r="2.6" fill="var(--accent-bright)" />
    </svg>
  )
}
