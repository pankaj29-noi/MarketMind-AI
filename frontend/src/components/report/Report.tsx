import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ExecutiveSummaryCard } from "./ExecutiveSummaryCard";
import { ResultsTableCard } from "./ResultsTableCard";
import { ChartCard } from "./ChartCard";
import { InsightCards } from "./InsightCard";
import { RecommendationCards } from "./RecommendationCard";
import { SQLViewer } from "./SQLViewer";
import { DebugPanel } from "./DebugPanel";
import { ReportActions } from "./ReportActions";
import { IntelligenceSignal } from "@/components/analysis/IntelligenceSignal";
import type { ReportSection, DebugInfo } from "@/types/index";

export interface AppReportPayload {
  report: ReportSection;
  debug?: DebugInfo;
  model?: string;
  provider?: string;
}

function FlowLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mm-flow-label type-section-label text-muted-foreground/80">
      {children}
    </div>
  );
}

function Reveal({
  delay,
  children,
}: {
  delay: number;
  children: React.ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className="mm-flow-section"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.26,
        delay: reduceMotion ? 0 : delay / 1000,
        ease: [0.2, 0.8, 0.2, 1],
      }}
    >
      {children}
    </motion.div>
  );
}

export function Report({ payload }: { payload: AppReportPayload }) {
  const tableCount = payload.report.tables?.length ?? 0;
  const chartCount = payload.report.charts?.length ?? 0;
  const isFailure = payload.report.report_type === "FAILURE";
  const reduceMotion = useReducedMotion();

  return (
    <div className="mm-analysis-flow relative space-y-6">
      {!reduceMotion && (
        <IntelligenceSignal
          mode={isFailure ? "error" : "complete"}
          className="left-0 top-0 hidden h-auto w-px sm:block"
          orientation="vertical"
        />
      )}

      <Reveal delay={0}>
        <FlowLabel>AI analysis complete</FlowLabel>
        <ExecutiveSummaryCard payload={payload} />
      </Reveal>

      {(tableCount > 0 || chartCount > 0) && (
        <Reveal delay={80}>
          <FlowLabel>Data evidence</FlowLabel>
          <div className="relative flex flex-wrap items-center gap-3 border border-border/70 bg-secondary/15 px-3 py-2 overflow-hidden">
            {!reduceMotion && <IntelligenceSignal mode="once" />}
            <span className="type-section-label text-primary">Result signal</span>
            {tableCount > 0 && (
              <span className="type-mono text-[11px] text-muted-foreground">
                {tableCount} table{tableCount !== 1 ? "s" : ""} ·{" "}
                {payload.report.tables[0].rows.length.toLocaleString()} rows
              </span>
            )}
            {chartCount > 0 && (
              <span className="type-mono text-[11px] text-muted-foreground">
                {chartCount} chart{chartCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </Reveal>
      )}

      {tableCount > 0 && (
        <Reveal delay={130}>
          <ResultsTableCard payload={payload} />
        </Reveal>
      )}

      {chartCount > 0 && (
        <Reveal delay={190}>
          <FlowLabel>Visual analysis</FlowLabel>
          <div className={chartCount === 1 ? "" : "grid gap-4 lg:grid-cols-2"}>
            {payload.report.charts.map((c, i) => (
              <ChartCard
                key={i}
                chart={c}
                chartId={`chart-${i}-${payload.report.title.replace(/\s/g, "-").slice(0, 20)}`}
              />
            ))}
          </div>
        </Reveal>
      )}

      {payload.report.insights?.length > 0 && (
        <Reveal delay={250}>
          <InsightCards payload={payload} />
        </Reveal>
      )}

      {payload.report.recommendations?.length > 0 && (
        <Reveal delay={300}>
          <RecommendationCards payload={payload} />
        </Reveal>
      )}

      {payload.debug?.generated_code && (
        <Reveal delay={340}>
          <SQLViewer payload={payload} />
        </Reveal>
      )}

      {payload.debug && (
        <Reveal delay={380}>
          <DebugPanel payload={payload} />
        </Reveal>
      )}

      <Reveal delay={420}>
        <ReportActions payload={payload} />
      </Reveal>
    </div>
  );
}
