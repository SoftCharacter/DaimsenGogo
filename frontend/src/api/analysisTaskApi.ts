import client from './client'
import type { AnalysisTask, AnalysisTaskSummary } from '../types/analysisTask'

export async function listAnalysisTasks(): Promise<AnalysisTaskSummary[]> {
  const res = await client.get<AnalysisTaskSummary[]>('/analysis-tasks/')
  return res.data
}

export async function getAnalysisTask(taskId: string): Promise<AnalysisTask> {
  const res = await client.get<AnalysisTask>(`/analysis-tasks/${encodeURIComponent(taskId)}`)
  return res.data
}

export async function deleteAnalysisTask(taskId: string): Promise<void> {
  await client.delete(`/analysis-tasks/${encodeURIComponent(taskId)}`)
}

export async function runAnalysisTask(query: string, signal?: AbortSignal): Promise<Response> {
  const response = await fetch('/api/analysis-tasks/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal,
  })

  if (!response.ok) {
    const errorBody = await response.text()
    throw new Error(errorBody || `分析任务请求失败: ${response.status}`)
  }

  return response
}

export async function resumeAnalysisTask(taskId: string, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(`/api/analysis-tasks/${encodeURIComponent(taskId)}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
  })

  if (!response.ok) {
    const errorBody = await response.text()
    throw new Error(errorBody || `继续分析任务失败: ${response.status}`)
  }

  return response
}
