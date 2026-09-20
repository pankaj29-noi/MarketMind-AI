import React from 'react';
import {
  Loader2,
  BarChart3,
  Trophy,
  TrendingUp,
  Percent,
  Filter,
  GitCompare,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import type { SuggestedQuestion } from '@/services/suggestedQuestions';
import { cn } from '@/lib/utils';

const CATEGORY_ICON: Record<string, React.ElementType> = {
  overview: Sparkles,
  ranking: Trophy,
  aggregation: BarChart3,
  time_analysis: TrendingUp,
  percentage: Percent,
  conditional: Filter,
  group_comparison: GitCompare,
  relationship: GitCompare,
};

interface SuggestedQuestionsPanelProps {
  title?: string;
  subtitle?: string;
  questions: SuggestedQuestion[];
  loading?: boolean;
  error?: string | null;
  message?: string | null;
  disabled?: boolean;
  onAsk: (question: string) => void;
  onRefresh?: () => void;
}

export const SuggestedQuestionsPanel: React.FC<SuggestedQuestionsPanelProps> = ({
  title = 'Questions for your dataset',
  subtitle = 'Generated from this CSV’s schema — click to analyze',
  questions,
  loading,
  error,
  message,
  disabled,
  onAsk,
  onRefresh,
}) => {
  return (
    <div className="mm-empty-ready relative mx-auto max-w-2xl overflow-hidden px-6 py-8 text-center">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/35 to-transparent"
        aria-hidden
      />
      <div className="type-section-label text-primary">{title}</div>
      <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{subtitle}</p>

      {loading && (
        <div className="mt-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Profiling dataset and validating suggestions…
        </div>
      )}

      {!loading && error && (
        <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && message && questions.length === 0 && (
        <div className="mt-4 text-sm text-muted-foreground">{message}</div>
      )}

      {!loading && questions.length > 0 && (
        <div className="mt-6 grid w-full gap-2 sm:grid-cols-2 text-left">
          {questions.map((q) => {
            const Icon = CATEGORY_ICON[q.category] || Sparkles;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => onAsk(q.text)}
                disabled={disabled}
                className={cn(
                  'mm-micro-control group flex items-start gap-2 border border-border bg-background/30 px-3.5 py-3 text-left text-xs leading-relaxed text-foreground/90',
                  'hover:bg-primary/5 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40'
                )}
              >
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/80" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block">{q.text}</span>
                  <span className="mt-1 block type-mono text-[9px] uppercase tracking-wider text-muted-foreground/70">
                    {q.category.replace('_', ' ')} · {q.difficulty}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      {!loading && onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={disabled}
          className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-primary/90 hover:text-primary disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Generate more
        </button>
      )}
    </div>
  );
};
