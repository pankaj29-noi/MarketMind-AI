import { cn } from "@/lib/utils";

/** Segmented signal meter — display only; score must be real 0–1 (or 0–100). */
export function SignalMeter({
  score,
  className,
  size = "md",
}: {
  score: number;
  className?: string;
  size?: "sm" | "md";
}) {
  const normalized = score > 1 ? Math.min(1, score / 100) : Math.max(0, Math.min(1, score));
  const pct = Math.round(normalized * 100);
  const segments = 5;
  const filled = Math.round(normalized * segments);

  return (
    <div className={cn("flex flex-col items-end gap-1", className)} title={`${pct}% match`}>
      <div className="flex items-baseline gap-1.5">
        <span
          className={cn(
            "font-semibold tabular-nums tracking-tight text-primary",
            size === "md" ? "text-xl" : "text-sm"
          )}
        >
          {pct}
        </span>
        <span className="type-mono text-[9px] text-muted-foreground">SIG</span>
      </div>
      <div className="flex gap-0.5" aria-hidden>
        {Array.from({ length: segments }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 rounded-[1px] transition-colors duration-[var(--duration-fast)]",
              size === "md" ? "w-3.5" : "w-2.5",
              i < filled
                ? "bg-primary"
                : "bg-border"
            )}
          />
        ))}
      </div>
    </div>
  );
}
