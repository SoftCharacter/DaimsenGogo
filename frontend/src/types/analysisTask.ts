import type { SSEEvent } from './stock'
import type { Theme } from './theme'

export type AnalysisTaskStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface AnalysisCheckpoint {
  step: number
  max_steps: number
  messages: Array<Record<string, unknown>>
  last_llm_output: string
  last_action: Record<string, unknown> | null
  last_observation: string
  config_snapshot: Record<string, unknown>
  updated_at: string
  architecture?: string
  plan?: Record<string, unknown> | null
  current_plan_step?: number
  step_attempt?: number
  local_action_count?: number
  completed_steps?: Array<Record<string, unknown>>
  current_step_messages?: Array<Record<string, unknown>>
  verified_stock_codes?: string[]
  last_step_error?: string
}

export interface AnalysisTaskEvent {
  seq: number
  type: string
  data: Record<string, unknown>
  created_at: string
}

export interface AnalysisTask {
  id: string
  query: string
  status: AnalysisTaskStatus
  created_at: string
  updated_at: string
  started_at: string
  finished_at: string
  current_step: number
  max_steps: number
  events: AnalysisTaskEvent[]
  result: Theme | null
  error: string
  saved_theme_id: string
  checkpoint: AnalysisCheckpoint | null
}

export interface AnalysisTaskSummary {
  id: string
  query: string
  status: AnalysisTaskStatus
  current_step: number
  max_steps: number
  updated_at: string
  created_at: string
  result_name: string
  error: string
  saved_theme_id: string
}

export type AnalysisTaskSSEEvent = SSEEvent & { task_id?: string }
