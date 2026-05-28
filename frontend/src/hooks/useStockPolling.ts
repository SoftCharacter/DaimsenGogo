/**
 * 实时行情轮询Hook
 *
 * 定时获取当前主题中所有股票的最新行情数据。
 * 使用 setInterval 实现周期性轮询，组件挂载时立即获取一次，
 * 卸载时自动清理定时器。通过 useRef 持有最新的 codes，
 * 避免闭包陷阱导致使用过时的股票代码列表。
 */
import { useEffect, useRef } from 'react'
import { useStockStore } from '../stores/stockStore'

/** 默认轮询间隔：30秒 */
const DEFAULT_INTERVAL_MS = 30_000

/**
 * 实时行情轮询Hook
 *
 * 以固定间隔周期性调用 stockStore.fetchQuotes 获取最新行情。
 * codes 变化时会重新设置轮询周期（重新开始计时），
 * codes 为空数组时不会发起任何请求。
 *
 * @param codes - 需要轮询行情的股票代码数组，如 ["SZ:002049", "SH:600000"]
 * @param intervalMs - 轮询间隔毫秒数，默认 30000ms（30秒）
 *
 * @example
 * ```tsx
 * // 在主题详情页中使用
 * const codes = theme.categories.flatMap(c => c.stocks.map(s => s.code))
 * useStockPolling(codes)
 * ```
 */
export function useStockPolling(
  codes: string[],
  taskId?: string,
  intervalMs: number = DEFAULT_INTERVAL_MS,
): void {
  /**
   * 使用ref保存最新的codes引用
   * 避免setInterval回调中捕获到过时的codes闭包值
   */
  const codesRef = useRef<string[]>(codes)
  codesRef.current = codes

  /**
   * 从store中获取fetchQuotes方法
   * zustand的selector返回的函数引用是稳定的，不会触发不必要的重渲染
   */
  const fetchQuotes = useStockStore((s) => s.fetchQuotes)

  useEffect(() => {
    /** codes为空时不需要轮询，直接返回 */
    if (codes.length === 0) return

    /** 组件挂载或codes变化时，立即获取一次最新行情 */
    fetchQuotes(codesRef.current, taskId)

    /**
     * 设置定时轮询
     * 回调内通过codesRef.current读取最新的codes，
     * 确保即使codes在interval期间发生变化，也能获取正确的股票列表
     */
    const timer = setInterval(() => {
      /** 定时触发时再次检查codes是否为空（可能在interval期间变化） */
      if (codesRef.current.length > 0) {
        fetchQuotes(codesRef.current, taskId)
      }
    }, intervalMs)

    /** 组件卸载或依赖变化时清除定时器，防止内存泄漏 */
    return () => {
      clearInterval(timer)
    }
  }, [codes, taskId, intervalMs, fetchQuotes])
}
