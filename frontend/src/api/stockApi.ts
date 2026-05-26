import client from './client'
import type { StockQuote, KLinePoint, StockDiagnosis } from '../types/stock'

/**
 * 行情数据API模块
 * 提供股票实时行情、K线数据和搜索接口
 */

/**
 * 股票搜索结果条目
 */
interface StockSearchResult {
  code: string          // 股票代码，如 "SZ:002261"
  name: string          // 股票名称
  current_price: number // 当前价格
}

/**
 * 批量获取股票实时行情
 * 将股票代码数组拼接为逗号分隔字符串传递给后端
 * @param codes - 股票代码数组，如 ["SZ:002261", "SH:600000"]
 * @returns 行情数据数组
 */
export async function fetchQuotes(codes: string[], taskId?: string): Promise<StockQuote[]> {
  // 将代码数组用逗号拼接为查询参数
  const codesParam = codes.join(',')
  const res = await client.get<{ data: StockQuote[] }>('/stocks/quotes', {
    params: { codes: codesParam, task_id: taskId || undefined },
  })
  // 后端返回 { data: [...] } 结构，提取内层data
  return res.data.data
}

/**
 * 获取单只股票的K线数据
 * @param code - 股票代码，如 "SZ:002261"
 * @param period - K线周期，默认 "daily"（日K）
 * @param count - 获取数据点数量，默认22（近一个月日K）
 * @returns K线数据点数组
 */
export async function fetchKline(
  code: string,
  period: string = 'daily',
  count: number = 22,
  taskId?: string,
): Promise<KLinePoint[]> {
  const res = await client.get<{ data: KLinePoint[] }>('/stocks/kline', {
    params: { code, period, count, task_id: taskId || undefined },
  })
  // 后端返回 { data: [...] } 结构，提取内层data
  return res.data.data
}

export async function fetchStockDiagnosis(
  code: string,
  name?: string,
): Promise<StockDiagnosis> {
  const res = await client.get<StockDiagnosis>('/stocks/diagnosis', {
    params: { code, name: name || undefined },
    timeout: 180000,
  })
  return res.data
}

/**
 * 根据关键词搜索股票
 * 支持按名称或代码模糊搜索
 * @param keyword - 搜索关键词
 * @returns 匹配的股票列表（代码、名称、当前价格）
 */
export async function searchStocks(keyword: string): Promise<StockSearchResult[]> {
  const res = await client.get<{ data: StockSearchResult[] }>('/stocks/search', {
    params: { q: keyword },
  })
  // 后端返回 { data: [...] } 结构，提取内层data
  return res.data.data
}
