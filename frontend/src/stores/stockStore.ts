import { create } from 'zustand'
import type { StockQuote } from '../types/stock'
import { fetchQuotes as apiFetchQuotes } from '../api/stockApi'

/**
 * 行情Store状态接口
 * 定义股票实时行情相关的状态字段和操作方法
 */
interface StockState {
  quotes: Record<string, StockQuote>  // 股票代码 → 行情数据的映射表
  loading: boolean                     // 是否正在加载行情数据
  error: string | null                 // 错误信息

  /** 批量获取股票实时行情并更新本地状态 */
  fetchQuotes: (codes: string[], taskId?: string) => Promise<void>
}

/**
 * 行情状态管理Store
 * 使用zustand管理股票实时行情数据的全局状态
 * 行情数据以 code → StockQuote 映射表的形式存储，便于按代码快速查找
 */
export const useStockStore = create<StockState>((set) => ({
  /* ---------- 初始状态 ---------- */
  quotes: {},
  loading: false,
  error: null,

  /**
   * 批量获取股票实时行情
   * 请求成功后将返回的行情数组转换为映射表，与现有数据合并
   * 采用合并策略（而非替换），避免覆盖其他代码的行情数据
   * @param codes - 股票代码数组，如 ["SZ:002261", "SH:600000"]
   */
  fetchQuotes: async (codes: string[], taskId?: string) => {
    // 空数组时直接返回，避免无意义的请求
    if (codes.length === 0) return

    set({ loading: true, error: null })
    try {
      const quoteList = await apiFetchQuotes(codes, taskId)
      // 将行情数组转换为以code为键的映射表
      const newQuotes: Record<string, StockQuote> = {}
      for (const quote of quoteList) {
        newQuotes[quote.code] = quote
      }
      // 与现有数据合并，保留未请求的股票行情
      set((state) => ({
        quotes: { ...state.quotes, ...newQuotes },
        loading: false,
      }))
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '获取行情数据失败'
      set({ error: message, loading: false })
    }
  },
}))
