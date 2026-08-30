/**
 * Shared pipeline stage labels — must match RightSidebar / agent-facing names.
 * Status is derived only from real trace + isAnalyzing; never invent progress.
 */

export const PIPELINE_STAGE_LABELS = [
  "Understanding dataset",
  "Planning analysis",
  "Generating",
  "Executing query",
  "Validating results",
  "Generating report",
] as const;

export const PIPELINE_FRIENDLY_LABELS: Record<string, string> = {
  schema_profiler: "Understanding dataset",
  planner: "Planning analysis",
  sql_generator: "Generating",
  sandbox_executor: "Executing query",
  validator: "Validating results",
  report_agent: "Generating report",
};

export type PipelineStepStatus = "pending" | "running" | "success" | "failed";

export interface TraceStepLike {
  step: string;
  status?: string;
  duration_ms?: number;
  details?: string;
}

export interface ResolvedPipelineStep {
  step: string;
  status: PipelineStepStatus;
  duration_ms?: number;
  details?: string;
}

export function resolvePipelineSteps(opts: {
  trace?: TraceStepLike[] | null;
  isAnalyzing?: boolean;
  activeStatus?: boolean;
}): ResolvedPipelineStep[] {
  const { trace, isAnalyzing, activeStatus } = opts;
  const hasTrace = !!(trace && trace.length > 0);

  let nextRunningIdx = -1;
  let lastExecutedIdx = -1;

  if (hasTrace) {
    const lastNodeName = trace![trace!.length - 1].step;
    lastExecutedIdx = PIPELINE_STAGE_LABELS.findIndex(
      (l) => l === (PIPELINE_FRIENDLY_LABELS[lastNodeName] || lastNodeName)
    );
    if (isAnalyzing) {
      nextRunningIdx = Math.min(PIPELINE_STAGE_LABELS.length - 1, lastExecutedIdx + 1);
    }
  } else if (isAnalyzing) {
    nextRunningIdx = 0;
  }

  return PIPELINE_STAGE_LABELS.map((label, idx) => {
    let status: PipelineStepStatus = "pending";
    let duration_ms: number | undefined;
    let details: string | undefined;

    const traceStep = trace?.find(
      (t) => (PIPELINE_FRIENDLY_LABELS[t.step] || t.step) === label
    );
    if (traceStep) {
      duration_ms = traceStep.duration_ms;
      details = traceStep.details;
    }

    if (activeStatus === true) {
      status = "success";
    } else if (nextRunningIdx !== -1) {
      if (idx < nextRunningIdx) status = "success";
      else if (idx === nextRunningIdx) status = "running";
      else status = "pending";
    } else {
      if (idx < lastExecutedIdx) {
        status = "success";
      } else if (idx === lastExecutedIdx) {
        status = activeStatus === false ? "failed" : "success";
      } else {
        status = "pending";
      }
    }

    return { step: label, status, duration_ms, details };
  });
}
