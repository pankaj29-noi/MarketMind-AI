import { cn } from "@/lib/utils";

export type IntelligenceSignalMode =
  | "idle"
  | "running"
  | "complete"
  | "error"
  | "once";

interface IntelligenceSignalProps {
  mode?: IntelligenceSignalMode;
  className?: string;
  /** Vertical connector variant for pipeline / flow rails */
  orientation?: "horizontal" | "vertical";
}

/**
 * Signature MarketMind “intelligence signal” — CSS-only travel beam.
 * Purely presentational; no state or API side effects.
 */
export function IntelligenceSignal({
  mode = "idle",
  className,
  orientation = "horizontal",
}: IntelligenceSignalProps) {
  if (mode === "idle") return null;

  return (
    <div
      className={cn(
        "pointer-events-none absolute z-[2] overflow-hidden",
        orientation === "horizontal"
          ? "inset-x-0 top-0 h-px"
          : "inset-y-0 left-0 w-px",
        className
      )}
      aria-hidden
      data-mm-signal={mode}
    >
      <span
        className={cn(
          "mm-intel-signal-beam block",
          orientation === "horizontal" ? "h-full w-1/3" : "h-1/3 w-full",
          mode === "running" && "mm-intel-signal-running",
          mode === "complete" && "mm-intel-signal-complete",
          mode === "error" && "mm-intel-signal-error",
          mode === "once" && "mm-intel-signal-once",
          orientation === "vertical" && "mm-intel-signal-vertical"
        )}
      />
    </div>
  );
}
