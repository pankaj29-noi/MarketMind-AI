import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Clock,
  Loader2,
  RefreshCw,
  Sparkles,
  ThumbsUp,
} from 'lucide-react';
import {
  fetchObservabilityRuns,
  fetchObservabilitySummary,
  type ObservabilitySummary,
  type WorkflowRun,
} from '@/services/observability';
import { cn } from '@/lib/utils';

function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(0)}%`;
}

function formatLatency(ms?: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function formatTime(iso?: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'complete':
      return 'bg-success/15 text-success border-success/30';
    case 'running':
      return 'bg-primary/15 text-primary border-primary/30';
    case 'needs_info':
      return 'bg-amber-500/15 text-amber-600 border-amber-500/30';
    case 'no_products':
    case 'no_suppliers':
      return 'bg-orange-500/15 text-orange-600 border-orange-500/30';
    case 'failed':
      return 'bg-destructive/15 text-destructive border-destructive/30';
    default:
      return 'bg-muted text-muted-foreground border-border';
  }
}

export const AgentMonitoring: React.FC = () => {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, r] = await Promise.all([
        fetchObservabilitySummary(),
        fetchObservabilityRuns(40),
      ]);
      setSummary(s);
      setRuns(r);
    } catch (err: any) {
      setError(err.message || 'Failed to load monitoring data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full w-full flex-col bg-background text-foreground">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/70 px-6 py-3 backdrop-blur-xl">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            MarketMind AI
          </div>
          <h1 className="text-sm font-semibold sm:text-base flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            Agent Monitoring
          </h1>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[11px] text-muted-foreground hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl space-y-6 px-6 py-8">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Observability
            </div>
            <h2 className="mt-1 text-2xl font-bold tracking-tight">Workflow health at a glance</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Lightweight run tracking and feedback for Lead Intelligence — no external tracing stack required.
            </p>
          </div>

          {loading && !summary && (
            <div className="flex flex-col items-center justify-center py-24 space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Loading agent metrics…</p>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive shrink-0" />
              <div>
                <div className="font-medium">Could not load monitoring data</div>
                <div className="text-xs text-muted-foreground mt-0.5">{error}</div>
              </div>
            </div>
          )}

          {summary && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                {
                  label: 'Total Runs',
                  value: summary.total_runs.toLocaleString(),
                  icon: Activity,
                },
                {
                  label: 'Success Rate',
                  value: formatPct(summary.success_rate),
                  icon: Sparkles,
                },
                {
                  label: 'Average Latency',
                  value: formatLatency(summary.average_latency_ms),
                  icon: Clock,
                },
                {
                  label: 'Helpful Feedback',
                  value: formatPct(summary.helpful_feedback_rate),
                  icon: ThumbsUp,
                  sub: `${summary.helpful_feedback_count}/${summary.total_feedback} ratings`,
                },
              ].map((card) => (
                <div
                  key={card.label}
                  className="rounded-xl border border-border bg-card/40 px-4 py-4"
                >
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <card.icon className="h-3 w-3" />
                    {card.label}
                  </div>
                  <div className="mt-2 text-2xl font-bold tracking-tight">{card.value}</div>
                  {card.sub && (
                    <div className="mt-0.5 text-[11px] text-muted-foreground">{card.sub}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <section className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Recent Workflow Runs
            </h3>
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-secondary/50 text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Run ID</th>
                    <th className="px-3 py-2 font-medium">Workflow</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Latency</th>
                    <th className="px-3 py-2 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.length === 0 && !loading ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-10 text-center text-sm text-muted-foreground">
                        No workflow runs yet. Analyze a lead requirement to populate this table.
                      </td>
                    </tr>
                  ) : (
                    runs.map((run) => (
                      <tr key={run.run_id} className="border-t border-border/60 align-top">
                        <td className="px-3 py-2.5 font-mono text-[11px]">
                          <div className="truncate max-w-[140px]" title={run.run_id}>
                            {run.run_id.slice(0, 8)}…
                          </div>
                          {run.input_summary && (
                            <div className="mt-0.5 text-[10px] text-muted-foreground line-clamp-1 max-w-[180px]">
                              {run.input_summary}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-xs">
                          {run.workflow_name.replace(/_/g, ' ')}
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={cn(
                              'inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize',
                              statusClass(run.final_status)
                            )}
                          >
                            {run.final_status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-xs tabular-nums">
                          {formatLatency(run.latency_ms)}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                          {formatTime(run.started_at || run.created_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default AgentMonitoring;
