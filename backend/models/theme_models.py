"""
主题数据模型
定义供应链分析主题的数据结构，包含分类和股票信息
"""
from pydantic import BaseModel


class StockItem(BaseModel):
    """单只股票信息"""
    code: str                # 股票代码，格式 "SZ:002049"
    name: str                # 公司中文名
    name_en: str = ""        # 公司英文名
    percentage: int = 0      # 本质占比 0-100
    description: str = ""    # 业务描述（模型生成）
    category_tag: str = ""   # 所属供应链分类名


class Category(BaseModel):
    """供应链分类"""
    id: str                          # 分类ID，如 "chip_design"
    name: str                        # 分类名称，如 "芯片设计"
    order: int = 0                   # 排序序号
    stocks: list[StockItem] = []     # 该分类下的股票列表


class Theme(BaseModel):
    """分析主题 - 包含完整的供应链分析结果"""
    id: str                          # 主题唯一标识
    name: str                        # 主题名称，如 "华为昇腾950"
    description: str = ""            # 主题描述
    source_task_id: str = ""         # 来源分析任务ID，用于隔离股票数据缓存
    created_at: str = ""             # 创建时间 ISO格式
    updated_at: str = ""             # 更新时间 ISO格式
    categories: list[Category] = []  # 供应链分类列表


class ThemeSummary(BaseModel):
    """主题摘要 - 用于列表展示"""
    id: str
    name: str
    description: str = ""
    updated_at: str = ""
