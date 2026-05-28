import { useEffect, useMemo, useRef } from 'react'
import type { SSEEvent } from '../../types/stock'
import EventItem from './EventItem'
import type { DisplayEvent } from './EventItem'

interface ReasoningStreamProps {
  events: Array<SSEEvent & { seq?: number }>
  currentStep: number
  maxSteps: number
  error: string | null
}

function isDisplayEvent(event: SSEEvent): event is DisplayEvent {
  return ['thinking', 'tool_call', 'tool_result', 'error'].includes(event.type)
}

function getEventKey(event: SSEEvent & { seq?: number }, index: number): string {
  if (event.seq !== undefined) return `seq-${event.seq}`
  if (event.type === 'thinking') return `${event.type}-${event.step}-${event.content.slice(0, 80)}-${index}`
  if (event.type === 'tool_call') return `${event.type}-${event.step}-${event.tool}-${event.input}-${index}`
  if (event.type === 'tool_result') return `${event.type}-${event.step}-${event.tool}-${event.output.slice(0, 80)}-${index}`
  if (event.type === 'error') return `${event.type}-${event.message}-${index}`
  return `${event.type}-${index}`
}

export default function ReasoningStream({
  events,
  currentStep,
  maxSteps,
  error,
}: ReasoningStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const displayEvents = useMemo(() => events.filter(isDisplayEvent), [events])
  const lastEventKey = displayEvents.length > 0
    ? getEventKey(displayEvents[displayEvents.length - 1] as SSEEvent & { seq?: number }, displayEvents.length - 1)
    : ''
  const progressPercent = maxSteps > 0
    ? Math.min(100, Math.max(0, Math.round((currentStep / maxSteps) * 100)))
    : 0
  const repeatedError = Boolean(
    error && displayEvents.some((event) => event.type === 'error' && event.message === error),
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lastEventKey, error])

  if (displayEvents.length === 0 && !error) return null

  return (
    <div className="rounded-lg border p-5 bg-[#151c2c] border-[#1e293b]">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-[#e2e8f0]">推理过程</h3>
        {maxSteps > 0 && (
          <span className="text-xs text-[#94a3b8]">
            步骤 {currentStep} / {maxSteps}
          </span>
        )}
      </div>

      {maxSteps > 0 && (
        <div className="h-1 rounded-full mb-4 bg-[#1e293b] overflow-hidden">
          <div
            className="h-full rounded-full bg-[#6366f1] transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
        {displayEvents.map((event, index) => (
          <div
            key={getEventKey(event as SSEEvent & { seq?: number }, index)}
            className="border-l-2 pl-4 py-1 border-[#1e293b]"
          >
            <EventItem event={event} />
          </div>
        ))}

        {error && !repeatedError && (
          <div className="border-l-2 pl-4 py-1 border-[#ef4444]">
            <div className="flex gap-3 items-start">
              <span className="text-base mt-0.5 shrink-0">错误</span>
              <p className="text-sm text-[#ef4444]">{error}</p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
