import React, { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

export interface PlotlyChartProps {
  chartData: any;
  chartId?: string;
}

function readThemeColors(isDark: boolean) {
  return isDark
    ? {
        font: '#f4f4f5',
        grid: 'rgba(255, 255, 255, 0.08)',
        line: 'rgba(255, 255, 255, 0.12)',
      }
    : {
        font: '#18181b',
        grid: 'rgba(24, 24, 27, 0.08)',
        line: 'rgba(24, 24, 27, 0.14)',
      };
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({ chartData, chartId }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !chartData) return;

    const isDark = document.documentElement.classList.contains('dark');
    const colors = readThemeColors(isDark);

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
      if (containerRef.current) {
        try {
          Plotly.purge(containerRef.current);
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
      const isDark = root.classList.contains('dark');
      const colors = readThemeColors(isDark);
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
