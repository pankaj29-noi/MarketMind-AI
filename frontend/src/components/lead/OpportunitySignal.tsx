import { motion, useReducedMotion } from "framer-motion";
import {
  BadgeCheck,
  Clock,
  MapPin,
  Star,
  ChevronDown,
} from "lucide-react";
import { useState } from "react";
import type { RankedSupplier } from "@/types/lead";
import { cn } from "@/lib/utils";
import { SignalMeter } from "./SignalMeter";

interface OpportunitySignalProps {
  supplier: RankedSupplier;
  index: number;
  prioritized?: boolean;
}

export function OpportunitySignal({
  supplier: s,
  index,
  prioritized = false,
}: OpportunitySignalProps) {
  const [open, setOpen] = useState(prioritized);
  const reduceMotion = useReducedMotion();
  const hasDetail = !!(s.explanation || s.matching_products?.length);

  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.22,
        delay: reduceMotion ? 0 : Math.min(index * 0.05, 0.25),
        ease: [0.2, 0.8, 0.2, 1],
      }}
      className={cn(
        "mm-micro-row relative overflow-hidden border border-border/70 bg-background/25 transition-colors",
        prioritized && "border-primary/30 bg-primary/[0.03]",
        "hover:border-primary/35"
      )}
    >
      <div
        className={cn(
          "absolute inset-y-0 left-0 w-[2px]",
          prioritized ? "bg-primary/80" : "bg-primary/35"
        )}
        aria-hidden
      />

      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-3.5 pl-5 sm:px-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="type-mono text-[10px] text-primary/80">
              {String(s.rank).padStart(2, "0")}
            </span>
            <h4 className="truncate text-sm font-semibold tracking-tight">{s.name}</h4>
            {s.verified && (
              <span className="inline-flex items-center gap-1 border border-success/30 bg-success/10 px-1.5 py-0.5 type-mono text-[9px] text-success">
                <BadgeCheck className="h-3 w-3" /> Verified
              </span>
            )}
            {prioritized && (
              <span className="type-section-label text-[9px] text-primary">
                Strongest signal
              </span>
            )}
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" strokeWidth={1.75} />
              {[s.city, s.state].filter(Boolean).join(", ") || "—"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Star className="h-3 w-3 text-primary/70" strokeWidth={1.75} />
              {s.rating != null ? s.rating.toFixed(1) : "—"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" strokeWidth={1.75} />
              {s.response_time_hours != null
                ? `${s.response_time_hours}h response`
                : "Response N/A"}
            </span>
          </div>
        </div>

        <SignalMeter score={s.final_score} />
      </div>

      {hasDetail && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mm-micro-control flex w-full items-center justify-between border-t border-border/60 px-4 py-2 pl-5 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40 sm:px-5"
            aria-expanded={open}
          >
            <span className="type-section-label text-[10px] text-muted-foreground">
              Why this lead
            </span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 text-muted-foreground transition-transform duration-[var(--duration-fast)]",
                open && "rotate-180"
              )}
            />
          </button>
          {open && (
            <div className="space-y-3 border-t border-border/50 px-4 py-3 pl-5 animate-fade-in sm:px-5">
              {s.explanation && (
                <div>
                  <div className="type-section-label text-[9px] text-primary/70">
                    Matching evidence
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {s.explanation}
                  </p>
                </div>
              )}
              {s.matching_products?.length > 0 && (
                <div>
                  <div className="type-section-label text-[9px] text-primary/70">
                    Relevant signals
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {s.matching_products.slice(0, 6).map((name) => (
                      <span
                        key={name}
                        className="border border-border bg-background/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {[
                  { label: "Product match", value: s.product_match_score },
                  { label: "Rating", value: s.rating_score },
                  { label: "Location", value: s.location_score },
                  { label: "Verified", value: s.verified_score },
                  { label: "Response", value: s.response_time_score },
                  { label: "Orders", value: s.order_performance_score },
                ].map((f) => (
                  <div
                    key={f.label}
                    className="border border-border/60 bg-background/20 px-2 py-1.5"
                  >
                    <div className="type-meta text-[9px]">{f.label}</div>
                    <div className="type-mono mt-0.5 text-[11px]">
                      {(f.value * 100).toFixed(0)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </motion.article>
  );
}
