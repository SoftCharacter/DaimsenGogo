import { create } from 'zustand'
import type { Theme } from '../types/theme'
import { deleteAnalysisTask, pauseAnalysisTask, resumeAnalysisTask, runAnalysisTask, watchAnalysisTaskEvents } from '../api/analysisTaskApi'
import { parseSSEBuffer, type AnalysisStreamEvent } from '../utils/sse'

interface AnalysisState {
  isRunning: boolean
  taskId: string | null
  events: AnalysisStreamEvent[]
  currentStep: number
  maxSteps: number
  result: Theme | null
  error: string | null
  startAnalysis: (query: string) => Promise<void>
  continueAnalysis: (taskId: string) => Promise<void>
  observeTask: (taskId: string, startSeq?: number) => Promise<void>
  pauseTask: (taskId: string) => Promise<void>
  deleteTask: (taskId: string) => Promise<void>
  reset: () => void
  disconnect: () => void
}

const INITIAL_STATE = {
  isRunning: false,
  taskId: null as string | null,
  events: [] as AnalysisStreamEvent[],
  currentStep: 0,
  maxSteps: 0,
  result: null as Theme | null,
  error: null as string | null,
}

let abortController: AbortController | null = null
let activeRunId = 0

function applyEvents(prev: AnalysisState, events: AnalysisStreamEvent[]): Partial<AnalysisState> {
  const next: Partial<AnalysisState> = {
    events: [...prev.events, ...events],
  }

  for (const event of events) {
    if ('task_id' in event && typeof event.task_id === 'string') {
      next.taskId = event.task_id
    }

    switch (event.type) {
      case 'progress':
        next.currentStep = event.step
        next.maxSteps = event.max_steps
        break
      case 'result':
        next.result = event.theme
        break
      case 'error':
        next.error = event.message
        next.isRunning = false
        break
      case 'paused':
        next.error = event.message
        next.isRunning = false
        break
      case 'done':
        next.isRunning = false
        break
    }
  }

  return next
}

async function consumeSSE(
  response: Response,
  controller: AbortController,
  onEvents: (events: AnalysisStreamEvent[]) => void,
): Promise<void> {
  const body = response.body
  if (!body) throw new Error('响应体为空，无法读取SSE流')

  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let completed = false

  try {
    while (!controller.signal.aborted) {
      const { done, value } = await reader.read()
      if (done) {
        completed = true
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const [newEvents, remaining] = parseSSEBuffer(buffer)
      buffer = remaining
      if (newEvents.length > 0) onEvents(newEvents)
    }
  } finally {
    reader.releaseLock()
  }

  if (!completed || controller.signal.aborted) return
  const [tailEvents] = parseSSEBuffer(`${buffer}\n\n`)
  if (tailEvents.length > 0) onEvents(tailEvents)
}

function nextRun(controller: AbortController): number {
  abortController?.abort()
  abortController = controller
  activeRunId += 1
  return activeRunId
}

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  ...INITIAL_STATE,

  startAnalysis: async (query: string) => {
    const controller = new AbortController()
    const runId = nextRun(controller)
    set({ ...INITIAL_STATE, isRunning: true })

    try {
      const response = await runAnalysisTask(query, controller.signal)
      await consumeSSE(response, controller, (newEvents) => {
        if (activeRunId !== runId) return
        set((prev) => applyEvents(prev, newEvents))
      })

      if (!controller.signal.aborted && activeRunId === runId && get().isRunning) {
        set({ isRunning: false })
      }
    } catch (err: unknown) {
      if (controller.signal.aborted || activeRunId !== runId) return
      const message = err instanceof Error ? err.message : '分析过程发生未知错误'
      set({ error: message, isRunning: false })
    } finally {
      if (abortController === controller) abortController = null
    }
  },

  continueAnalysis: async (taskId: string) => {
    const controller = new AbortController()
    const runId = nextRun(controller)
    set({ ...INITIAL_STATE, taskId, isRunning: true })

    try {
      const response = await resumeAnalysisTask(taskId, controller.signal)
      await consumeSSE(response, controller, (newEvents) => {
        if (activeRunId !== runId) return
        set((prev) => applyEvents(prev, newEvents))
      })

      if (!controller.signal.aborted && activeRunId === runId && get().isRunning) {
        set({ isRunning: false })
      }
    } catch (err: unknown) {
      if (controller.signal.aborted || activeRunId !== runId) return
      const message = err instanceof Error ? err.message : '分析过程发生未知错误'
      set({ error: message, isRunning: false })
    } finally {
      if (abortController === controller) abortController = null
    }
  },

  observeTask: async (taskId: string, startSeq: number = 0) => {
    const controller = new AbortController()
    const runId = nextRun(controller)
    set({ ...INITIAL_STATE, taskId, isRunning: true })

    try {
      const response = await watchAnalysisTaskEvents(taskId, startSeq, controller.signal)
      await consumeSSE(response, controller, (newEvents) => {
        if (activeRunId !== runId) return
        set((prev) => applyEvents(prev, newEvents))
      })

      if (!controller.signal.aborted && activeRunId === runId && get().isRunning) {
        set({ isRunning: false })
      }
    } catch (err: unknown) {
      if (controller.signal.aborted || activeRunId !== runId) return
      const message = err instanceof Error ? err.message : '观察分析任务失败'
      set({ error: message, isRunning: false })
    } finally {
      if (abortController === controller) abortController = null
    }
  },

  pauseTask: async (taskId: string) => {
    await pauseAnalysisTask(taskId)
  },

  deleteTask: async (taskId: string) => {
    await deleteAnalysisTask(taskId)
    if (get().taskId !== taskId) return
    abortController?.abort()
    abortController = null
    activeRunId += 1
    set(INITIAL_STATE)
  },

  reset: () => {
    abortController?.abort()
    abortController = null
    activeRunId += 1
    set(INITIAL_STATE)
  },

  disconnect: () => {
    abortController?.abort()
    abortController = null
    activeRunId += 1
    set({ isRunning: false })
  },
}))
