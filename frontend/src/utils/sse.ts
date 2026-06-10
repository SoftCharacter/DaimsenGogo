import type { SSEEvent } from '../types/stock'

export type AnalysisStreamEvent = SSEEvent & { seq?: number; task_id?: string }

export function parseSSEBuffer(buffer: string): [AnalysisStreamEvent[], string] {
  const events: AnalysisStreamEvent[] = []
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
      events.push({ type: eventType, ...parsed } as AnalysisStreamEvent)
    } catch {
      console.warn('[sse] JSON解析失败:', dataLines.join('\n'))
    }
  }

  return [events, remaining]
}
