import { cn } from "@/lib/utils";
import type { WorkflowRun } from "@/services/observability";
import { cnStatus, formatLatency, formatTime } from "./missionControl";

interface RunHistoryListProps {
  runs: WorkflowRun[];
  selectedId?: string | null;
  onSelect: (run: WorkflowRun) => void;
}

export function RunHistoryList({ runs, selectedId, onSelect }: RunHistoryListProps) {
  if (runs.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="type-section-label text-primary">Execution history</div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            Recorded workflow runs ({runs.length})
          </h3>
        </div>
      </div>

      <ul className="divide-y divide-border/60 border border-border/70 bg-background/20">
        {runs.map((run) => {
          const active = run.run_id === selectedId;
          return (
            <li key={run.run_id}>
              <button
                type="button"
                onClick={() => onSelect(run)}
                className={cn(
                  "mm-micro-row flex w-full flex-col gap-1.5 px-3 py-3 text-left transition-colors sm:flex-row sm:items-center sm:justify-between",
                  active
                    ? "bg-primary/[0.07] border-l-2 border-l-primary"
                    : "border-l-2 border-l-transparent hover:bg-primary/[0.03]",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="type-mono text-[11px] text-foreground">
                      {run.run_id.slice(0, 8)}…
                    </span>
                    <span className={cnStatus(run.final_status)}>
                      {run.final_status.replace(/_/g, " ")}
                    </span>
                    {active && (
                      <span className="type-section-label text-[9px] text-primary">
                        Selected
                      </span>
                    )}
                  </div>
                  <div className="mt-1 truncate text-[11px] text-muted-foreground">
                    {run.workflow_name.replace(/_/g, " ")}
                    {run.input_summary ? ` · ${run.input_summary}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3 type-mono text-[10px] text-muted-foreground">
                  <span>{formatLatency(run.latency_ms)}</span>
                  <span>{formatTime(run.started_at || run.created_at)}</span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
