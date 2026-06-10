/**
 * SSE流式连接管理Hook
 * 负责发起POST请求的SSE流式分析，并实时解析服务端推送的事件。
 * 由于是POST请求，无法使用浏览器原生EventSource，
 * 因此通过 fetch + ReadableStream + TextDecoder 手动解析SSE协议。
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import type { SSEEvent } from '../types/stock'
import type { Theme } from '../types/theme'
import { runAnalysis } from '../api/analysisApi'
import { parseSSEBuffer } from '../utils/sse'

/** SSE Hook 内部状态接口，追踪分析流程的完整生命周期状态 */
interface SSEState {
  isRunning: boolean       // 是否正在进行分析
  events: SSEEvent[]       // 已接收的所有SSE事件列表
  currentStep: number      // 当前执行到的步骤编号
  maxSteps: number         // 预估的最大步骤数
  result: Theme | null     // 分析完成后的主题结果
  error: string | null     // 错误信息（为null表示无错误）
}

/** SSE Hook 初始状态常量 */
const INITIAL_STATE: SSEState = {
  isRunning: false, events: [], currentStep: 0,
  maxSteps: 0, result: null, error: null,
}

/**
 * SSE流式分析Hook
 * 提供发起分析、接收实时事件、获取最终结果的完整能力。
 * 内部管理AbortController以支持组件卸载时自动中断请求。
 * @returns SSE状态对象 + startAnalysis / reset 操作方法
 * @example
 * ```tsx
 * const { isRunning, events, result, startAnalysis, reset } = useSSE()
 * startAnalysis('分析华为供应链')
 * ```
 */
export function useSSE(): SSEState & {
  startAnalysis: (query: string) => void
  reset: () => void
} {
  const [state, setState] = useState<SSEState>(INITIAL_STATE)
  /** 保存AbortController引用，用于中断正在进行的请求 */
  const abortRef = useRef<AbortController | null>(null)

  /**
   * 发起SSE流式分析，读取ReadableStream并解析SSE事件
   * @param query - 用户输入的分析查询文本
   */
  const startAnalysis = useCallback(async (query: string) => {
    /** 如果存在上一次的请求，先中断它 */
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    /** 重置状态，标记为运行中 */
    setState({ ...INITIAL_STATE, isRunning: true })

    try {
      /** 发起分析请求，传递AbortSignal以支持请求级中断 */
      const response = await runAnalysis(query, controller.signal)
      const body = response.body
      if (!body) throw new Error('响应体为空，无法读取SSE流')

      /** 使用ReadableStream逐块读取数据 */
      const reader = body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = '' // SSE文本累积缓冲区

      /** 循环读取流，直到结束或被中断 */
      while (true) {
        /** 检查是否被外部中断 */
        if (controller.signal.aborted) break

        const { done, value } = await reader.read()
        if (done) break

        /** 将二进制数据解码为文本并追加到缓冲区 */
        buffer += decoder.decode(value, { stream: true })

        /** 从缓冲区中解析所有完整的SSE事件 */
        const [newEvents, remaining] = parseSSEBuffer(buffer)
        buffer = remaining

        /** 根据每个事件的类型更新对应的状态字段 */
        for (const event of newEvents) {
          setState((prev) => {
            /** 创建新的事件列表（追加当前事件） */
            const updatedEvents = [...prev.events, event]
            /** 基于当前状态的副本进行增量更新 */
            const next: SSEState = { ...prev, events: updatedEvents }

            switch (event.type) {
              case 'progress':
                /** 更新进度信息：当前步骤和最大步骤数 */
                next.currentStep = event.step
                next.maxSteps = event.max_steps
                break
              case 'result':
                /** 分析完成，提取主题结果（theme字段即Theme对象） */
                next.result = event.theme
                break
              case 'error':
                /** 后端返回了错误事件 */
                next.error = event.message
                next.isRunning = false
                break
              case 'done':
                /** 分析流正常结束 */
                next.isRunning = false
                break
              // thinking / tool_call / tool_result 仅追加到事件列表，不需要额外状态更新
            }

            return next
          })
        }
      }
    } catch (err: unknown) {
      /** 被中断时不视为错误（用户主动取消或组件卸载） */
      if (controller.signal.aborted) return
      const message = err instanceof Error ? err.message : '分析过程发生未知错误'
      setState((prev) => ({ ...prev, error: message, isRunning: false }))
    }
  }, [])

  /** 重置所有状态到初始值，同时中断可能正在进行的SSE请求 */
  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setState(INITIAL_STATE)
  }, [])

  /** 组件卸载时自动中断请求，防止更新已销毁组件的状态 */
  useEffect(() => () => { abortRef.current?.abort() }, [])

  return { ...state, startAnalysis, reset }
}
