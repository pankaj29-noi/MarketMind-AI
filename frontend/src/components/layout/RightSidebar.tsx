import { useState, useRef } from "react";
import { Activity, CheckCircle2, ChevronRight, ChevronUp, Clock, Cpu, Loader2, Sparkles, TrendingUp, XCircle, Zap, Table, BarChart2, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { resolvePipelineSteps } from "@/lib/pipelineSteps";

interface TraceStep {
  step: string;
  status: "pending" | "running" | "success" | "failed" | "skipped";
  duration_ms?: number;
  details?: string;
}

interface RightSidebarProps {
  trace: TraceStep[];
  activeExecutionTime?: number;
  activeRetryCount?: number;
  activeModel?: string;
  activeProvider?: string;
  activeStatus?: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isAnalyzing?: boolean;
  latestReport?: any;
}

export function RightSidebar({
  trace,
  activeExecutionTime,
  activeRetryCount,
  activeModel,
  activeProvider,
  activeStatus,
  isCollapsed,
  onToggleCollapse,
  isAnalyzing,
  latestReport,
}: RightSidebarProps) {
  const [openStep, setOpenStep] = useState<number | null>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const hasTrace = trace && trace.length > 0;
  const pipelineStatus = isAnalyzing ? "Running" : activeStatus === false ? "Failed" : hasTrace ? "Completed" : "Idle";

  const handleScroll = () => {
    if (scrollRef.current) {
      setShowScrollTop(scrollRef.current.scrollTop > 200);
    }
  };

  const scrollToTop = () => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  const resolvedSteps = resolvePipelineSteps({
    trace,
    isAnalyzing,
    activeStatus,
  });

  const rowsReturned = latestReport?.tables?.[0]?.rows?.length;
  const chartsGenerated = latestReport?.charts?.length || 0;
  const confidence = latestReport?.executive_summary?.confidence;
  const executionStatus = activeStatus === false ? "Failed" : isAnalyzing ? "Running" : hasTrace ? "Success" : "Idle";

  return (
    <>
      {/* Collapse toggle tab — always visible */}
      <div 
        className="fixed top-1/2 z-30 -translate-y-1/2 hidden xl:flex items-center transition-[right] duration-300 ease-in-out"
        style={{ right: isCollapsed ? 0 : "320px" }}
      >
        <button
          onClick={onToggleCollapse}
          className="grid h-10 w-5 place-items-center rounded-l-lg border border-r-0 border-border bg-sidebar/80 text-muted-foreground hover:bg-sidebar hover:text-foreground transition-colors shadow-sm"
          aria-label={isCollapsed ? "Open right sidebar" : "Close right sidebar"}
        >
          <ChevronRight className={cn("h-3.5 w-3.5 transition-transform duration-300 ease-in-out", isCollapsed ? "rotate-180" : "")} />
        </button>
      </div>

      <aside
        className={cn(
          "hidden xl:flex h-screen shrink-0 flex-col border-l border-border bg-sidebar/40 transition-[width] duration-300 ease-in-out overflow-hidden relative",
          isCollapsed ? "w-0 border-l-0" : "w-80"
        )}
      >
        {/* Scrollable sidebar container */}
        <div 
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-4 overflow-y-auto scrollbar-custom animate-fade-in" 
          style={{ width: "20rem" }}
        >
          
          {/* 1. Pipeline — secondary system view */}
          <div className="surface-subtle shrink-0 p-3 sm:p-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 type-section-label text-foreground">
                <Activity className="h-3.5 w-3.5 text-primary" /> Pipeline
              </div>
              <span className={cn(
                "px-2 py-0.5 type-mono text-[10px]",
                pipelineStatus === "Completed" ? "bg-success/15 text-success" :
                pipelineStatus === "Running"   ? "bg-primary/15 text-primary" :
                pipelineStatus === "Failed"    ? "bg-destructive/15 text-destructive" :
                "bg-secondary text-muted-foreground"
              )}>
                {pipelineStatus}
              </span>
            </div>

            <ol className="mt-2.5 space-y-1.5">
              {resolvedSteps.map((s, i) => {
                const isRunning = s.status === "running";
                const isDone = s.status === "success";
                const isFailed = s.status === "failed";
                const isPending = s.status === "pending";

                return (
                  <li key={i}>
                    <button
                      className={cn(
                        "flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left border transition-all duration-300",
                        isRunning
                          ? "bg-primary/[0.06] border-primary/30 font-medium"
                          : isPending
                          ? "border-transparent opacity-45"
                          : "border-transparent hover:bg-sidebar-accent/30"
                      )}
                      onClick={() => hasTrace && s.details ? setOpenStep(openStep === i ? null : i) : undefined}
                    >
                      <div className={cn(
                        "grid h-6 w-6 shrink-0 place-items-center rounded-full border transition-all duration-300",
                        isDone    ? "bg-success/10 text-success border-success/20" :
                        isFailed  ? "bg-destructive/10 text-destructive border-destructive/20" :
                        isRunning ? "bg-primary/10 text-primary border-primary/20 ring-1 ring-primary/20" :
                        "bg-secondary text-muted-foreground border-border"
                      )}>
                        {isRunning ? (
                          <Loader2 className="h-3 w-3 animate-spin text-primary" />
                        ) : isDone ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                        ) : isFailed ? (
                          <XCircle className="h-3.5 w-3.5 text-destructive" />
                        ) : (
                          <div className="h-2 w-2 rounded-full bg-muted-foreground/40" />
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className={cn(
                          "text-xs transition-colors duration-300",
                          isRunning ? "text-primary font-semibold" :
                          isDone ? "text-foreground font-medium" :
                          "text-muted-foreground"
                        )}>{s.step}</div>
                        {s.duration_ms !== undefined && isDone && (
                          <div className="text-[10px] text-muted-foreground font-mono mt-0.5">{s.duration_ms} ms</div>
                        )}
                        {isRunning && (
                          <div className="text-[10px] text-primary/80 mt-0.5 font-medium">Processing…</div>
                        )}
                      </div>

                      <div className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full transition-all duration-300",
                        isDone   ? "bg-success" :
                        isFailed ? "bg-destructive" :
                        isRunning ? "bg-primary animate-pulse" :
                        "bg-border"
                      )} />
                    </button>

                    {openStep === i && s.details && (
                      <div className="ml-9 mt-1 bg-secondary/40 px-3 py-2 text-[11px] text-muted-foreground animate-fade-in">
                        {s.details}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </div>

          {/* 2. Run statistics — secondary */}
          <div className="surface-subtle shrink-0 p-4">
            <div className="flex items-center gap-2 type-section-label text-foreground">
              <Cpu className="h-3.5 w-3.5 text-primary" /> Run statistics
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              <Stat icon={Clock} label="Latency" value={activeExecutionTime ? `${(activeExecutionTime / 1000).toFixed(2)}s` : "--"} />
              <Stat icon={Zap} label="Retries" value={activeRetryCount !== undefined ? String(activeRetryCount) : "--"} />
              <Stat icon={Sparkles} label="Provider" value={activeProvider || "--"} />
              <Stat icon={TrendingUp} label="Model" value={activeModel || "--"} />
              
              {/* Expanded SaaS stats */}
              {rowsReturned !== undefined && (
                <Stat icon={Table} label="Rows returned" value={String(rowsReturned)} />
              )}
              {chartsGenerated > 0 && (
                <Stat icon={BarChart2} label="Charts" value={String(chartsGenerated)} />
              )}
              {confidence && (
                <Stat icon={ShieldCheck} label="Confidence" value={confidence} />
              )}
              {executionStatus && (
                <Stat icon={Activity} label="Status" value={executionStatus} />
              )}
            </div>
          </div>
        </div>
        {/* 4. Floating Scroll to Top button */}
        <button
          onClick={scrollToTop}
          className={cn(
            "absolute bottom-6 right-6 z-20 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background/80 backdrop-blur-md text-muted-foreground hover:bg-background hover:text-foreground hover:border-primary/40 transition-all duration-300 shadow-md hover:scale-105",
            showScrollTop ? "opacity-100 scale-100" : "opacity-0 scale-75 pointer-events-none"
          )}
          title="Scroll to top"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
      </aside>
    </>
  );
}

function Stat({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/40 p-2">
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <Icon className="h-3 w-3 text-primary" /> {label}
      </div>
      <div className="mt-0.5 truncate text-sm font-semibold">{value}</div>
    </div>
  );
}