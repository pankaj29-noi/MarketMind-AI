import { useState } from "react";
import {
  Database,
  Search,
  Plus,
  MessageSquare,
  BarChart3,
  Table2,
  Hash,
  Type,
  Calendar,
  CircleCheck,
  ChevronDown,
  ChevronLeft,
  Target,
  Activity,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Column, HistoricalReport } from "@/types/index";
import { ModuleNavItem } from "./ModuleNavItem";
import { SystemStatus, deriveSystemStatus } from "./SystemStatus";

interface AppSidebarProps {
  hasDataset: boolean;
  datasetName?: string;
  rowCount?: number;
  columns?: Column[];
  tables?: string[];
  history: HistoricalReport[];
  onUpload: () => void;
  onSelectHistory: (id: string) => void;
  selectedHistoryId?: string;
  activePath: string;
  setActivePath: (path: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isAnalyzing?: boolean;
}

const getIconForType = (type: string) => {
  if (type.includes("int") || type.includes("float") || type.includes("numeric")) return Hash;
  if (type.includes("date") || type.includes("time")) return Calendar;
  return Type;
};

function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "Just now";
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

const MODULES = [
  { path: "/", label: "WORKSPACE", icon: Sparkles },
  { path: "/analytics", label: "ANALYTICS", icon: BarChart3 },
  { path: "/lead", label: "LEAD INTELLIGENCE", icon: Target },
  { path: "/monitoring", label: "AGENT MONITORING", icon: Activity },
] as const;

function BrandMark() {
  return (
    <div
      className="relative grid h-8 w-8 shrink-0 place-items-center"
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="h-8 w-8">
        <rect
          x="1.5"
          y="1.5"
          width="29"
          height="29"
          rx="2"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.22"
          className="text-primary"
        />
        <path
          d="M8 22 L8 10 L16 18 L24 10 L24 22"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="miter"
          className="text-primary"
        />
        <circle cx="16" cy="14" r="1.6" className="fill-primary mm-signal-pulse" />
      </svg>
    </div>
  );
}

export function AppSidebar({
  hasDataset,
  datasetName,
  rowCount,
  columns,
  tables,
  history,
  onUpload,
  onSelectHistory,
  selectedHistoryId,
  activePath,
  setActivePath,
  isCollapsed,
  onToggleCollapse,
  isAnalyzing = false,
}: AppSidebarProps) {
  const [schemaOpen, setSchemaOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredColumns =
    columns?.filter((c) =>
      c.name.toLowerCase().includes(searchQuery.toLowerCase())
    ) ?? [];

  const statusKind = deriveSystemStatus({ isAnalyzing, hasDataset });

  return (
    <aside
      className={cn(
        "mm-console-sidebar flex h-full shrink-0 flex-col border-r border-border/80 bg-sidebar/90 text-sidebar-foreground backdrop-blur-sm transition-[width] duration-300 ease-in-out overflow-hidden",
        isCollapsed ? "w-0 border-r-0" : "w-72"
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col" style={{ width: "18rem" }}>
        {/* Brand */}
        <div className="shrink-0 border-b border-border/60 px-3.5 pb-3 pt-3.5">
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <BrandMark />
              <div className="min-w-0">
                <div className="type-app-title tracking-[0.08em]">MARKETMIND</div>
                <div className="type-meta mt-0.5 tracking-[0.14em]">
                  BUSINESS INTELLIGENCE SYSTEM
                </div>
              </div>
            </div>
            <button
              onClick={onToggleCollapse}
              className="ml-1 grid h-7 w-7 shrink-0 place-items-center text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
              aria-label="Collapse sidebar"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* System modules */}
        <nav
          className="shrink-0 space-y-0.5 border-b border-border/60 px-2 py-2.5"
          aria-label="System modules"
        >
          <div className="type-section-label mb-1.5 px-2.5 opacity-70">
            Modules
          </div>
          {MODULES.map(({ path, label, icon: Icon }) => (
            <ModuleNavItem
              key={path}
              label={label}
              icon={<Icon className="h-3.5 w-3.5" strokeWidth={1.75} />}
              active={activePath === path}
              onClick={() => setActivePath(path)}
            />
          ))}
        </nav>

        {/* New analysis */}
        <div className="shrink-0 px-3.5 py-3">
          <button
            onClick={onUpload}
            className="group interactive-quiet flex w-full items-center justify-between border border-primary/25 bg-primary/[0.08] px-3 py-2.5 text-left text-xs font-medium text-primary hover:border-primary/45 hover:bg-primary/[0.14]"
          >
            <span className="flex items-center gap-2">
              <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
              New analysis
            </span>
            <kbd className="type-mono rounded border border-primary/20 bg-background/40 px-1.5 py-0.5 text-[10px] text-primary/80">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* Dataset — DATA CONTEXT */}
        {hasDataset && (
          <div className="shrink-0 px-3.5 pb-3">
            <div className="surface-command px-3 py-2.5">
              <div className="type-section-label text-primary/80">Data context</div>
              <div className="mt-2 flex items-center gap-2">
                <div className="grid h-7 w-7 shrink-0 place-items-center border border-border bg-secondary/60">
                  <Database className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium tracking-tight">
                    {datasetName || "dataset.csv"}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                    <CircleCheck className="h-3 w-3 text-success" />
                    Dataset available
                  </div>
                </div>
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-1.5 text-[11px]">
                <div className="border border-border/80 bg-background/30 px-2 py-1.5">
                  <div className="type-meta">
                    {tables && tables.length > 1 ? "Total rows" : "Rows"}
                  </div>
                  <div className="type-mono mt-0.5 text-[12px] font-medium">
                    {rowCount?.toLocaleString() || 0}
                  </div>
                </div>
                <div className="border border-border/80 bg-background/30 px-2 py-1.5">
                  <div className="type-meta">
                    {tables && tables.length > 1 ? "Tables" : "Columns"}
                  </div>
                  <div className="type-mono mt-0.5 text-[12px] font-medium">
                    {tables && tables.length > 1
                      ? tables.length
                      : columns?.length || 0}
                  </div>
                </div>
              </div>
              {tables && tables.length > 1 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {tables.map((t) => (
                    <span
                      key={t}
                      className="border border-border bg-background/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Scrollable: schema + history */}
        <div className="scrollbar-thin flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3.5">
          {hasDataset && columns && columns.length > 0 && (
            <div className="shrink-0">
              {schemaOpen && (
                <div className="relative mb-2">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search columns…"
                    className="w-full border border-border bg-secondary/30 py-1.5 pl-7 pr-2.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/25"
                  />
                </div>
              )}

              <button
                onClick={() => setSchemaOpen((v) => !v)}
                className="flex w-full items-center justify-between py-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                <span className="flex items-center gap-1.5">
                  <Table2 className="h-3 w-3" /> Schema explorer ({columns.length})
                </span>
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 transition-transform",
                    schemaOpen ? "" : "-rotate-90"
                  )}
                />
              </button>

              {schemaOpen && (
                <div className="mm-schema-scan mb-2 divide-y divide-border/50 border border-border/60 bg-background/20">
                  {filteredColumns.map((c) => {
                    const Icon = getIconForType(c.dtype);
                    return (
                      <div
                        key={c.name}
                        className="flex items-center justify-between gap-2 px-2.5 py-1.5 text-xs mm-micro-row hover:bg-sidebar-accent/50"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <Icon className="h-3 w-3 shrink-0 text-muted-foreground/70" strokeWidth={1.75} />
                          <span className="truncate font-mono text-[11px] text-foreground/90">
                            {c.name}
                          </span>
                        </span>
                        <span className="shrink-0 border border-border/80 bg-secondary/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-muted-foreground">
                          {c.dtype}
                        </span>
                      </div>
                    );
                  })}
                  {filteredColumns.length === 0 && (
                    <div className="py-3 text-center text-[11px] text-muted-foreground">
                      No columns match
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex-1">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              className="flex w-full items-center justify-between py-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
            >
              <span className="flex items-center gap-1.5">
                <MessageSquare className="h-3 w-3" /> Recent
              </span>
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  historyOpen ? "" : "-rotate-90"
                )}
              />
            </button>

            {historyOpen && (
              <div className="space-y-0.5 pb-2">
                {history.length === 0 ? (
                  <div className="py-4 text-center text-[11px] text-muted-foreground opacity-60">
                    No history yet
                  </div>
                ) : (
                  history.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => onSelectHistory(c.id.toString())}
                      className={cn(
                        "block w-full px-2.5 py-2.5 text-left transition-colors group",
                        selectedHistoryId === c.id.toString()
                          ? "bg-sidebar-accent text-sidebar-accent-foreground"
                          : "hover:bg-sidebar-accent/60"
                      )}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="truncate text-xs font-medium leading-snug">
                          {c.question}
                        </div>
                        {c.success !== undefined && (
                          <div
                            className={cn(
                              "mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full",
                              c.success ? "bg-success" : "bg-destructive"
                            )}
                          />
                        )}
                      </div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">
                        {c.created_at
                          ? formatRelativeTime(String(c.created_at))
                          : ""}
                      </div>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Console footer status — derived from real session state */}
        <div className="shrink-0 border-t border-border/70 px-3.5 py-3">
          <SystemStatus kind={statusKind} />
          {hasDataset && (
            <div className="mt-1.5 truncate type-meta">
              {datasetName || "dataset"}
              {typeof rowCount === "number"
                ? ` · ${rowCount.toLocaleString()} rows`
                : ""}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
