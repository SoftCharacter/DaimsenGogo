/**
 * 单只股票信息
 */
export interface StockItem {
  code: string;         // 股票代码 "SZ:002049"
  name: string;         // 公司中文名
  name_en: string;      // 公司英文名
  percentage: number;   // 本质占比 0-100
  description: string;  // 业务描述
  category_tag: string; // 所属分类名
}

/**
 * 业务确证阶段排除的候选股票
 */
export interface RejectedStock {
  code: string;
  name: string;
  relation_score: number;
  relation_type: string;
  reason: string;
  evidence_url: string;
}

/**
 * 供应链分类
 */
export interface Category {
  id: string;           // 分类ID
  name: string;         // 分类名称
  order: number;        // 排序序号
  stocks: StockItem[];  // 分类下的股票列表
}

/**
 * 分析主题 - 完整供应链分析结果
 */
export interface Theme {
  id: string;
  name: string;
  description: string;
  source_task_id: string;
  created_at: string;
  updated_at: string;
  categories: Category[];
  rejected_stocks: RejectedStock[];
}

/**
 * 主题摘要 - 列表展示
 */
export interface ThemeSummary {
  id: string;
  name: string;
  description: string;
  updated_at: string;
}
