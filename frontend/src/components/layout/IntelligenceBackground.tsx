/**
 * Ambient intelligence background layer for MarketMind AI.
 * Purely presentational — no routing, API, or state side effects.
 */
export function IntelligenceBackground() {
  return (
    <div
      className="intelligence-bg"
      aria-hidden="true"
      data-mm-foundation="ambient-bg"
    >
      <div className="mm-ambient-drift" />
      <div className="mm-scan-line" />
    </div>
  );
}
