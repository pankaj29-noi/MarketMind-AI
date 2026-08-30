export interface WorkflowRun {
  run_id: string;
  session_id?: string | null;
  workflow_name: string;
  input_summary?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  latency_ms?: number | null;
  final_status: string;
  product_matches_count?: number;
  supplier_matches_count?: number;
  error_message?: string | null;
  created_at?: string | null;
}

export interface ObservabilitySummary {
  total_runs: number;
  complete_count: number;
  failure_count: number;
  running_count: number;
  success_rate: number;
  average_latency_ms: number;
  total_feedback: number;
  helpful_feedback_count: number;
  helpful_feedback_rate: number;
}

export async function fetchObservabilityRuns(limit = 50): Promise<WorkflowRun[]> {
  const res = await fetch(`http://localhost:8000/marketplace/observability/runs?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to load workflow runs');
  const data = await res.json();
  return data.runs || [];
}

export async function fetchObservabilitySummary(): Promise<ObservabilitySummary> {
  const res = await fetch('http://localhost:8000/marketplace/observability/summary');
  if (!res.ok) throw new Error('Failed to load observability summary');
  const data = await res.json();
  return data.summary;
}

export async function submitWorkflowFeedback(
  runId: string,
  rating: 'helpful' | 'not_helpful',
  comment?: string
): Promise<void> {
  const res = await fetch('http://localhost:8000/marketplace/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, rating, comment: comment || undefined }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || 'Failed to submit feedback');
  }
}
