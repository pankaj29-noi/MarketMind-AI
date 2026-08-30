import { Sparkles, ShieldCheck, AlertTriangle } from "lucide-react";
import type { AppReportPayload } from "./Report";

export function ExecutiveSummaryCard({ payload }: { payload: AppReportPayload }) {
  const { executive_summary, report_type } = payload.report;
  const isFailure = report_type === "FAILURE";
  return (
    <section className="glass-card relative overflow-hidden rounded-3xl p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-primary/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-[color:var(--color-primary-glow)]/15 blur-3xl" />
      <div className="relative">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary">
            {isFailure ? (
              <><AlertTriangle className="h-3 w-3" /> Analysis Status</>
            ) : (
              <><Sparkles className="h-3 w-3" /> Executive Summary</>
            )}
          </span>
          <span
            className={
              isFailure
                ? "inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400"
                : "inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-success"
            }
          >
            <ShieldCheck className="h-3 w-3" /> {executive_summary.confidence} confidence
          </span>
        </div>

        <h2 className="mt-5 text-2xl font-bold leading-tight tracking-tight sm:text-3xl">
          <span className={isFailure ? "text-foreground" : "gradient-text"}>
            {executive_summary.headline}
          </span>
        </h2>

        <div className="mt-5 max-w-[70ch] text-sm leading-[1.8] text-muted-foreground sm:text-base space-y-4 font-normal whitespace-pre-wrap">
          {executive_summary.summary.split(/\n+/).map((para, idx) => {
            const trimmed = para.trim();
            if (!trimmed) return null;
            return <p key={idx}>{trimmed}</p>;
          })}
        </div>
      </div>
    </section>
  );
}
