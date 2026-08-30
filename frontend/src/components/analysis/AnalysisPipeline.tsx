import { motion, useReducedMotion } from "framer-motion";
import { Check, Circle, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  resolvePipelineSteps,
  type TraceStepLike,
} from "@/lib/pipelineSteps";
import { IntelligenceSignal } from "./IntelligenceSignal";

interface AnalysisPipelineProps {
  trace?: TraceStepLike[] | null;
  isAnalyzing?: boolean;
  activeStatus?: boolean;
  question?: string;
  className?: string;
}

export function AnalysisPipeline({
  trace,
  isAnalyzing = true,
  activeStatus,
  question,
  className,
}: AnalysisPipelineProps) {
  const reduceMotion = useReducedMotion();
  const steps = resolvePipelineSteps({ trace, isAnalyzing, activeStatus });
  const active = steps.find((s) => s.status === "running");

  return (
    <section
      className={cn(
        "surface-command relative overflow-hidden px-4 py-5 sm:px-5 mm-phase-running-accent",
        className
      )}
      aria-live="polite"
      aria-busy={isAnalyzing}
    >
      {!reduceMotion && isAnalyzing && (
        <IntelligenceSignal mode="running" className="top-0" />
      )}

      <div className="type-section-label text-primary/80">Analysis sequence</div>
      <h3 className="mt-1.5 text-sm font-semibold tracking-tight text-foreground">
        {active ? active.step : isAnalyzing ? "Preparing analysis…" : "Sequence complete"}
      </h3>
      {question && (
        <p className="mt-1 truncate type-meta">
          <span className="text-primary/70">›</span> {question}
        </p>
      )}

      <ol className="mt-5 space-y-0">
        {steps.map((s, i) => {
          const isRunning = s.status === "running";
          const isDone = s.status === "success";
          const isFailed = s.status === "failed";
          const isPending = s.status === "pending";

          return (
            <motion.li
              key={s.step}
              initial={reduceMotion ? false : { opacity: 0, x: -6 }}
              animate={{ opacity: isPending && !isAnalyzing ? 0.35 : 1, x: 0 }}
              transition={{ duration: 0.2, delay: reduceMotion ? 0 : i * 0.04 }}
              className="relative flex gap-3 pb-4 last:pb-0"
            >
              {i < steps.length - 1 && (
                <span
                  className={cn(
                    "absolute left-[9px] top-5 h-[calc(100%-12px)] w-px overflow-hidden",
                    isDone ? "bg-success/40" : "bg-border"
                  )}
                  aria-hidden
                >
                  {isRunning && !reduceMotion && (
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
                  "relative z-[1] mt-0.5 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border transition-colors duration-[var(--duration-fast)]",
                  isDone && "border-success/50 bg-success/15 text-success",
                  isFailed && "border-destructive/50 bg-destructive/15 text-destructive",
                  isRunning && "border-primary/50 bg-primary/15 text-primary",
                  isPending && "border-border bg-secondary/40 text-muted-foreground"
                )}
              >
                {isRunning ? (
                  <Loader2 className="h-2.5 w-2.5 animate-spin" />
                ) : isDone ? (
                  <Check className="h-2.5 w-2.5" strokeWidth={2.5} />
                ) : isFailed ? (
                  <X className="h-2.5 w-2.5" strokeWidth={2.5} />
                ) : (
                  <Circle className="h-1.5 w-1.5 fill-current" />
                )}
              </span>

              <div className="min-w-0 flex-1 pt-px">
                <div
                  className={cn(
                    "flex items-center justify-between gap-2 text-xs",
                    isRunning && "font-semibold text-primary",
                    isDone && "font-medium text-foreground",
                    isFailed && "font-medium text-destructive",
                    isPending && "text-muted-foreground"
                  )}
                >
                  <span>{s.step}</span>
                  {isDone && s.duration_ms !== undefined && (
                    <span className="type-mono text-[10px] text-muted-foreground">
                      {s.duration_ms} ms
                    </span>
                  )}
                </div>
                {isRunning && (
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
