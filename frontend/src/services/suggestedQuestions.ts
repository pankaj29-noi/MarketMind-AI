import { API_BASE } from '@/lib/api';

export interface SuggestedQuestion {
  id: string;
  text: string;
  category: string;
  difficulty: string;
  confidence: number;
  intent?: string;
}

export interface SuggestedQuestionsResponse {
  dataset_id: string;
  fingerprint?: string;
  profile_summary?: {
    row_count?: number;
    column_count?: number;
    dimensions?: string[];
    measures?: string[];
    time_dimensions?: string[];
  };
  questions: SuggestedQuestion[];
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
  const res = await fetch(`${API_BASE}/session/${params.sessionId}/suggested-questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: params.datasetId,
      count: params.count ?? 10,
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
