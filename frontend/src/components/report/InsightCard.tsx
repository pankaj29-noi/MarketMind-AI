import { motion, useReducedMotion } from "framer-motion";
import type { AppReportPayload } from "./Report";

export function InsightCards({ payload }: { payload: AppReportPayload }) {
  const insights = payload.report.insights;
  const reduceMotion = useReducedMotion();

  if (!insights || insights.length === 0) {
    return (
      <section className="surface-subtle px-5 py-6">
        <div className="type-section-label">Intelligence findings</div>
        <p className="mt-3 text-sm text-muted-foreground opacity-60">
          No insights available for this analysis.
        </p>
      </section>
    );
  }

  return (
    <section className="relative">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="type-section-label text-primary">Intelligence findings</div>
          <h3 className="mt-1 text-base font-semibold tracking-tight">
            Structured signals from this run
          </h3>
        </div>
        <span className="type-mono text-[10px] text-muted-foreground">
          {insights.length} finding{insights.length !== 1 ? "s" : ""}
        </span>
      </div>

      <ol className="space-y-0 border-l border-border/80">
        {insights.map((it, idx) => (
          <motion.li
            key={it.title + idx}
            initial={reduceMotion ? false : { opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: 0.22,
              delay: reduceMotion ? 0 : 0.05 + idx * 0.06,
              ease: [0.2, 0.8, 0.2, 1],
            }}
            className="relative border-b border-border/50 py-4 pl-5 last:border-b-0 mm-micro-row transition-colors"
          >
            <span
              className="absolute -left-[5px] top-5 h-2.5 w-2.5 rounded-full border border-primary/50 bg-background"
              aria-hidden
            />
            <div className="flex items-baseline gap-2">
              <span className="type-mono text-[10px] text-primary/70">
                {String(idx + 1).padStart(2, "0")}
              </span>
              <span className="type-section-label text-[10px] text-muted-foreground">
                Finding
              </span>
            </div>
            <h4 className="mt-1.5 text-sm font-semibold leading-snug tracking-tight text-foreground">
              {it.title}
            </h4>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground sm:text-[13px]">
              {it.body}
            </p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
