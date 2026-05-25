import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  ColorType,
  CrosshairMode,
} from 'lightweight-charts'
import { fetchKline } from '../../api/stockApi'
import type { KLinePoint } from '../../types/stock'

const MONTH_KLINE_COUNT = 22

/**
 * MiniChart组件属性接口
 */
interface MiniChartProps {
  /** 股票代码，如 "SZ:002049" */
  code: string
  /** 图表高度(px)，默认120 */
  height?: number
  /** 来源分析任务ID，用于隔离K线缓存 */
  taskId?: string
}

/**
 * 将后端KLinePoint数据转换为lightweight-charts所需的蜡烛图数据格式
 * lightweight-charts要求time字段为字符串日期(yyyy-MM-dd)
 * @param points - 后端返回的K线数据点数组
 * @returns 转换后的蜡烛图数据数组
 */
function toChartData(points: KLinePoint[]) {
  return points.map((p) => ({
    time: p.date,        // 直接使用后端日期字符串
    open: p.open,
    high: p.high,
    low: p.low,
    close: p.close,
  }))
}

/**
 * 迷你K线图组件
 * 使用lightweight-charts渲染蜡烛图，适合嵌入卡片展示。
 * 数据来源固定为后端 /api/stocks/kline，前端不直连第三方行情源。
 * 特性：
 * - 自动调用fetchKline获取K线数据
 * - 深色主题配色
 * - 隐藏时间轴标签和水印
 * - ResizeObserver自适应容器宽度
 * - 组件销毁时自动清理资源
 */
export default function MiniChart({ code, height = 120, taskId }: MiniChartProps) {
  /** DOM容器引用 */
  const containerRef = useRef<HTMLDivElement>(null)
  /** chart实例引用，用于后续操作和清理 */
  const chartRef = useRef<IChartApi | null>(null)
  /** series实例引用，用于更新数据 */
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  /** 加载状态 */
  const [loading, setLoading] = useState(true)
  /** 错误状态 */
  const [error, setError] = useState(false)
  /** 图表是否进入可视区域 */
  const [visible, setVisible] = useState(false)

  /**
   * 创建图表实例
   * 在容器DOM就绪后初始化chart和candlestick series
   */
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    /* 创建图表实例，配置深色主题 */
    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      /* 深色背景和文字配色 */
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
        fontSize: 10,
      },
      /* 深色网格线 */
      grid: {
        vertLines: { color: 'rgba(30,41,59,0.5)' },
        horzLines: { color: 'rgba(30,41,59,0.5)' },
      },
      /* 隐藏右侧价格轴标签 */
      rightPriceScale: {
        visible: false,
      },
      /* 隐藏时间轴标签 */
      timeScale: {
        visible: false,
      },
      /* 隐藏十字光标 */
      crosshair: {
        mode: CrosshairMode.Hidden,
      },
      /* 禁用滚动和缩放，迷你图无需交互 */
      handleScroll: false,
      handleScale: false,
    })

    /* 添加蜡烛图系列，设置涨跌颜色 */
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444',           // 涨 - 红色
      downColor: '#22c55e',         // 跌 - 绿色
      borderUpColor: '#ef4444',     // 涨蜡烛边框
      borderDownColor: '#22c55e',   // 跌蜡烛边框
      wickUpColor: '#ef4444',       // 涨影线颜色
      wickDownColor: '#22c55e',     // 跌影线颜色
    })

    chartRef.current = chart
    seriesRef.current = series

    /* ResizeObserver: 监听容器宽度变化并同步更新图表尺寸 */
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect
        if (width > 0) {
          chart.resize(width, height)
        }
      }
    })
    observer.observe(container)

    /* 清理：组件卸载时销毁observer和chart */
    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  /**
   * 监听图表进入可视区域，避免首屏一次性触发所有K线请求
   */
  useEffect(() => {
    const container = containerRef.current
    if (!container || visible) return

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true)
        observer.disconnect()
      }
    }, { rootMargin: '160px' })

    observer.observe(container)
    return () => observer.disconnect()
  }, [visible])

  /**
   * 获取K线数据并渲染
   * code变化且进入可视区域后重新请求数据并更新图表
   */
  useEffect(() => {
    if (!visible || !seriesRef.current || !chartRef.current) return

    let cancelled = false
    setLoading(true)
    setError(false)

    fetchKline(code, 'daily', MONTH_KLINE_COUNT, taskId)
      .then((data) => {
        /* 防止组件卸载后设置状态 */
        if (cancelled || !seriesRef.current || !chartRef.current) return
        /* 转换数据格式并设置到series */
        const chartData = toChartData(data)
        seriesRef.current.setData(chartData)
        /* 自动缩放时间轴以适配所有数据 */
        chartRef.current.timeScale().fitContent()
        setLoading(false)
      })
      .catch(() => {
        if (!cancelled) {
          setError(true)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [code, taskId, visible])

  return (
    <div className="relative w-full" style={{ height }}>
      {/* 图表容器 */}
      <div ref={containerRef} className="w-full h-full" />
      {/* 加载中遮罩 */}
      {loading && visible && (
        <div className="absolute inset-0 flex items-center justify-center
                        bg-[#151c2c]/60">
          <span className="text-xs text-[#64748b]">加载中...</span>
        </div>
      )}
      {/* 错误提示 */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center
                        bg-[#151c2c]/60">
          <span className="text-xs text-[#ef4444]">加载失败</span>
        </div>
      )}
    </div>
  )
}
