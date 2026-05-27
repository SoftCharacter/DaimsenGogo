import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useThemeStore } from '../stores/themeStore'
import { useStockStore } from '../stores/stockStore'
import { useStockPolling } from '../hooks/useStockPolling'
import Sidebar from '../components/dashboard/Sidebar'
import CategoryTabs from '../components/dashboard/CategoryTabs'
import StockGrid from '../components/dashboard/StockGrid'
import OverviewGrid from '../components/dashboard/OverviewGrid'
import StockDiagnosisPanel from '../components/dashboard/StockDiagnosisPanel'
import { fetchEnhancedStockDiagnosis, fetchStockDiagnosis } from '../api/stockApi'
import type { StockDiagnosis } from '../types/stock'
import type { StockItem } from '../types/theme'

/**
 * 大屏展示页面
 * 左侧为主题侧栏，右侧为当前主题的供应链分析展示
 * 支持分类切换、实时行情轮询、响应式布局
 */
export default function DashboardPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  /* ---------- Store ---------- */
  const currentTheme = useThemeStore((s) => s.currentTheme)
  const themeLoading = useThemeStore((s) => s.loading)
  const fetchTheme = useThemeStore((s) => s.fetchTheme)
  const quotes = useStockStore((s) => s.quotes)

  /* ---------- 分类切换状态 ---------- */
  const [activeCategoryId, setActiveCategoryId] = useState<string | null>(null)
  const [diagnosisStock, setDiagnosisStock] = useState<StockItem | null>(null)
  const [diagnosis, setDiagnosis] = useState<StockDiagnosis | null>(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisEnhancing, setDiagnosisEnhancing] = useState(false)
  const [diagnosisError, setDiagnosisError] = useState('')
  const diagnosisRequestId = useRef(0)
  const enhanceRequestId = useRef(0)

  /** 路由ID变化时加载对应主题 */
  useEffect(() => {
    if (id) {
      fetchTheme(id)
    }
  }, [id, fetchTheme])

  const displayTheme = currentTheme?.id === id ? currentTheme : null

  /** 从主题中提取所有股票代码，用于行情轮询 */
  const allCodes = useMemo(() => {
    if (!displayTheme) return []
    return displayTheme.categories.flatMap((c) =>
      c.stocks.map((s) => s.code),
    )
  }, [displayTheme])

  /** 启动实时行情轮询 */
  useStockPolling(allCodes, displayTheme?.source_task_id || undefined)

  /** 侧栏主题切换 */
  const handleThemeSelect = useCallback((themeId: string) => {
    setActiveCategoryId(null)
    navigate(`/dashboard/${themeId}`)
  }, [navigate])

  const handleStockClick = useCallback((stock: StockItem) => {
    const requestId = diagnosisRequestId.current + 1
    diagnosisRequestId.current = requestId
    enhanceRequestId.current += 1
    setDiagnosisStock(stock)
    setDiagnosis(null)
    setDiagnosisError('')
    setDiagnosisLoading(true)
    setDiagnosisEnhancing(false)

    fetchStockDiagnosis(stock.code, stock.name)
      .then((result) => {
        if (diagnosisRequestId.current !== requestId) return
        setDiagnosis(result)
      })
      .catch((err) => {
        if (diagnosisRequestId.current !== requestId) return
        const message = err?.response?.data?.detail || err?.message || '个股诊断生成失败'
        setDiagnosisError(message)
      })
      .finally(() => {
        if (diagnosisRequestId.current !== requestId) return
        setDiagnosisLoading(false)
      })
  }, [])

  const handleCloseDiagnosis = useCallback(() => {
    diagnosisRequestId.current += 1
    enhanceRequestId.current += 1
    setDiagnosisStock(null)
    setDiagnosis(null)
    setDiagnosisError('')
    setDiagnosisLoading(false)
    setDiagnosisEnhancing(false)
  }, [])

  const handleEnhanceDiagnosis = useCallback((stock: StockItem) => {
    const requestId = enhanceRequestId.current + 1
    enhanceRequestId.current = requestId
    setDiagnosisEnhancing(true)

    fetchEnhancedStockDiagnosis(stock.code, stock.name)
      .then((result) => {
        if (enhanceRequestId.current !== requestId) return
        setDiagnosis(result)
      })
      .catch(() => {
        if (enhanceRequestId.current !== requestId) return
        setDiagnosis((current) => current
          ? { ...current, llm_status: 'error' }
          : current)
      })
      .finally(() => {
        if (enhanceRequestId.current !== requestId) return
        setDiagnosisEnhancing(false)
      })
  }, [])

  /** 当前选中的分类对象 */
  const activeCategory = useMemo(() => {
    if (!displayTheme || !activeCategoryId) return null
    return displayTheme.categories.find((c) => c.id === activeCategoryId) ?? null
  }, [displayTheme, activeCategoryId])

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* 左侧：主题侧栏 */}
      <Sidebar currentThemeId={id} onSelect={handleThemeSelect} />

      {/* 右侧：主内容区 */}
      <div className="flex-1 overflow-y-auto p-6">
        {!id ? (
          /* 未选择主题时的空状态 */
          <div className="flex items-center justify-center h-full">
            <p className="text-[#64748b] text-sm">
              请从左侧选择一个主题，或创建新的分析
            </p>
          </div>
        ) : !displayTheme ? (
          /* 主题切换加载中，避免展示上一个主题的内容 */
          <div className="flex items-center justify-center h-full">
            <p className="text-[#64748b] text-sm">
              {themeLoading ? '正在加载主题...' : '主题不存在或加载失败'}
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {/* 主题标题和描述 */}
            <div>
              <h2 className="text-xl font-bold text-[#e2e8f0]">
                {displayTheme.name}
              </h2>
              <p className="text-sm text-[#94a3b8] mt-1">
                {displayTheme.description}
              </p>
            </div>

            {/* 分类标签切换 */}
            <CategoryTabs
              categories={displayTheme.categories}
              activeId={activeCategoryId}
              onSelect={setActiveCategoryId}
            />

            {/* 内容区：按分类或全部展示 */}
            {activeCategoryId && activeCategory ? (
              /* 选中某个分类时：单个分类的股票网格 */
              <StockGrid
                stocks={activeCategory.stocks}
                quotes={quotes}
                showPercentageBar
                onStockClick={handleStockClick}
              />
            ) : (
              /* "全部"模式：K线总览网格，合并所有分类的股票 */
              <OverviewGrid
                stocks={displayTheme.categories.flatMap((c) => c.stocks)}
                quotes={quotes}
                taskId={displayTheme.source_task_id || undefined}
                onStockClick={handleStockClick}
              />
            )}
          </div>
        )}
      </div>

      {diagnosisStock && (
        <StockDiagnosisPanel
          stock={diagnosisStock}
          diagnosis={diagnosis}
          loading={diagnosisLoading}
          enhancing={diagnosisEnhancing}
          error={diagnosisError}
          onEnhance={handleEnhanceDiagnosis}
          onClose={handleCloseDiagnosis}
        />
      )}
    </div>
  )
}
