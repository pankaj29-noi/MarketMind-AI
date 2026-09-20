import React from 'react';
import { Loader2, Zap, BarChart3, Flame, Brain, RefreshCw } from 'lucide-react';
import type {
  DatasetComplexity,
  QuestionTier,
  QuestionTierGroup,
  SuggestedQuestion,
} from '@/services/suggestedQuestions';
import { cn } from '@/lib/utils';

const TIER_META: Record<
  QuestionTier,
  { label: string; icon: React.ElementType; accent: string }
> = {
  quick: { label: 'Quick', icon: Zap, accent: 'text-primary/80' },
  analytics: { label: 'Analytics', icon: BarChart3, accent: 'text-primary/80' },
  advanced: { label: 'Advanced', icon: Flame, accent: 'text-amber-500' },
  expert: { label: 'Expert', icon: Brain, accent: 'text-violet-500' },
};

const TIER_ORDER: QuestionTier[] = ['quick', 'analytics', 'advanced', 'expert'];

interface SuggestedQuestionsPanelProps {
  title?: string;
  subtitle?: string;
  questions: SuggestedQuestion[];
  tiers?: QuestionTierGroup[];
  complexity?: DatasetComplexity | null;
  profileSummary?: { row_count?: number; column_count?: number } | null;
  loading?: boolean;
  error?: string | null;
  message?: string | null;
  disabled?: boolean;
  onAsk: (question: string) => void;
  onRefresh?: () => void;
}

function groupByTier(
  questions: SuggestedQuestion[],
  tiers?: QuestionTierGroup[]
): QuestionTierGroup[] {
  if (tiers && tiers.length > 0) return tiers;
  const map = new Map<QuestionTier, SuggestedQuestion[]>();
  questions.forEach((q) => {
    const tier = (q.tier ?? 'analytics') as QuestionTier;
    const list = map.get(tier) ?? [];
    list.push(q);
    map.set(tier, list);
  });
  return TIER_ORDER.filter((t) => (map.get(t)?.length ?? 0) > 0).map((tier) => ({
    tier,
    questions: map.get(tier) as SuggestedQuestion[],
  }));
}

export const SuggestedQuestionsPanel: React.FC<SuggestedQuestionsPanelProps> = ({
  title = 'Questions you can ask',
  subtitle = 'Discovered from this CSV — every suggestion is validated against your data',
  questions,
  tiers,
  complexity,
  profileSummary,
  loading,
  error,
  message,
  disabled,
  onAsk,
  onRefresh,
}) => {
  const groups = groupByTier(questions, tiers);

  const shapeLine = (() => {
    if (!profileSummary?.row_count) return null;
    const parts = [
      `${profileSummary.row_count.toLocaleString()} rows`,
      `${profileSummary.column_count ?? 0} columns`,
    ];
    if (complexity) {
      if (complexity.dimensions) parts.push(`${complexity.dimensions} dimensions`);
      if (complexity.measures) parts.push(`${complexity.measures} measures`);
      if (complexity.time_dimensions) parts.push(`${complexity.time_dimensions} time field`);
    }
    return parts.join(' · ');
  })();

  return (
    <div className="mm-empty-ready relative mx-auto max-w-3xl overflow-hidden px-6 py-8">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/35 to-transparent"
        aria-hidden
      />
      <div className="text-center">
        <div className="type-section-label text-primary">{title}</div>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{subtitle}</p>
        {!loading && shapeLine && (
          <p className="mt-1 type-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
            {shapeLine}
          </p>
        )}
      </div>

      {loading && (
        <div className="mt-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Analyzing your dataset…
        </div>
      )}

      {!loading && error && (
        <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && message && questions.length === 0 && (
        <div className="mt-4 text-center text-sm text-muted-foreground">{message}</div>
      )}

      {!loading &&
        groups.map((group) => {
          const meta = TIER_META[group.tier] ?? TIER_META.analytics;
          const Icon = meta.icon;
          return (
            <section key={group.tier} className="mt-6">
              <div className="flex items-center gap-1.5">
                <Icon className={cn('h-3.5 w-3.5', meta.accent)} aria-hidden />
                <span className="type-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  {meta.label}
                </span>
              </div>
              <div className="mt-2 grid w-full gap-2 sm:grid-cols-2">
                {group.questions.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => onAsk(q.text)}
                    disabled={disabled}
                    title={q.why}
                    className={cn(
                      'mm-micro-control group flex items-start gap-2 border border-border bg-background/30 px-3.5 py-3 text-left text-xs leading-relaxed text-foreground/90',
                      'hover:bg-primary/5 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40',
                      group.tier === 'advanced' && 'border-amber-500/25',
                      group.tier === 'expert' && 'border-violet-500/25'
                    )}
                  >
                    <Icon
                      className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', meta.accent)}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">{q.text}</span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}

      {!loading && onRefresh && (
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={onRefresh}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary/90 hover:text-primary disabled:opacity-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Generate more
          </button>
        </div>
      )}
    </div>
  );
};
