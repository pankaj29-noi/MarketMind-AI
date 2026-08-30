import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, FlaskConical, ShieldCheck } from "lucide-react";
import type { AppReportPayload } from "./Report";
import { cn } from "@/lib/utils";
import { IntelligenceSignal } from "@/components/analysis/IntelligenceSignal";
import { extractPrimaryNumber, useCountReveal } from "@/hooks/useCountReveal";

function HeadlineReveal({ text, isFailure }: { text: string; isFailure: boolean }) {
  const parsed = !isFailure ? extractPrimaryNumber(text) : null;
  const animated = useCountReveal(parsed?.number ?? null, 480);
  const reduceMotion = useReducedMotion();

  if (!parsed || reduceMotion) {
    return <>{text}</>;
  }

  const decimals = parsed.raw.includes(".")
    ? (parsed.raw.split(".")[1]?.replace(/[^\d]/g, "").length ?? 0)
    : 0;
  const formatted =
    (parsed.raw.startsWith("$") ? "$" : "") +
    animated.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

  return (
    <>
      {parsed.prefix}
      <span className="tabular-nums">{formatted}</span>
      {parsed.suffix}
    </>
  );
}

export function ExecutiveSummaryCard({ payload }: { payload: AppReportPayload }) {
  const { executive_summary, report_type } = payload.report;
  const isFailure = report_type === "FAILURE";
  const isDemoAnalysis = payload.debug?.analysis_source === "deterministic_fallback";
  const analysisSource = payload.debug?.analysis_source;
  const reduceMotion = useReducedMotion();

  return (
    <motion.section
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
      className={cn(
        "mm-discovery-focus surface-elevated relative overflow-hidden border-primary/20 px-5 py-6 sm:px-7 sm:py-8",
        isFailure && "border-destructive/25"
      )}
    >
      {!reduceMotion && (
        <IntelligenceSignal mode={isFailure ? "error" : "once"} className="top-0" />
      )}

      <div
        className={cn(
          "pointer-events-none absolute inset-y-3 left-0 w-[2px]",
          isFailure ? "bg-destructive/55" : "bg-primary/70"
        )}
        aria-hidden
      />

      <div className="relative pl-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("type-section-label", isFailure ? "text-destructive" : "text-primary")}>
            {isFailure ? "Analysis status" : "Primary finding"}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 border px-2 py-0.5 type-mono text-[10px]",
              isFailure
                ? "border-warning/30 bg-warning/10 text-warning"
                : "border-success/30 bg-success/10 text-success"
            )}
          >
            <ShieldCheck className="h-3 w-3" />
            {executive_summary.confidence} confidence
          </span>
          {!isFailure && isDemoAnalysis && (
            <span className="inline-flex items-center gap-1.5 border border-primary/25 bg-primary/10 px-2 py-0.5 type-mono text-[10px] text-primary">
              <FlaskConical className="h-3 w-3" /> Demo analysis
            </span>
          )}
          {isFailure && (
            <span className="inline-flex items-center gap-1.5 border border-destructive/30 bg-destructive/10 px-2 py-0.5 type-mono text-[10px] text-destructive">
              <AlertTriangle className="h-3 w-3" /> Failure
            </span>
          )}
        </div>

        {(payload.model || payload.provider || analysisSource) && (
          <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 type-mono text-[10px] text-muted-foreground">
            {payload.provider && <span>provider · {payload.provider}</span>}
            {payload.model && <span>model · {payload.model}</span>}
            {analysisSource && <span>source · {analysisSource}</span>}
          </div>
        )}

        <h2 className="mt-5 text-2xl font-semibold leading-[1.15] tracking-tight text-foreground sm:text-[1.85rem]">
          <HeadlineReveal text={executive_summary.headline} isFailure={isFailure} />
        </h2>

        <div className="mt-4 max-w-[70ch] space-y-3 text-sm leading-[1.75] text-muted-foreground sm:text-[15px]">
          {executive_summary.summary.split(/\n+/).map((para, idx) => {
            const trimmed = para.trim();
            if (!trimmed) return null;
            return <p key={idx}>{trimmed}</p>;
          })}
        </div>
      </div>
    </motion.section>
  );
}
