import { useState } from 'react'
import type { SSEEvent } from '../../types/stock'

/**
 * 需要在时间线中展示的事件类型
 * progress / result / done 事件不参与渲染
 */
export type DisplayEvent = Extract<
  SSEEvent,
  { type: 'thinking' | 'tool_call' | 'tool_result' | 'error' }
>

/**
 * 可折叠的工具结果区块子组件
 * 默认收起，点击展开显示完整输出内容
 */
function CollapsibleResult({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)

  /**
   * 截断长文本用于预览
   * 超过120字符时截断并添加省略号
   */
  const preview = content.length > 120
    ? content.slice(0, 120) + '...'
    : content

  return (
    <div
      className="mt-1 p-2 rounded text-xs leading-relaxed cursor-pointer
                 bg-[#0a0e17] text-[#94a3b8] border border-[#1e293b]"
      onClick={() => setExpanded(!expanded)}
    >
      {/* 折叠/展开提示 */}
      <span className="text-[#475569] text-[10px] select-none">
        {expanded ? '▼ 收起' : '▶ 展开详情'}
      </span>
      {/* 内容区域：展开时显示全部，收起时显示预览 */}
      <pre className="whitespace-pre-wrap break-words mt-1 font-mono">
        {expanded ? content : preview}
      </pre>
    </div>
  )
}

/**
 * 单个时间线事件条目的渲染组件
 * 根据事件类型显示不同的图标、颜色和内容格式：
 * - thinking: 紫色文字 + 💭图标
 * - tool_call: 蓝色工具名标签 + 🔧图标
 * - tool_result: 灰色可折叠区块 + 📋图标
 * - error: 红色高亮 + ❌图标
 */
export default function EventItem({ event }: { event: DisplayEvent }) {
  switch (event.type) {
    /* 思考步骤 - 紫色文字 */
    case 'thinking':
      return (
        <div className="flex gap-3 items-start">
          <span className="text-base mt-0.5 shrink-0">💭</span>
          <p className="text-sm leading-relaxed text-[#a78bfa] whitespace-pre-wrap">
            {event.content}
          </p>
        </div>
      )

    /* 工具调用 - 蓝色标签 */
    case 'tool_call':
      return (
        <div className="flex gap-3 items-start">
          <span className="text-base mt-0.5 shrink-0">🔧</span>
          <div>
            {/* 工具名称标签 */}
            <span className="inline-block px-2 py-0.5 rounded text-xs font-mono
                             bg-[#1e3a5f] text-[#60a5fa]">
              {event.tool}
            </span>
            {/* 输入参数展示 */}
            <pre className="mt-1 text-xs text-[#94a3b8] whitespace-pre-wrap break-words font-mono">
              {event.input}
            </pre>
          </div>
        </div>
      )

    /* 工具结果 - 灰色可折叠区块 */
    case 'tool_result':
      return (
        <div className="flex gap-3 items-start">
          <span className="text-base mt-0.5 shrink-0">📋</span>
          <div className="flex-1 min-w-0">
            {/* 工具名称 */}
            <span className="text-xs text-[#64748b]">{event.tool} 返回:</span>
            {/* 可折叠结果（序列化为字符串） */}
            <CollapsibleResult content={event.output} />
          </div>
        </div>
      )

    /* 错误消息 - 红色高亮 */
    case 'error':
      return (
        <div className="flex gap-3 items-start">
          <span className="text-base mt-0.5 shrink-0">❌</span>
          <p className="text-sm text-[#ef4444]">{event.message}</p>
        </div>
      )
  }
}
