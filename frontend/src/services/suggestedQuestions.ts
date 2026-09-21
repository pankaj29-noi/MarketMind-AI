import { apiFetch } from '@/lib/apiFetch';

export type QuestionTier = 'quick' | 'analytics' | 'advanced' | 'expert';

export interface SuggestedQuestion {
  id: string;
  text: string;
  category: string;
  difficulty: string;
  tier?: QuestionTier;
  confidence: number;
  intent?: string;
  required_columns?: string[];
  operations?: string[];
  validation_status?: string;
  why?: string;
}

export interface QuestionTierGroup {
  tier: QuestionTier;
  questions: SuggestedQuestion[];
}

export interface DatasetComplexity {
  score: number;
  band: 'minimal' | 'basic' | 'moderate' | 'rich';
  dimensions: number;
  measures: number;
  time_dimensions: number;
  entities: number;
  advanced_possible: boolean;
  expert_possible: boolean;
}

export interface SuggestedQuestionsResponse {
  dataset_id: string;
  fingerprint?: string;
  generation_version?: string;
  profile_summary?: {
    row_count?: number;
    column_count?: number;
    dimensions?: string[];
    measures?: string[];
    time_dimensions?: string[];
    entities?: string[];
    supported_operations?: string[];
  };
  complexity?: DatasetComplexity;
  questions: SuggestedQuestion[];
  tiers?: QuestionTierGroup[];
  message?: string | null;
  cache_hit?: boolean;
  generation_ms?: number;
}

export async function fetchSuggestedQuestions(params: {
  sessionId: string;
  datasetId: string;
  count?: number;
  refresh?: boolean;
  excludeIds?: string[];
}): Promise<SuggestedQuestionsResponse> {
  const res = await apiFetch(`/session/${params.sessionId}/suggested-questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: params.datasetId,
      count: params.count ?? 14,
      difficulty: 'mixed',
      refresh: Boolean(params.refresh),
      exclude_ids: params.excludeIds ?? [],
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || 'Failed to generate suggested questions.');
  }
  return res.json();
}

export interface FollowupQuestionsResponse {
  dataset_id: string;
  questions: SuggestedQuestion[];
  generation_ms?: number;
}

export async function fetchFollowupQuestions(params: {
  sessionId: string;
  datasetId: string;
  question: string;
  resultColumns?: string[];
  resultRows?: Record<string, unknown>[];
  count?: number;
}): Promise<FollowupQuestionsResponse> {
  const res = await apiFetch(`/session/${params.sessionId}/followup-questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: params.datasetId,
      question: params.question,
      result_columns: params.resultColumns ?? [],
      result_rows: (params.resultRows ?? []).slice(0, 5),
      count: params.count ?? 3,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || 'Failed to generate follow-up questions.');
  }
  return res.json();
}
