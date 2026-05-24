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
      <div className="max-w-4xl mx-auto p-6">
        <h2 className="text-xl font-bold mb-4 text-[#e2e8f0]">编辑分析结果</h2>
        {storeLoading && !currentTheme && (
          <div className="rounded-lg border p-8 text-center bg-[#151c2c] border-[#1e293b]">
            <p className="text-[#94a3b8]">加载中...</p>
          </div>
        )}
        {currentTheme && currentTheme.id === id && (
          <ResultEditor key={currentTheme.id} theme={currentTheme} onSave={handleEditSave} saving={editSaving} />
        )}
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5">
      <div className="grid grid-cols-[280px_minmax(0,1fr)] gap-4">
        <aside className="rounded-lg border bg-[#151c2c] border-[#1e293b] overflow-hidden h-fit">
          <div className="px-4 py-3 border-b border-[#1e293b]">
            <h3 className="text-sm font-medium text-[#e2e8f0]">历史任务</h3>
          </div>
          <div className="max-h-[720px] overflow-y-auto">
            {loadingTasks && <p className="px-4 py-3 text-xs text-[#64748b]">加载中...</p>}
            {!loadingTasks && tasks.length === 0 && <p className="px-4 py-3 text-xs text-[#64748b]">暂无历史任务</p>}
            {tasks.map((task) => (
              <div key={task.id} className="px-4 py-3 border-b border-[#1e293b] last:border-b-0">
                <button className="text-left w-full" onClick={() => void loadTask(task.id)}>
                  <div className="text-sm text-[#e2e8f0] truncate">{task.query}</div>
                  <div className="text-xs text-[#94a3b8] mt-1">{task.status} · {task.current_step}/{task.max_steps}</div>
                </button>
                <div className="mt-2 flex gap-2">
                  <button
                    disabled={isRunning || !['paused', 'failed'].includes(task.status)}
                    className="text-xs px-2 py-1 rounded bg-[#6366f1] text-white disabled:opacity-40"
                    onClick={() => void handleContinueTask(task.id)}
                  >继续</button>
                  <button
                    disabled={isRunning}
                    className="text-xs px-2 py-1 rounded border border-[#1e293b] text-[#94a3b8] disabled:opacity-40"
                    onClick={() => void handleDeleteTask(task.id)}
                  >删除</button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="space-y-5">
          <h2 className="text-xl font-bold text-[#e2e8f0]">AI供应链分析</h2>
          <AnalysisInput onSubmit={handleStartAnalysis} isRunning={isRunning} />
          {loadingTask && <p className="text-sm text-[#94a3b8]">任务加载中...</p>}
          <ReasoningStream
            events={taskEvents}
            currentStep={isRunning ? currentStep : (currentTask?.current_step ?? currentStep)}
            maxSteps={isRunning ? maxSteps : (currentTask?.max_steps ?? maxSteps)}
            error={displayError}
          />
          {displayResult && (
            <div className="space-y-3">
              {!confirmedTheme ? (
                <div className="flex gap-3">
                  <button
                    onClick={handleConfirmResult}
                    className="px-5 py-2.5 rounded-md text-sm font-medium bg-[#6366f1] text-white hover:bg-[#5558e6] transition-colors"
                  >确认分析结果</button>
                </div>
              ) : (
                <ResultEditor key={confirmedTheme.id} theme={confirmedTheme} onSave={handleSaveTheme} saving={themeSaving} />
              )}
            </div>
          )}
          {savedThemeId && (
            <div className="flex gap-3">
              <button onClick={() => navigate(`/dashboard/${savedThemeId}`)} className="px-5 py-2.5 rounded-md text-sm font-medium border text-[#e2e8f0] border-[#1e293b] hover:border-[#6366f1] transition-colors">查看结果</button>
              <button onClick={() => navigate(`/analysis/${savedThemeId}/edit`)} className="px-5 py-2.5 rounded-md text-sm font-medium border text-[#94a3b8] border-[#1e293b] hover:border-[#6366f1] hover:text-[#e2e8f0] transition-colors">编辑结果</button>
            </div>
          )}
          {currentTask && (
            <div className="rounded-lg border p-4 bg-[#151c2c] border-[#1e293b] text-sm text-[#94a3b8]">
              <div>任务状态：{currentTask.status}</div>
              <div className="mt-1">查询：{currentTask.query}</div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
