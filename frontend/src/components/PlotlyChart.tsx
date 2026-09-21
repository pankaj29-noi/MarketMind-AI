import React, { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';
import { getChartThemeColors } from '@/lib/theme';

export interface PlotlyChartProps {
  chartData: any;
  chartId?: string;
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({ chartData, chartId }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !chartData) return;

    const colors = getChartThemeColors();

    try {
      Plotly.purge(containerRef.current);

      const plotData = chartData.data || [];
      const layout = chartData.layout || {};

      const themedLayout = {
        ...layout,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: {
          family: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
          color: colors.font,
          size: 11,
          ...(layout.font || {}),
        },
        xaxis: {
          ...layout.xaxis,
          gridcolor: colors.grid,
          linecolor: colors.line,
          zerolinecolor: colors.line,
          tickfont: { color: colors.font },
        },
        yaxis: {
          ...layout.yaxis,
          gridcolor: colors.grid,
          linecolor: colors.line,
          zerolinecolor: colors.line,
          tickfont: { color: colors.font },
        },
        legend: {
          ...(layout.legend || {}),
          font: { color: colors.font, size: 11 },
        },
        margin: { t: 40, r: 20, l: 50, b: 40, ...(layout.margin || {}) },
      };

      Plotly.newPlot(containerRef.current, plotData, themedLayout, {
        responsive: true,
        displayModeBar: false,
      });
    } catch (e) {
      console.error('Plotly rendering failed:', e);
    }

    return () => {
      const el = containerRef.current;
      if (el) {
        try {
          Plotly.purge(el);
        } catch {
          /* ignore purge errors on unmount */
        }
      }
    };
  }, [chartData]);

  // Re-theme when the document dark class toggles without remounting chartData.
  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      if (!containerRef.current || !chartData) return;
      const colors = getChartThemeColors();
      Plotly.relayout(containerRef.current, {
        'font.color': colors.font,
        'xaxis.gridcolor': colors.grid,
        'xaxis.linecolor': colors.line,
        'xaxis.zerolinecolor': colors.line,
        'xaxis.tickfont.color': colors.font,
        'yaxis.gridcolor': colors.grid,
        'yaxis.linecolor': colors.line,
        'yaxis.zerolinecolor': colors.line,
        'yaxis.tickfont.color': colors.font,
        'legend.font.color': colors.font,
      }).catch(() => undefined);
    });
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, [chartData]);

  return (
    <div
      id={chartId}
      ref={containerRef}
      className="w-full h-full min-h-[450px]"
      style={{ minHeight: '450px' }}
    />
  );
};
export default PlotlyChart;
