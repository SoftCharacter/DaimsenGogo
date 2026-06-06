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

export interface MacdPoint {
  date: string;
  timestamp: number;
  close: number;
  dif: number;
  dea: number;
  macd: number;
}

export interface MovingAveragePoint {
  date: string;
  timestamp: number;
  close: number;
  ma5: number | null;
  ma20: number | null;
  ma120: number | null;
  ma240: number | null;
}

export interface ShareholderPoint {
  date: string;
  timestamp: number;
  ashare_holder: number;
  change_percent: number | null;
  price: number | null;
  per_amount: number | null;
  top_holder_ratio: number | null;
}

export interface NetProfitPoint {
  report_name: string;
  report_date: string;
  timestamp: number;
  net_profit_atsopc: number;
  yoy_percent: number | null;
}

export interface StockEventPoint {
  date: string;
  timestamp: number;
  category: string | null;
  title: string;
  message: string;
  subtype: number | null;
  sentiment: string | null;
}

export interface ChipHistogramBin {
  price: number;
  percent: number;
  profitable: boolean;
}

export interface ChipDistributionSnapshot {
  date: string;
  timestamp: number;
  close: number;
  benefit_ratio: number;
  avg_cost: number;
  cost_90_low: number;
  cost_90_high: number;
  cost_90_concentration: number;
  cost_70_low: number;
  cost_70_high: number;
  cost_70_concentration: number;
  support_price: number | null;
  pressure_price: number | null;
  relative_price_trend: string;
  concentration_trend: string;
  interpretation: string;
}

export interface ChipDistribution {
  source: string;
  params: Record<string, number>;
  snapshots: ChipDistributionSnapshot[];
  latest: ChipDistributionSnapshot | null;
  histogram: ChipHistogramBin[];
  histograms: Record<string, ChipHistogramBin[]>;
}

export interface StockDiagnosis {
  code: string;
  name: string;
  generated_at: string;
  source: string;
  timings_ms: Record<string, number>;
  moving_averages: MovingAveragePoint[];
  macd: MacdPoint[];
  shareholders: ShareholderPoint[];
  net_profit: NetProfitPoint[];
  events: StockEventPoint[];
  chip_distribution: ChipDistribution | null;
  event_summary: string;
  diagnosis_report: string;
  llm_status: string;
  data_errors: Record<string, string>;
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
  | { type: 'queued'; task_id?: string }
  | { type: 'paused'; message: string; step?: number; plan_step?: string }
  | { type: 'done' };
