/**
 * DaimsenGogo 定稿品牌标志（方向 A · 精炼实心）
 * 内联 logo/daimsengogo-mark.svg —— 字母 D 与鸟头双关标，fill="currentColor"，
 * 颜色由 CSS 变量 --brand-logo 驱动（深色亮紫 / 浅色深紫），一个文件适配所有主题。
 *
 * 几何：标志净高占 512 视图的 312（y100–412），即四周自带 ≥25% 安全留白。
 * 顶栏默认 size=40 → 标志净高约 24px（落在建议的 22–26px 区间）。
 */
export default function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ color: 'var(--brand-logo)', flex: 'none', display: 'block' }}
      aria-label="DaimsenGogo"
      role="img"
    >
      <defs>
        <mask id="dg-k-cc">
          <rect x="92" y="100" width="158" height="312" rx="6" fill="#fff" />
          <circle cx="256" cy="256" r="156" fill="#fff" />
          <circle cx="288" cy="256" r="118" fill="#000" />
        </mask>
        <clipPath id="dg-c-cc">
          <circle cx="288" cy="256" r="118" />
        </clipPath>
      </defs>
      <g fill="currentColor">
        <rect x="0" y="0" width="512" height="512" mask="url(#dg-k-cc)" />
        <circle cx="248" cy="210" r="30" />
        <g clipPath="url(#dg-c-cc)">
          <path d="M170 342 L430 240 L444 396 L156 396 Z" />
        </g>
      </g>
    </svg>
  )
}
