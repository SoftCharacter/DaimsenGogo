import { create } from 'zustand'
import type { SSEEvent } from '../types/stock'
import type { Theme } from '../types/theme'
import { runAnalysisTask, resumeAnalysisTask } from '../api/analysisTaskApi'

interface AnalysisState {
  isRunning: boolean
  taskId: string | null
  events: SSEEvent[]
  currentStep: number
  maxSteps: number
  result: Theme | null
  error: string | null
  startAnalysis: (query: string) => Promise<void>
  continueAnalysis: (taskId: string) => Promise<void>
  reset: () => void
  cancel: () => void
}

const INITIAL_STATE = {
  isRunning: false,
  taskId: null as string | null,
  events: [] as SSEEvent[],
  currentStep: 0,
  maxSteps: 0,
  result: null as Theme | null,
  error: null as string | null,
}

let abortController: AbortController | null = null
let activeRunId = 0

export function parseSSEBuffer(buffer: string): [SSEEvent[], string] {
  const events: SSEEvent[] = []
  const normalized = buffer.replace(/\r\n/g, '\n')
  const parts = normalized.split('\n\n')
  const remaining = parts.pop() ?? ''

  for (const part of parts) {
    if (!part.trim()) continue

    let eventType = ''
    const dataLines: string[] = []
    for (const line of part.split('\n')) {
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }

    if (!eventType || dataLines.length === 0) continue
    try {
      const parsed = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
      events.push({ type: eventType, ...parsed } as SSEEvent)
    } catch {
      console.warn('[analysisStore] JSON解析失败:', dataLines.join('\n'))
    }
  }

  return [events, remaining]
}

function applyEvent(prev: AnalysisState, event: SSEEvent): Partial<AnalysisState> {
  const next: Partial<AnalysisState> = {
    events: [...prev.events, event],
  }

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
    case 'done':
      next.isRunning = false
      break
  }

  return next
}

async function consumeSSE(
  response: Response,
  controller: AbortController,
  onEvent: (event: SSEEvent) => void,
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
      for (const event of newEvents) onEvent(event)
    }
  } finally {
    reader.releaseLock()
  }

  if (!completed || controller.signal.aborted) return
  const [tailEvents] = parseSSEBuffer(`${buffer}\n\n`)
  for (const event of tailEvents) onEvent(event)
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
      await consumeSSE(response, controller, (event) => {
        if (activeRunId !== runId) return
        set((prev) => applyEvent(prev, event))
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
      await consumeSSE(response, controller, (event) => {
        if (activeRunId !== runId) return
        set((prev) => applyEvent(prev, event))
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

  reset: () => {
    abortController?.abort()
    abortController = null
    activeRunId += 1
    set(INITIAL_STATE)
  },

  cancel: () => {
    abortController?.abort()
    abortController = null
    activeRunId += 1
    set({ isRunning: false })
  },
}))
