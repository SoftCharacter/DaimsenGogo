/**
 * 旧版分析API模块
 * 保留直接SSE流式分析接口兼容，当前主业务入口已迁移到 analysisTaskApi
 * 新功能优先接入 /api/analysis-tasks/*
 */

/**
 * 发起供应链分析请求（SSE流式）
 *
 * 使用原生fetch发送POST请求，返回Response对象
 * 调用方通过 response.body（ReadableStream）逐步读取SSE事件
 * 具体的SSE解析逻辑在 useSSE hook 中处理
 *
 * @param query - 用户输入的分析查询文本，如 "分析华为供应链"
 * @returns 原始Response对象，供调用方读取流式数据
 * @throws 当HTTP状态码非2xx时抛出错误
 *
 * @example
 * ```ts
 * const response = await runAnalysis('分析苹果供应链');
 * // 后续在useSSE中处理 response.body 的ReadableStream
 * ```
 */
export async function runAnalysis(
  query: string,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await fetch('/api/analysis/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal,
  })

  // 检查HTTP状态码，非2xx时提取错误信息并抛出
  if (!response.ok) {
    const errorBody = await response.text()
    throw new Error(errorBody || `分析请求失败: ${response.status}`)
  }

  return response
}
