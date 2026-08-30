import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Radar,
  RefreshCw,
  Sparkles,
  ThumbsUp,
} from 'lucide-react';
import { useReducedMotion } from 'framer-motion';
import {
  fetchObservabilityRuns,
  fetchObservabilitySummary,
  type ObservabilitySummary,
  type WorkflowRun,
} from '@/services/observability';
import { cn } from '@/lib/utils';
import { IntelligenceSignal } from '@/components/analysis/IntelligenceSignal';
import { ExecutionObservatory } from '@/components/monitoring/ExecutionObservatory';
import { RunHistoryList } from '@/components/monitoring/RunHistoryList';
import { SystemTracePanel } from '@/components/monitoring/SystemTracePanel';
import {
  buildObservatoryStages,
  deriveMissionPhase,
  formatLatency,
  formatPct,
  phaseDotClass,
} from '@/components/monitoring/missionControl';

export const AgentMonitoring: React.FC = () => {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

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
      setSelectedId((prev) => {
        if (prev && r.some((x) => x.run_id === prev)) return prev;
        return r[0]?.run_id ?? null;
      });
    } catch (err: any) {
      setError(err.message || 'Failed to load monitoring data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selected = useMemo(
    () => runs.find((r) => r.run_id === selectedId) ?? runs[0] ?? null,
    [runs, selectedId]
  );

  const latest = runs[0] ?? null;
  const phase = deriveMissionPhase(summary, latest);
  const stages = selected ? buildObservatoryStages(selected) : [];
  const isLiveRunning = selected?.final_status === 'running';

  return (
    <div className="flex h-full w-full flex-col bg-transparent text-foreground">
      {/* Mission control header */}
      <header className="mm-system-bar sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border/80 px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <div className="type-section-label text-primary">Agent monitoring</div>
          <h1 className="mt-0.5 flex items-center gap-2 text-sm font-semibold tracking-tight sm:text-base">
            <Radar className="h-4 w-4 text-primary" strokeWidth={1.75} />
            Autonomous execution observatory
          </h1>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="hidden items-center gap-2 type-mono text-[10px] tracking-[0.12em] text-muted-foreground sm:inline-flex">
            <span className={cn('h-1.5 w-1.5 rounded-full', phaseDotClass(phase))} />
            {phase}
          </span>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="mm-micro-control inline-flex items-center gap-1.5 border border-border px-2.5 py-1.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6">
          <div>
            <div className="type-section-label text-primary">Mission control</div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
              Observe autonomous workflow executions
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Recorded Lead Intelligence runs and aggregate health — refresh to update.
              {phase === 'RUNNING'
                ? ' At least one workflow is currently marked running.'
                : ' Historical runs remain stable; live signal appears only for running status.'}
            </p>
          </div>

          {loading && !summary && (
            <div className="surface-command relative overflow-hidden px-4 py-16 text-center">
              {!reduceMotion && <IntelligenceSignal mode="running" className="top-0" />}
              <Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />
              <p className="mt-3 text-sm text-muted-foreground">Loading mission control…</p>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <div className="font-medium">Could not load monitoring data</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{error}</div>
              </div>
            </div>
          )}

          {summary && (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {[
                {
                  label: 'Total runs',
                  value: summary.total_runs.toLocaleString(),
                  icon: Activity,
                },
                {
                  label: 'Success rate',
                  value: formatPct(summary.success_rate),
                  icon: Sparkles,
                },
                {
                  label: 'Average latency',
                  value: formatLatency(summary.average_latency_ms),
                  icon: Clock,
                },
                {
                  label: 'Helpful feedback',
                  value: formatPct(summary.helpful_feedback_rate),
                  icon: ThumbsUp,
                  sub: `${summary.helpful_feedback_count}/${summary.total_feedback} ratings`,
                },
              ].map((card) => (
                <div
                  key={card.label}
                  className="border border-border/70 bg-background/25 px-4 py-3.5"
                >
                  <div className="flex items-center gap-1.5 type-meta text-[10px]">
                    <card.icon className="h-3 w-3 text-primary" strokeWidth={1.75} />
                    {card.label}
                  </div>
                  <div className="type-metric mt-2 text-xl">{card.value}</div>
                  {card.sub && (
                    <div className="mt-0.5 type-meta text-[10px]">{card.sub}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Empty / standby */}
          {!loading && !error && runs.length === 0 && (
            <section className="mm-empty-ready relative overflow-hidden px-5 py-12 text-center">
              {!reduceMotion && <IntelligenceSignal mode="once" className="top-0" />}
              <div className="type-section-label text-primary">Mission control standby</div>
              <h3 className="mt-2 text-lg font-semibold tracking-tight">
                No workflow executions recorded yet
              </h3>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground leading-relaxed">
                Run Lead Intelligence analysis to populate this observatory with workflow status,
                latency, and match counts.
              </p>
              <div className="mt-4 type-mono text-[10px] text-muted-foreground/80">
                › INPUT → WORKFLOW → EXECUTION → OUTPUT
              </div>
            </section>
          )}

          {selected && stages.length > 0 && (
            <div className="mm-analysis-flow grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="space-y-4">
                <ExecutionObservatory
                  stages={stages}
                  isLiveRunning={isLiveRunning}
                  runLabel={`${selected.run_id.slice(0, 8)}… · ${selected.final_status}`}
                />

                {/* Completion / failure moment from real status */}
                {selected.final_status === 'complete' && (
                  <div className="relative overflow-hidden border border-success/30 bg-success/10 px-4 py-3">
                    {!reduceMotion && <IntelligenceSignal mode="complete" />}
                    <div className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                      <div>
                        <div className="type-section-label text-[10px] text-success">
                          Run complete
                        </div>
                        <p className="mt-0.5 text-sm font-medium">
                          All available execution stages for this run are resolved.
                        </p>
                        {selected.latency_ms != null && (
                          <p className="mt-1 type-mono text-[10px] text-muted-foreground">
                            Latency {formatLatency(selected.latency_ms)}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {['failed', 'no_products', 'no_suppliers', 'needs_info'].includes(
                  selected.final_status
                ) && (
                  <div className="border border-destructive/25 bg-destructive/10 px-4 py-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                      <div>
                        <div className="type-section-label text-[10px] text-destructive">
                          Failure state
                        </div>
                        <p className="mt-0.5 text-sm font-medium capitalize">
                          {selected.final_status.replace(/_/g, ' ')}
                        </p>
                        {selected.error_message && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            {selected.error_message}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                <SystemTracePanel run={selected} />
              </div>

              <RunHistoryList
                runs={runs}
                selectedId={selected.run_id}
                onSelect={(run) => setSelectedId(run.run_id)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentMonitoring;
