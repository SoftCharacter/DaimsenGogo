import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import AnalysisInput from '../components/analysis/AnalysisInput'
import ReasoningStream from '../components/analysis/ReasoningStream'
import ResultEditor from '../components/analysis/ResultEditor'
import { useAnalysisStore } from '../stores/analysisStore'
import { useThemeStore } from '../stores/themeStore'
import type { Theme } from '../types/theme'
import type { SSEEvent } from '../types/stock'
import { deleteAnalysisTask, getAnalysisTask, listAnalysisTasks } from '../api/analysisTaskApi'
import type { AnalysisTask, AnalysisTaskEvent, AnalysisTaskSummary } from '../types/analysisTask'

type DisplaySSEEvent = SSEEvent & { seq?: number; task_id?: string }

function toSSEEvent(event: AnalysisTaskEvent): DisplaySSEEvent | null {
  const data = event.data
  switch (event.type) {
    case 'thinking':
      return { type: 'thinking', content: String(data.content ?? ''), step: Number(data.step ?? 0), seq: event.seq }
    case 'tool_call':
      return { type: 'tool_call', tool: String(data.tool ?? ''), input: String(data.input ?? ''), step: Number(data.step ?? 0), seq: event.seq }
    case 'tool_result':
      return { type: 'tool_result', tool: String(data.tool ?? ''), output: String(data.output ?? ''), step: Number(data.step ?? 0), seq: event.seq }
    case 'progress':
      return { type: 'progress', step: Number(data.step ?? 0), max_steps: Number(data.max_steps ?? 0), seq: event.seq }
    case 'result':
      return data.theme ? { type: 'result', theme: data.theme as Theme, seq: event.seq } : null
    case 'error':
      return { type: 'error', message: String(data.message ?? ''), seq: event.seq }
    case 'done':
      return { type: 'done', seq: event.seq }
    default:
      return null
  }
}

function eventSignature(event: DisplaySSEEvent): string {
  if (event.seq !== undefined) return `seq:${event.seq}`
  if (event.type === 'thinking') return `${event.type}:${event.step}:${event.content}`
  if (event.type === 'tool_call') return `${event.type}:${event.step}:${event.tool}:${event.input}`
  if (event.type === 'tool_result') return `${event.type}:${event.step}:${event.tool}:${event.output}`
  if (event.type === 'progress') return `${event.type}:${event.step}:${event.max_steps}`
  if (event.type === 'error') return `${event.type}:${event.message}`
  return event.type
}

function mergeEvents(historyEvents: DisplaySSEEvent[], liveEvents: SSEEvent[]): DisplaySSEEvent[] {
  const merged = [...historyEvents]
  const seen = new Set(historyEvents.map(eventSignature))
  for (const event of liveEvents as DisplaySSEEvent[]) {
    const signature = eventSignature(event)
    if (seen.has(signature)) continue
    seen.add(signature)
    merged.push(event)
  }
  return merged
}

function taskToSummary(task: AnalysisTask): AnalysisTaskSummary {
  return {
    id: task.id,
    query: task.query,
    status: task.status,
    current_step: task.current_step,
    max_steps: task.max_steps,
    updated_at: task.updated_at,
    created_at: task.created_at,
    result_name: task.result?.name ?? '',
    error: task.error,
    saved_theme_id: task.saved_theme_id,
  }
}

export default function AnalysisPage() {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const isEditMode = Boolean(id)

  const {
    isRunning, taskId, events, currentStep, maxSteps,
    result, error, startAnalysis, continueAnalysis,
  } = useAnalysisStore()

  const createTheme = useThemeStore((s) => s.createTheme)
  const fetchTheme = useThemeStore((s) => s.fetchTheme)
  const updateTheme = useThemeStore((s) => s.updateTheme)
  const currentTheme = useThemeStore((s) => s.currentTheme)
  const storeLoading = useThemeStore((s) => s.loading)

  const [savedThemeId, setSavedThemeId] = useState<string | null>(null)
  const [confirmedTheme, setConfirmedTheme] = useState<Theme | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [themeSaving, setThemeSaving] = useState(false)
  const [tasks, setTasks] = useState<AnalysisTaskSummary[]>([])
  const [currentTask, setCurrentTask] = useState<AnalysisTask | null>(null)
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [loadingTask, setLoadingTask] = useState(false)
  const loadSeqRef = useRef(0)
  const refreshedTaskIdRef = useRef<string | null>(null)

  const historyEvents = useMemo(
    () => currentTask?.events.map(toSSEEvent).filter((item): item is DisplaySSEEvent => item !== null) ?? [],
    [currentTask],
  )

  const taskEvents = useMemo(() => {
    if (currentTask && isRunning && taskId === currentTask.id) return mergeEvents(historyEvents, events)
    if (!currentTask || isRunning) return events
    return historyEvents
  }, [currentTask, events, historyEvents, isRunning, taskId])

  const displayResult = result ?? currentTask?.result ?? null
  const displayError = isRunning ? error : (currentTask?.error || error)

  useEffect(() => {
    if (isEditMode && id) fetchTheme(id)
  }, [isEditMode, id, fetchTheme])

  const refreshTasks = useCallback(async () => {
    setLoadingTasks(true)
    try {
      setTasks(await listAnalysisTasks())
    } catch {
      toast.error('加载历史任务失败')
    } finally {
      setLoadingTasks(false)
    }
  }, [])

  useEffect(() => {
    void refreshTasks()
  }, [refreshTasks])

  useEffect(() => {
    if (!taskId || refreshedTaskIdRef.current === taskId) return
    refreshedTaskIdRef.current = taskId
    void refreshTasks()
  }, [refreshTasks, taskId])

  const loadTask = useCallback(async (nextTaskId: string) => {
    const seq = loadSeqRef.current + 1
    loadSeqRef.current = seq
    setLoadingTask(true)
    try {
      const task = await getAnalysisTask(nextTaskId)
      if (loadSeqRef.current !== seq) return
      setCurrentTask(task)
      setConfirmedTheme(task.result)
      setSavedThemeId(task.saved_theme_id || null)
      setTasks((prev) => prev.map((item) => item.id === task.id ? taskToSummary(task) : item))
    } catch {
      if (loadSeqRef.current === seq) toast.error('加载任务详情失败')
    } finally {
      if (loadSeqRef.current === seq) setLoadingTask(false)
    }
  }, [])

  const handleEditSave = useCallback(async (updated: Theme) => {
    if (!id) return
    setEditSaving(true)
    try {
      const saved = await updateTheme(id, updated)
      toast.success('主题已更新')
      navigate(`/dashboard/${saved.id}`)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setEditSaving(false)
    }
  }, [id, updateTheme, navigate])

  const handleStartAnalysis = useCallback((query: string) => {
    setSavedThemeId(null)
    setConfirmedTheme(null)
    setCurrentTask(null)
    refreshedTaskIdRef.current = null
    void (async () => {
      await startAnalysis(query)
      await refreshTasks()
    })()
  }, [startAnalysis, refreshTasks])

  const handleConfirmResult = useCallback(() => {
    if (!displayResult) return
    setConfirmedTheme(displayResult)
    toast.success('请确认并可继续编辑后保存')
  }, [displayResult])

  const handleSaveTheme = useCallback(async (updatedTheme: Theme) => {
    const sourceTheme = updatedTheme ?? confirmedTheme ?? displayResult
    if (!sourceTheme) return
    setThemeSaving(true)
    try {
      const created = await createTheme({
        ...sourceTheme,
        source_task_id: currentTask?.id || taskId || sourceTheme.source_task_id || '',
      })
      setSavedThemeId(created.id)
      setConfirmedTheme(created)
      toast.success('主题已保存')
    } catch {
      toast.error('保存主题失败，请重试')
    } finally {
      setThemeSaving(false)
    }
  }, [confirmedTheme, currentTask?.id, displayResult, createTheme, taskId])

  const handleDeleteTask = useCallback(async (nextTaskId: string) => {
    try {
      await deleteAnalysisTask(nextTaskId)
      setTasks((prev) => prev.filter((task) => task.id !== nextTaskId))
      if (currentTask?.id === nextTaskId) {
        loadSeqRef.current += 1
        setCurrentTask(null)
      }
      toast.success('任务已删除')
    } catch {
      toast.error('删除任务失败')
    }
  }, [currentTask?.id])

  const handleContinueTask = useCallback(async (nextTaskId: string) => {
    setSavedThemeId(null)
    setConfirmedTheme(null)
    try {
      if (currentTask?.id !== nextTaskId) await loadTask(nextTaskId)
      await continueAnalysis(nextTaskId)
      await loadTask(nextTaskId)
      await refreshTasks()
      toast.success('任务继续执行完成')
    } catch {
      toast.error('继续任务失败')
    }
  }, [continueAnalysis, currentTask?.id, loadTask, refreshTasks])

  if (isEditMode) {
    return (
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="max-w-4xl mx-auto" style={{ padding: '32px 24px 48px' }}>
          <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--text)' }}>编辑分析结果</h2>
          {storeLoading && !currentTheme && (
            <div className="panel" style={{ padding: 32, textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <p style={{ color: 'var(--text-dim)' }}>加载中...</p>
            </div>
          )}
          {currentTheme && currentTheme.id === id && (
            <ResultEditor key={currentTheme.id} theme={currentTheme} onSave={handleEditSave} saving={editSaving} />
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '40px 0' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '0 32px' }}>
        {/* Hero */}
        <div className="fade-in" style={{ textAlign: 'center', marginBottom: 14 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.22em', color: 'var(--accent-bright)' }}>
            AI 供应链分析
          </span>
          <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em', margin: '12px 0 8px' }}>
            描述产品、技术或事件，
            <br />
            DG 为你拆解<span style={{ color: 'var(--accent-bright)' }}>全链路</span>投资图谱
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-dim)' }}>
            从上游原材料到下游整机集成，自动识别 A 股成分股并生成盘面洞察
          </p>
        </div>

        {/* 输入条 */}
        <div style={{ marginTop: 26 }}>
          <AnalysisInput onSubmit={handleStartAnalysis} isRunning={isRunning} />
        </div>

        {/* 执行流 / 结果 */}
        {(loadingTask || taskEvents.length > 0 || displayError || displayResult || savedThemeId) && (
          <div style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {loadingTask && <p style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>任务加载中...</p>}
            <ReasoningStream
              events={taskEvents}
              currentStep={isRunning ? currentStep : currentTask?.current_step ?? currentStep}
              maxSteps={isRunning ? maxSteps : currentTask?.max_steps ?? maxSteps}
              error={displayError}
            />
            {displayResult &&
              (!confirmedTheme ? (
                <div>
                  <button
                    onClick={handleConfirmResult}
                    style={{
                      cursor: 'pointer',
                      border: 'none',
                      borderRadius: 'var(--r-sm)',
                      padding: '12px 24px',
                      fontFamily: 'var(--font-cjk)',
                      fontWeight: 700,
                      fontSize: 14,
                      color: '#fff',
                      background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
                      boxShadow: '0 10px 24px -12px var(--accent)',
                    }}
                  >
                    确认分析结果
                  </button>
                </div>
              ) : (
                <ResultEditor key={confirmedTheme.id} theme={confirmedTheme} onSave={handleSaveTheme} saving={themeSaving} />
              ))}
            {savedThemeId && (
              <div style={{ display: 'flex', gap: 12 }}>
                <button
                  onClick={() => navigate(`/dashboard/${savedThemeId}`)}
                  className="card"
                  style={{ cursor: 'pointer', padding: '10px 20px', fontSize: 13.5, fontWeight: 600, color: 'var(--text)', background: 'var(--surface)' }}
                >
                  查看结果
                </button>
                <button
                  onClick={() => navigate(`/analysis/${savedThemeId}/edit`)}
                  className="card"
                  style={{ cursor: 'pointer', padding: '10px 20px', fontSize: 13.5, fontWeight: 600, color: 'var(--text-dim)', background: 'transparent' }}
                >
                  编辑结果
                </button>
              </div>
            )}
          </div>
        )}

        {/* 历史任务 */}
        <div style={{ marginTop: 46 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.16em', color: 'var(--text-faint)' }}>历史任务</span>
            <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{tasks.length} 条记录</span>
          </div>
          {loadingTasks && tasks.length === 0 && <p style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>加载中...</p>}
          {!loadingTasks && tasks.length === 0 && <p style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>暂无历史任务</p>}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
            {tasks.map((task, i) => {
              const status = statusMeta(task.status)
              const canContinue = !isRunning && ['paused', 'failed'].includes(task.status)
              return (
                <div
                  key={task.id}
                  className="card fade-in"
                  style={{ animationDelay: `${i * 60}ms`, background: 'var(--surface)', padding: '16px 18px', cursor: 'pointer' }}
                  onClick={() => void loadTask(task.id)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                    <span style={{ fontWeight: 600, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {task.result_name || task.query}
                    </span>
                    <span
                      style={{
                        flex: 'none',
                        fontSize: 10.5,
                        fontWeight: 700,
                        color: status.color,
                        background: status.bg,
                        padding: '3px 9px',
                        borderRadius: 99,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      ● {status.label}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 14, margin: '12px 0 14px', color: 'var(--text-faint)', fontSize: 11.5 }}>
                    <span className="mono">{task.current_step}/{task.max_steps} 步</span>
                    <span>·</span>
                    <span className="mono">{task.updated_at?.slice(0, 10)}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      disabled={!canContinue}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleContinueTask(task.id)
                      }}
                      style={{
                        cursor: canContinue ? 'pointer' : 'not-allowed',
                        border: 'none',
                        borderRadius: 'var(--r-sm)',
                        padding: '8px 18px',
                        fontFamily: 'var(--font-cjk)',
                        fontWeight: 600,
                        fontSize: 12.5,
                        color: '#fff',
                        background: 'var(--accent)',
                        opacity: canContinue ? 1 : 0.4,
                      }}
                    >
                      继续
                    </button>
                    <button
                      disabled={isRunning}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleDeleteTask(task.id)
                      }}
                      className="card"
                      style={{
                        cursor: isRunning ? 'not-allowed' : 'pointer',
                        borderRadius: 'var(--r-sm)',
                        padding: '8px 16px',
                        fontFamily: 'var(--font-cjk)',
                        fontWeight: 600,
                        fontSize: 12.5,
                        color: 'var(--text-dim)',
                        background: 'transparent',
                        opacity: isRunning ? 0.4 : 1,
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 任务状态 → 徽标文案与配色 */
function statusMeta(status: string): { label: string; color: string; bg: string } {
  switch (status) {
    case 'completed':
      return { label: '已完成', color: 'var(--down)', bg: 'var(--down-soft)' }
    case 'running':
      return { label: '执行中', color: 'var(--accent-bright)', bg: 'var(--accent-soft)' }
    case 'failed':
      return { label: '失败', color: 'var(--up)', bg: 'var(--up-soft)' }
    case 'paused':
      return { label: '已暂停', color: 'var(--text-dim)', bg: 'var(--surface-3)' }
    default:
      return { label: status || '未知', color: 'var(--text-dim)', bg: 'var(--surface-3)' }
  }
}
