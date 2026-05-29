import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useThemeStore } from '../stores/themeStore'
import { useStockStore } from '../stores/stockStore'
import { useStockPolling } from '../hooks/useStockPolling'
import Sidebar from '../components/dashboard/Sidebar'
import StockCard from '../components/dashboard/StockCard'
import OverviewPanel from '../components/dashboard/OverviewPanel'
import StockDiagnosisPanel from '../components/dashboard/StockDiagnosisPanel'
import { fetchEnhancedStockDiagnosis, fetchStockDiagnosis } from '../api/stockApi'
import type { StockDiagnosis } from '../types/stock'
import type { StockItem } from '../types/theme'

const ALL = '全部'

/**
 * 供应链看板页面（高保真重构）
 * 左 Sidebar(主题列表) + 右主区(主题头部 + 板块概览 + 环节筛选 chip + 个股卡片网格)。
 * 点卡片打开个股洞察弹窗。数据全部来自真实接口（主题 / 行情 / 诊断）。
 */
export default function DashboardPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  /* ---------- Store ---------- */
  const currentTheme = useThemeStore((s) => s.currentTheme)
  const themeLoading = useThemeStore((s) => s.loading)
  const fetchTheme = useThemeStore((s) => s.fetchTheme)
  const quotes = useStockStore((s) => s.quotes)

  /* ---------- 筛选 / 诊断状态 ---------- */
  const [activeSeg, setActiveSeg] = useState<string>(ALL)
  const [diagnosisStock, setDiagnosisStock] = useState<StockItem | null>(null)
  const [diagnosis, setDiagnosis] = useState<StockDiagnosis | null>(null)
  const [baseDiagnosis, setBaseDiagnosis] = useState<StockDiagnosis | null>(null)
  const [enhancedDiagnosis, setEnhancedDiagnosis] = useState<StockDiagnosis | null>(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisEnhancing, setDiagnosisEnhancing] = useState(false)
  const [diagnosisEnhanced, setDiagnosisEnhanced] = useState(false)
  const [diagnosisError, setDiagnosisError] = useState('')
  const diagnosisRequestId = useRef(0)
  const enhanceRequestId = useRef(0)

  /** 路由ID变化时加载对应主题 */
  useEffect(() => {
    if (id) fetchTheme(id)
  }, [id, fetchTheme])

  /** 主题切换时重置筛选 */
  useEffect(() => {
    setActiveSeg(ALL)
  }, [id])

  const displayTheme = currentTheme?.id === id ? currentTheme : null

  /** 全部成分股（合并所有分类） */
  const allStocks = useMemo(
    () => (displayTheme ? displayTheme.categories.flatMap((c) => c.stocks) : []),
    [displayTheme],
  )

  /** 用于行情轮询的代码列表 */
  const allCodes = useMemo(() => allStocks.map((s) => s.code), [allStocks])
  useStockPolling(allCodes, displayTheme?.source_task_id || undefined)

  /** 环节筛选项（全部 + 各分类） */
  const segments = useMemo(() => [ALL, ...(displayTheme?.categories.map((c) => c.name) ?? [])], [displayTheme])
  const segCount = useCallback(
    (seg: string) => (seg === ALL ? allStocks.length : allStocks.filter((s) => s.category_tag === seg).length),
    [allStocks],
  )

  /** 当前筛选后的列表 */
  const list = useMemo(
    () => (activeSeg === ALL ? allStocks : allStocks.filter((s) => s.category_tag === activeSeg)),
    [activeSeg, allStocks],
  )

  /* ---------- 交互 ---------- */
  const handleThemeSelect = useCallback(
    (themeId: string) => {
      navigate(`/dashboard/${themeId}`)
    },
    [navigate],
  )

  const handleStockClick = useCallback((stock: StockItem) => {
    const requestId = diagnosisRequestId.current + 1
    diagnosisRequestId.current = requestId
    enhanceRequestId.current += 1
    setDiagnosisStock(stock)
    setDiagnosis(null)
    setBaseDiagnosis(null)
    setEnhancedDiagnosis(null)
    setDiagnosisError('')
    setDiagnosisLoading(true)
    setDiagnosisEnhancing(false)
    setDiagnosisEnhanced(false)

    fetchStockDiagnosis(stock.code, stock.name)
      .then((result) => {
        if (diagnosisRequestId.current !== requestId) return
        setDiagnosis(result)
        setBaseDiagnosis(result)
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
    setBaseDiagnosis(null)
    setEnhancedDiagnosis(null)
    setDiagnosisError('')
    setDiagnosisLoading(false)
    setDiagnosisEnhancing(false)
    setDiagnosisEnhanced(false)
  }, [])

  const handleEnhanceDiagnosis = useCallback(
    (stock: StockItem) => {
      if (diagnosisEnhanced) {
        if (baseDiagnosis) setDiagnosis(baseDiagnosis)
        setDiagnosisEnhanced(false)
        setDiagnosisEnhancing(false)
        return
      }
      if (enhancedDiagnosis) {
        setDiagnosis(enhancedDiagnosis)
        setDiagnosisEnhanced(true)
        setDiagnosisEnhancing(false)
        return
      }
      const requestId = enhanceRequestId.current + 1
      enhanceRequestId.current = requestId
      setBaseDiagnosis((current) => current || diagnosis)
      setDiagnosisEnhancing(true)

      fetchEnhancedStockDiagnosis(stock.code, stock.name)
        .then((result) => {
          if (enhanceRequestId.current !== requestId) return
          setDiagnosis(result)
          setEnhancedDiagnosis(result)
          setDiagnosisEnhanced(true)
        })
        .catch(() => {
          if (enhanceRequestId.current !== requestId) return
          setDiagnosisEnhanced(false)
          setDiagnosis((current) => (current ? { ...current, llm_status: 'error' } : current))
        })
        .finally(() => {
          if (enhanceRequestId.current !== requestId) return
          setDiagnosisEnhancing(false)
        })
    },
    [baseDiagnosis, diagnosis, diagnosisEnhanced, enhancedDiagnosis],
  )

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0, width: '100%' }}>
      {/* 左侧：主题侧栏 */}
      <Sidebar currentThemeId={id} onSelect={handleThemeSelect} />

      {/* 右侧：主内容区 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px 40px' }}>
        {!id ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <p style={{ color: 'var(--text-faint)', fontSize: 13.5 }}>请从左侧选择一个主题，或创建新的分析</p>
          </div>
        ) : !displayTheme ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <p style={{ color: 'var(--text-faint)', fontSize: 13.5 }}>
              {themeLoading ? '正在加载主题...' : '主题不存在或加载失败'}
            </p>
          </div>
        ) : (
          <>
            {/* 主题头部 + 板块概览 */}
            <div
              className="fade-in"
              style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 32, marginBottom: 20, flexWrap: 'wrap' }}
            >
              <div style={{ maxWidth: 760, minWidth: 280, flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.01em' }}>{displayTheme.name}</h1>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: 'var(--accent-bright)',
                      background: 'var(--accent-soft)',
                      padding: '4px 10px',
                      borderRadius: 99,
                      border: '1px solid var(--accent-line)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {allStocks.length} 支成分股
                  </span>
                </div>
                <p style={{ fontSize: 13.5, lineHeight: 1.7, color: 'var(--text-dim)' }}>{displayTheme.description}</p>
              </div>
              <OverviewPanel stocks={allStocks} quotes={quotes} />
            </div>

            {/* 环节筛选 chip */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 22 }}>
              {segments.map((seg) => {
                const on = activeSeg === seg
                const c = segCount(seg)
                return (
                  <button
                    key={seg}
                    onClick={() => setActiveSeg(seg)}
                    style={{
                      cursor: 'pointer',
                      fontFamily: 'var(--font-cjk)',
                      fontSize: 12.5,
                      fontWeight: 600,
                      padding: '7px 13px',
                      borderRadius: 'var(--r-pill)',
                      transition: 'all 0.2s var(--ease)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 7,
                      border: `1px solid ${on ? 'var(--accent-line)' : 'var(--border)'}`,
                      color: on ? '#fff' : 'var(--text-dim)',
                      background: on ? 'var(--accent)' : 'var(--surface)',
                    }}
                  >
                    {seg}
                    <span
                      className="mono"
                      style={{
                        fontSize: 10.5,
                        opacity: on ? 0.85 : 0.5,
                        background: on ? 'rgba(255,255,255,0.18)' : 'var(--surface-3)',
                        padding: '1px 6px',
                        borderRadius: 99,
                      }}
                    >
                      {c}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* 卡片网格 */}
            {list.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-faint)', fontSize: 13.5 }}>
                暂无股票数据
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(var(--card-min, 330px), 1fr))',
                  gap: 16,
                }}
              >
                {list.map((s, i) => (
                  <StockCard
                    key={s.code}
                    stock={s}
                    quote={quotes[s.code]}
                    taskId={displayTheme.source_task_id || undefined}
                    delay={i * 35}
                    onClick={handleStockClick}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {diagnosisStock && (
        <StockDiagnosisPanel
          stock={diagnosisStock}
          diagnosis={diagnosis}
          loading={diagnosisLoading}
          enhancing={diagnosisEnhancing}
          enhanced={diagnosisEnhanced}
          error={diagnosisError}
          onEnhance={handleEnhanceDiagnosis}
          onClose={handleCloseDiagnosis}
        />
      )}
    </div>
  )
}
