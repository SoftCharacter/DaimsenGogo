import { useEffect, useRef, useState } from 'react'
import { fetchKline } from '../../api/stockApi'
import type { KLinePoint } from '../../types/stock'
import CandleChart from '../charts/CandleChart'

const MONTH_KLINE_COUNT = 22

/**
 * 个股卡片迷你 K 线（自绘 SVG）
 * 进入可视区域后才请求 /api/stocks/kline，避免首屏一次性触发所有请求。
 * 替换原 lightweight-charts 版 MiniChart，视觉对齐设计交接包。
 */
export default function CardKline({
  code,
  height = 132,
  taskId,
}: {
  code: string
  height?: number
  taskId?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const [data, setData] = useState<KLinePoint[] | null>(null)
  const [error, setError] = useState(false)

  /* 懒加载：进入视口才标记可见 */
  useEffect(() => {
    const el = containerRef.current
    if (!el || visible) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '160px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [visible])

  /* 可见后拉取 K 线 */
  useEffect(() => {
    if (!visible) return
    let cancelled = false
    setError(false)
    fetchKline(code, 'daily', MONTH_KLINE_COUNT, taskId)
      .then((points) => {
        if (!cancelled) setData(points)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [code, taskId, visible])

  return (
    <div ref={containerRef} style={{ width: '100%', height }}>
      {data && data.length > 0 ? (
        <CandleChart data={data} height={height} />
      ) : (
        <div
          style={{
            height,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 11,
            color: error ? 'var(--down)' : 'var(--text-faint)',
          }}
        >
          {error ? '加载失败' : '加载中...'}
        </div>
      )}
    </div>
  )
}
