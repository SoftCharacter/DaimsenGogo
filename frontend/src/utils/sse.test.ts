import { describe, expect, it, vi } from 'vitest'
import { parseSSEBuffer } from './sse'

describe('parseSSEBuffer', () => {
  it('解析单个完整 SSE 事件并返回空剩余 buffer', () => {
    const [events, remaining] = parseSSEBuffer('event: progress\ndata: {"step":2,"max_steps":6}\n\n')

    expect(events).toEqual([{ type: 'progress', step: 2, max_steps: 6 }])
    expect(remaining).toBe('')
  })

  it('一次解析多个完整 SSE 事件', () => {
    const input = [
      'event: queued',
      'data: {"task_id":"analysis_1"}',
      '',
      'event: thinking',
      'data: {"content":"思考中","step":1,"seq":3}',
      '',
      '',
    ].join('\n')

    const [events, remaining] = parseSSEBuffer(input)

    expect(events).toEqual([
      { type: 'queued', task_id: 'analysis_1' },
      { type: 'thinking', content: '思考中', step: 1, seq: 3 },
    ])
    expect(remaining).toBe('')
  })

  it('把 CRLF 标准化后解析事件', () => {
    const [events, remaining] = parseSSEBuffer('event: done\r\ndata: {"task_id":"analysis_2"}\r\n\r\n')

    expect(events).toEqual([{ type: 'done', task_id: 'analysis_2' }])
    expect(remaining).toBe('')
  })

  it('支持多行 data 拼接为一个 JSON payload', () => {
    const input = [
      'event: thinking',
      'data: {"content":"第一行",',
      'data: "step":1}',
      '',
      '',
    ].join('\n')

    const [events] = parseSSEBuffer(input)

    expect(events).toEqual([{ type: 'thinking', content: '第一行', step: 1 }])
  })

  it('保留未完成的半包 buffer', () => {
    const [events, remaining] = parseSSEBuffer('event: progress\ndata: {"step":1,"max_steps":6}')

    expect(events).toEqual([])
    expect(remaining).toBe('event: progress\ndata: {"step":1,"max_steps":6}')
  })

  it('跳过缺少 event 或 data 的片段', () => {
    const input = [
      'data: {"step":1}',
      '',
      'event: progress',
      '',
      'event: done',
      'data: {}',
      '',
      '',
    ].join('\n')

    const [events] = parseSSEBuffer(input)

    expect(events).toEqual([{ type: 'done' }])
  })

  it('跳过非 JSON data 并输出警告', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    const [events, remaining] = parseSSEBuffer('event: progress\ndata: not-json\n\n')

    expect(events).toEqual([])
    expect(remaining).toBe('')
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })
})
