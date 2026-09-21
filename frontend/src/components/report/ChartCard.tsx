/** Lazy Plotly chart card — keeps plotly out of the initial JS bundle. */
import { Suspense, lazy, useCallback } from "react";
import { Download } from "lucide-react";
import { ReportCard } from "./ReportCard";
import type { ChartSpec } from "../../types/index";

const PlotlyChart = lazy(() => import("../PlotlyChart"));

export function ChartCard({ chart, chartId }: { chart: ChartSpec; chartId: string }) {
  const handleExport = useCallback(async () => {
    const el = document.getElementById(chartId);
    if (!el) return;
    const Plotly = (await import("plotly.js-dist-min")).default;
    Plotly.downloadImage(el as any, { format: "png", filename: chartId });
  }, [chartId]);

  return (
    <ReportCard
      eyebrow="Chart"
      title={chart.title}
      action={
        <button
          onClick={handleExport}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background/40 px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground cursor-pointer"
        >
          <Download className="h-3.5 w-3.5" /> PNG
        </button>
      }
    >
      <div className="w-full mt-4 overflow-hidden border border-border bg-background/20 relative z-0 min-h-[450px]">
        <Suspense
          fallback={
            <div className="flex h-[450px] items-center justify-center text-sm text-muted-foreground">
              Loading chart…
            </div>
          }
        >
          <PlotlyChart chartData={chart.plotly_json} chartId={chartId} />
        </Suspense>
      </div>
    </ReportCard>
  );
}
