import { useState } from "react";
import { ChevronDown, Terminal } from "lucide-react";
import type { AppReportPayload } from "./Report";
import { cn } from "@/lib/utils";

export function DebugPanel({ payload }: { payload: AppReportPayload }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="overflow-hidden border border-border/70 bg-background/20">
      <button
        onClick={() => setOpen((v) => !v)}
        className="mm-micro-control flex w-full items-center justify-between px-4 py-3 text-left hover:bg-secondary/20 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
      >
        <div className="flex items-center gap-2.5">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
          <div>
            <div className="type-section-label text-muted-foreground">System trace</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground/80">
              Reasoning, plan, and runtime metadata
            </div>
          </div>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && payload.debug && (
        <div className="grid gap-3 border-t border-border p-4 animate-fade-in md:grid-cols-2">
          {payload.debug.llm_reasoning && (
            <Field label="LLM reasoning" value={payload.debug.llm_reasoning} />
          )}
          {payload.debug.execution_plan && (
            <Field label="Execution plan" value={payload.debug.execution_plan} mono />
          )}
          {payload.debug.execution_mode && (
            <Field label="Execution mode" value={payload.debug.execution_mode} mono />
          )}
          {payload.debug.analysis_source && (
            <Field label="Analysis source" value={String(payload.debug.analysis_source)} mono />
          )}
        </div>
      )}
    </section>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="border border-border/70 bg-background/30 p-3 md:col-span-2">
      <div className="type-section-label text-[10px]">{label}</div>
      <div
        className={cn(
          "mt-1.5 text-xs leading-relaxed text-foreground/85",
          mono && "font-mono"
        )}
      >
        {value}
      </div>
    </div>
  );
}
