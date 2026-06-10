import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { SSEEvent } from '../../types/stock'
import EventItem from './EventItem'
import type { DisplayEvent } from './EventItem'

interface ReasoningStreamProps {
  events: Array<SSEEvent & { seq?: number }>
  currentStep: number
  maxSteps: number
  error: string | null
}

const MAX_RENDERED_EVENTS = 200

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
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)
  const displayEvents = useMemo(() => events.filter(isDisplayEvent), [events])
  const hiddenCount = Math.max(0, displayEvents.length - MAX_RENDERED_EVENTS)
  const visibleEvents = useMemo(
    () => displayEvents.slice(hiddenCount),
    [displayEvents, hiddenCount],
  )
  const lastEventKey = displayEvents.length > 0
    ? getEventKey(displayEvents[displayEvents.length - 1] as SSEEvent & { seq?: number }, displayEvents.length - 1)
    : ''
  const progressPercent = maxSteps > 0
    ? Math.min(100, Math.max(0, Math.round((currentStep / maxSteps) * 100)))
    : 0
  const repeatedError = Boolean(
    error && displayEvents.some((event) => event.type === 'error' && event.message === error),
  )

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el || !autoScrollRef.current) return
    el.scrollTop = el.scrollHeight
  }, [lastEventKey, error])

  if (displayEvents.length === 0 && !error) return null

  return (
    <div className="panel" style={{ padding: 20, background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text)' }}>推理过程</h3>
        {maxSteps > 0 && (
          <span className="text-xs mono" style={{ color: 'var(--text-dim)' }}>
            步骤 {currentStep} / {maxSteps}
          </span>
        )}
      </div>

      {maxSteps > 0 && (
        <div className="h-1 rounded-full mb-4 overflow-hidden" style={{ background: 'var(--surface-3)' }}>
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${progressPercent}%`, background: 'var(--accent)' }}
          />
        </div>
      )}

      <div ref={scrollRef} onScroll={handleScroll} className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
        {hiddenCount > 0 && (
          <div className="pl-4 py-1 text-xs" style={{ borderLeft: '2px solid var(--border)', color: 'var(--text-dim)' }}>
            已折叠更早事件 {hiddenCount} 条
          </div>
        )}

        {visibleEvents.map((event, index) => {
          const originalIndex = hiddenCount + index
          return (
            <div
              key={getEventKey(event as SSEEvent & { seq?: number }, originalIndex)}
              className="pl-4 py-1"
              style={{ borderLeft: '2px solid var(--border)' }}
            >
              <EventItem event={event} />
            </div>
          )
        })}

        {error && !repeatedError && (
          <div className="pl-4 py-1" style={{ borderLeft: '2px solid var(--up)' }}>
            <div className="flex gap-3 items-start">
              <span className="text-base mt-0.5 shrink-0">错误</span>
              <p className="text-sm" style={{ color: 'var(--up)' }}>{error}</p>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
