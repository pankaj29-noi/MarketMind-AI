import { motion, useReducedMotion } from "framer-motion";
import { Check, Circle, Loader2, X } from "lucide-react";
import { IntelligenceSignal } from "@/components/analysis/IntelligenceSignal";
import { cn } from "@/lib/utils";
import type { ObservatoryStage, ObservatoryStageStatus } from "./missionControl";

function StatusGlyph({ status }: { status: ObservatoryStageStatus }) {
  if (status === "running") {
    return <Loader2 className="h-2.5 w-2.5 animate-spin text-primary" />;
  }
  if (status === "completed") {
    return <Check className="h-2.5 w-2.5 text-success" strokeWidth={2.5} />;
  }
  if (status === "failed") {
    return <X className="h-2.5 w-2.5 text-destructive" strokeWidth={2.5} />;
  }
  return <Circle className="h-1.5 w-1.5 fill-current text-muted-foreground" />;
}

interface ExecutionObservatoryProps {
  stages: ObservatoryStage[];
  /** True only when the selected run's real status is `running` */
  isLiveRunning: boolean;
  runLabel?: string;
}

export function ExecutionObservatory({
  stages,
  isLiveRunning,
  runLabel,
}: ExecutionObservatoryProps) {
  const reduceMotion = useReducedMotion();

  return (
    <section className="surface-command relative overflow-hidden px-4 py-5 sm:px-5">
      {!reduceMotion && isLiveRunning && (
        <IntelligenceSignal mode="running" className="top-0" />
      )}
      {!reduceMotion && !isLiveRunning && stages.some((s) => s.status === "completed") && (
        <IntelligenceSignal mode="complete" className="top-0" />
      )}

      <div className="type-section-label text-primary/80">Execution observatory</div>
      <h3 className="mt-1 text-sm font-semibold tracking-tight">
        {isLiveRunning ? "Autonomous workflow in progress" : "Recorded execution path"}
      </h3>
      {runLabel && (
        <p className="mt-1 type-meta truncate">
          <span className="text-primary/70">›</span> {runLabel}
        </p>
      )}

      <ol className="mt-5 space-y-0">
        {stages.map((stage, i) => {
          const isLast = i === stages.length - 1;
          const next = stages[i + 1];
          const showLiveConnector =
            isLiveRunning &&
            stage.status === "completed" &&
            next?.status === "running";

          return (
            <motion.li
              key={stage.id}
              initial={reduceMotion ? false : { opacity: 0, x: -6 }}
              animate={{ opacity: stage.status === "skipped" ? 0.4 : 1, x: 0 }}
              transition={{
                duration: 0.2,
                delay: reduceMotion ? 0 : Math.min(i * 0.04, 0.2),
              }}
              className="relative flex gap-3 pb-4 last:pb-0"
            >
              {!isLast && (
                <span
                  className={cn(
                    "absolute left-[9px] top-5 h-[calc(100%-12px)] w-px overflow-hidden",
                    stage.status === "completed" ? "bg-success/40" :
                    stage.status === "failed" ? "bg-destructive/40" : "bg-border"
                  )}
                  aria-hidden
                >
                  {showLiveConnector && !reduceMotion && (
                    <IntelligenceSignal
                      mode="running"
                      orientation="vertical"
                      className="inset-0 h-full w-full"
                    />
                  )}
                </span>
              )}

              <span
                className={cn(
                  "relative z-[1] mt-0.5 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border",
                  stage.status === "completed" && "border-success/50 bg-success/15",
                  stage.status === "failed" && "border-destructive/50 bg-destructive/15",
                  stage.status === "running" && "border-primary/50 bg-primary/15",
                  (stage.status === "waiting" || stage.status === "skipped") &&
                    "border-border bg-secondary/40"
                )}
              >
                <StatusGlyph status={stage.status} />
              </span>

              <div className="min-w-0 flex-1 pt-px">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span
                    className={cn(
                      "text-xs",
                      stage.status === "running" && "font-semibold text-primary",
                      stage.status === "completed" && "font-medium text-foreground",
                      stage.status === "failed" && "font-medium text-destructive",
                      (stage.status === "waiting" || stage.status === "skipped") &&
                        "text-muted-foreground"
                    )}
                  >
                    {stage.label}
                  </span>
                  <span className="type-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                    {stage.status}
                  </span>
                </div>
                {stage.detail && (
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground line-clamp-3">
                    {stage.detail}
                  </p>
                )}
                {stage.status === "running" && (
                  <div className="relative mt-1.5 h-px w-full overflow-hidden bg-border/60">
                    {!reduceMotion && (
                      <span className="mm-intel-signal-beam mm-intel-signal-running absolute inset-y-0 left-0 w-1/3" />
                    )}
                  </div>
                )}
              </div>
            </motion.li>
          );
        })}
      </ol>
    </section>
  );
}
