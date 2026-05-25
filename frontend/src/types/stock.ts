/**
 * 实时行情数据
 */
export interface StockQuote {
  code: string;           // 股票代码
  name: string;           // 股票名称
  current_price: number;  // 当前价格
  prev_close: number;     // 昨收价
  open_price: number;     // 开盘价
  high: number;           // 最高价
  low: number;            // 最低价
  change: number;         // 涨跌额
  change_percent: number; // 涨跌幅
  volume: number;         // 成交额（元）
  volume_display: string; // 成交额展示文本
  timestamp: string;      // 数据时间戳
}

/**
 * K线数据点
 */
export interface KLinePoint {
  date: string;   // 日期
  open: number;   // 开盘价
  high: number;   // 最高价
  low: number;    // 最低价
  close: number;  // 收盘价
  volume: number; // 成交量
}

/**
 * SSE事件类型 - 分析执行流
 * 与后端 _make_event() 生成的事件结构一一对应
 */
export type SSEEvent =
  | { type: 'thinking'; content: string; step: number; plan_step?: string; attempt?: number }
  | { type: 'tool_call'; tool: string; input: string; step: number; plan_step?: string; attempt?: number }
  | { type: 'tool_result'; tool: string; output: string; step: number; plan_step?: string; attempt?: number }
  | { type: 'progress'; step: number; max_steps: number; phase?: string; plan_step?: string; attempt?: number }
  | { type: 'result'; theme: import('./theme').Theme }
  | { type: 'error'; message: string }
  | { type: 'done' };
