import { useState } from "react";
import { ChevronDown, Terminal } from "lucide-react";
import type { WorkflowRun } from "@/services/observability";
import { cn } from "@/lib/utils";
import { formatLatency, formatTime } from "./missionControl";

/** Secondary technical dump of real run fields only. */
export function SystemTracePanel({ run }: { run: WorkflowRun }) {
  const [open, setOpen] = useState(false);

  const rows: { label: string; value: string }[] = [
    { label: "Run ID", value: run.run_id },
    { label: "Workflow", value: run.workflow_name },
    { label: "Status", value: run.final_status },
    { label: "Latency", value: formatLatency(run.latency_ms) },
    { label: "Started", value: formatTime(run.started_at || run.created_at) },
    { label: "Completed", value: formatTime(run.completed_at) },
  ];

  if (run.session_id) rows.push({ label: "Session", value: run.session_id });
  if (run.product_matches_count != null) {
    rows.push({ label: "Product matches", value: String(run.product_matches_count) });
  }
  if (run.supplier_matches_count != null) {
    rows.push({ label: "Supplier matches", value: String(run.supplier_matches_count) });
  }
  if (run.input_summary) rows.push({ label: "Input summary", value: run.input_summary });
  if (run.error_message) rows.push({ label: "Error", value: run.error_message });

  return (
    <section className="overflow-hidden border border-border/70 bg-background/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mm-micro-control flex w-full items-center justify-between px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2.5">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
          <div>
            <div className="type-section-label text-muted-foreground">System trace</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground/80">
              Run metadata available from observability store
            </div>
          </div>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform duration-[var(--duration-fast)]",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div className="grid gap-2 border-t border-border p-4 animate-fade-in sm:grid-cols-2">
          {rows.map((r) => (
            <div
              key={r.label}
              className="border border-border/60 bg-background/30 px-3 py-2 sm:col-span-1"
            >
              <div className="type-section-label text-[9px]">{r.label}</div>
              <div className="mt-1 break-all font-mono text-[11px] text-foreground/85">
                {r.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
