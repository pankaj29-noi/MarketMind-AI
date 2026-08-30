import { cn } from "@/lib/utils";
import type { ObservabilitySummary, WorkflowRun } from "@/services/observability";

export function formatLatency(ms?: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(0)}%`;
}

export type MissionPhase = "IDLE" | "RUNNING" | "COMPLETED" | "FAILED" | "STANDBY";

export function deriveMissionPhase(
  summary: ObservabilitySummary | null,
  latest?: WorkflowRun | null
): MissionPhase {
  if (summary && summary.running_count > 0) return "RUNNING";
  if (latest?.final_status === "running") return "RUNNING";
  if (!summary || summary.total_runs === 0) return "STANDBY";
  if (
    latest &&
    ["failed", "no_products", "no_suppliers"].includes(latest.final_status)
  ) {
    return "FAILED";
  }
  if (latest?.final_status === "complete") return "COMPLETED";
  if (latest?.final_status === "needs_info") return "FAILED";
  return "IDLE";
}

export type ObservatoryStageStatus = "waiting" | "running" | "completed" | "failed" | "skipped";

export interface ObservatoryStage {
  id: string;
  label: string;
  detail?: string;
  status: ObservatoryStageStatus;
}

/**
 * Build an observatory path from fields that actually exist on WorkflowRun.
 * Does not invent LangGraph agent nodes.
 */
export function buildObservatoryStages(run: WorkflowRun): ObservatoryStage[] {
  const status = run.final_status;
  const isRunning = status === "running";
  const isComplete = status === "complete";
  const isFailed = ["failed", "no_products", "no_suppliers", "needs_info"].includes(status);

  const stages: ObservatoryStage[] = [];

  stages.push({
    id: "input",
    label: "Input received",
    detail: run.input_summary || undefined,
    status: isRunning || isComplete || isFailed ? "completed" : "waiting",
  });

  stages.push({
    id: "workflow",
    label: "Workflow engaged",
    detail: run.workflow_name?.replace(/_/g, " "),
    status: isRunning || isComplete || isFailed ? "completed" : "waiting",
  });

  stages.push({
    id: "execution",
    label: "Execution",
    detail: run.latency_ms != null ? formatLatency(run.latency_ms) : undefined,
    status: isRunning
      ? "running"
      : isComplete
        ? "completed"
        : isFailed
          ? "failed"
          : "waiting",
  });

  const hasProductField = run.product_matches_count != null;
  const hasSupplierField = run.supplier_matches_count != null;

  if (hasProductField) {
    stages.push({
      id: "products",
      label: "Product matches",
      detail: `${run.product_matches_count} matched`,
      status: isRunning
        ? "waiting"
        : isComplete
          ? "completed"
          : isFailed && (run.product_matches_count ?? 0) === 0 && status === "no_products"
            ? "failed"
            : isFailed
              ? (run.product_matches_count ?? 0) > 0
                ? "completed"
                : "skipped"
              : "waiting",
    });
  }

  if (hasSupplierField) {
    stages.push({
      id: "suppliers",
      label: "Supplier output",
      detail: `${run.supplier_matches_count} ranked`,
      status: isRunning
        ? "waiting"
        : isComplete
          ? "completed"
          : isFailed && status === "no_suppliers"
            ? "failed"
            : isFailed
              ? (run.supplier_matches_count ?? 0) > 0
                ? "completed"
                : "skipped"
              : "waiting",
    });
  }

  if (run.error_message) {
    stages.push({
      id: "error",
      label: "Failure recorded",
      detail: run.error_message,
      status: "failed",
    });
  } else if (isComplete) {
    stages.push({
      id: "output",
      label: "Run complete",
      detail: "Final status resolved",
      status: "completed",
    });
  }

  return stages;
}

export function statusTone(status: string): string {
  switch (status) {
    case "complete":
      return "border-success/30 bg-success/10 text-success";
    case "running":
      return "border-primary/30 bg-primary/10 text-primary";
    case "needs_info":
      return "border-warning/30 bg-warning/10 text-warning";
    case "no_products":
    case "no_suppliers":
      return "border-warning/30 bg-warning/10 text-warning";
    case "failed":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    default:
      return "border-border bg-secondary/40 text-muted-foreground";
  }
}

export function phaseDotClass(phase: MissionPhase): string {
  switch (phase) {
    case "RUNNING":
      return "bg-warning mm-signal-pulse";
    case "COMPLETED":
      return "bg-success";
    case "FAILED":
      return "bg-destructive/80";
    default:
      return "bg-primary/70";
  }
}

export function cnStatus(status: string) {
  return cn(
    "inline-flex border px-2 py-0.5 type-mono text-[10px] uppercase tracking-wider capitalize",
    statusTone(status)
  );
}
