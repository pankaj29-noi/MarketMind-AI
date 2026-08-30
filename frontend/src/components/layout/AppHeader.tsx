import { cn } from "@/lib/utils";
import { SystemStatus, type SystemStatusKind } from "./SystemStatus";

const MODULE_LABELS: Record<string, string> = {
  "/": "WORKSPACE",
  "/analytics": "ANALYTICS",
  "/lead": "LEAD INTELLIGENCE",
  "/monitoring": "AGENT MONITORING",
};

interface AppHeaderProps {
  activePath: string;
  statusKind: SystemStatusKind;
  datasetName?: string;
  rowCount?: number;
  hasDataset?: boolean;
  model?: string;
  className?: string;
}

export function AppHeader({
  activePath,
  statusKind,
  datasetName,
  rowCount,
  hasDataset,
  model,
  className,
}: AppHeaderProps) {
  const moduleLabel = MODULE_LABELS[activePath] ?? "WORKSPACE";

  return (
    <header
      className={cn(
        "mm-system-bar shrink-0 z-[var(--z-sticky)] flex h-11 items-center justify-between gap-4 border-b border-border/80 px-4 sm:px-5",
        className
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
        <div className="hidden items-center gap-2 sm:flex">
          <span className="type-mono text-[10px] tracking-[0.16em] text-muted-foreground">
            MARKETMIND
          </span>
          <span className="text-border" aria-hidden>
            //
          </span>
        </div>
        <h1 className="type-section-label truncate text-foreground">{moduleLabel}</h1>

        {hasDataset && datasetName && (
          <>
            <span className="hidden text-border sm:inline" aria-hidden>
              /
            </span>
            <span className="hidden min-w-0 truncate type-meta sm:inline">
              {datasetName}
              {typeof rowCount === "number" && rowCount > 0
                ? ` · ${rowCount.toLocaleString()} rows`
                : ""}
            </span>
          </>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {model && (
          <span className="hidden type-mono text-[10px] text-muted-foreground md:inline">
            {model}
          </span>
        )}
        <SystemStatus kind={statusKind} compact />
      </div>
    </header>
  );
}
