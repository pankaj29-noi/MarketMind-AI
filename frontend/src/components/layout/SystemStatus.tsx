import { cn } from "@/lib/utils";

export type SystemStatusKind = "ready" | "loaded" | "analyzing" | "idle";

interface SystemStatusProps {
  kind: SystemStatusKind;
  label?: string;
  className?: string;
  compact?: boolean;
}

const DEFAULT_LABELS: Record<SystemStatusKind, string> = {
  ready: "SYSTEM READY",
  loaded: "DATASET LOADED",
  analyzing: "ANALYZING",
  idle: "IDLE",
};

export function SystemStatus({
  kind,
  label,
  className,
  compact = false,
}: SystemStatusProps) {
  const text = label ?? DEFAULT_LABELS[kind];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 font-mono tracking-[0.12em]",
        compact ? "text-[10px]" : "text-[11px]",
        className
      )}
      data-status={kind}
    >
      <span
        className={cn(
          "relative flex h-1.5 w-1.5 shrink-0 rounded-full",
          kind === "analyzing" && "bg-warning",
          kind === "loaded" && "bg-success",
          kind === "ready" && "bg-primary/80",
          kind === "idle" && "bg-muted-foreground/50"
        )}
        aria-hidden
      >
        {(kind === "analyzing" || kind === "loaded") && (
          <span
            className={cn(
              "absolute inset-0 rounded-full opacity-60",
              kind === "analyzing" ? "bg-warning animate-ping" : "bg-success/40 mm-signal-pulse"
            )}
          />
        )}
      </span>
      <span
        className={cn(
          "uppercase",
          kind === "analyzing" && "text-warning",
          kind === "loaded" && "text-success",
          kind === "ready" && "text-muted-foreground",
          kind === "idle" && "text-muted-foreground/70"
        )}
      >
        {text}
      </span>
    </span>
  );
}

/** Derive shell status from real app state only. */
export function deriveSystemStatus(opts: {
  isAnalyzing?: boolean;
  hasDataset?: boolean;
}): SystemStatusKind {
  if (opts.isAnalyzing) return "analyzing";
  if (opts.hasDataset) return "loaded";
  return "ready";
}
