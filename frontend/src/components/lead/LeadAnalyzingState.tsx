import { useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { IntelligenceSignal } from "@/components/analysis/IntelligenceSignal";

/**
 * Loading presentation for Lead Intelligence.
 * Reflects only the real `loading` flag — no invented progress stages.
 */
export function LeadAnalyzingState({ requirement }: { requirement?: string }) {
  const reduceMotion = useReducedMotion();

  return (
    <section
      className="surface-command relative overflow-hidden px-4 py-5 sm:px-5"
      aria-live="polite"
      aria-busy
    >
      {!reduceMotion && <IntelligenceSignal mode="running" className="top-0" />}

      <div className="type-section-label text-primary/80">Opportunity analysis</div>
      <h3 className="mt-1.5 flex items-center gap-2 text-sm font-semibold tracking-tight">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        Analyzing requirement…
      </h3>
      {requirement && (
        <p className="mt-1 truncate type-meta">
          <span className="text-primary/70">›</span> {requirement}
        </p>
      )}

      <div className="relative mt-5 h-px w-full overflow-hidden bg-border/60">
        {!reduceMotion && (
          <span className="mm-intel-signal-beam mm-intel-signal-running absolute inset-y-0 left-0 w-1/3" />
        )}
      </div>
      <p className="mt-3 type-meta">
        Extracting signals and ranking supplier opportunities from live marketplace data.
      </p>
    </section>
  );
}
