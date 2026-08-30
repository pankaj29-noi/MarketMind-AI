import React, { useState } from 'react';
import {
  Loader2,
  Target,
  Package,
  MapPin,
  Clock,
  BadgeCheck,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  Activity,
  Radar,
} from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { toast } from '@/lib/toast';
import type { LeadAnalyzeResponse } from '@/types/lead';
import { LEAD_EXAMPLE_REQUIREMENTS } from '@/types/lead';
import { submitWorkflowFeedback } from '@/services/observability';
import { API_BASE } from '@/lib/api';
import { cn } from '@/lib/utils';
import { IntelligenceSignal } from '@/components/analysis/IntelligenceSignal';
import { OpportunitySignal } from '@/components/lead/OpportunitySignal';
import { LeadAnalyzingState } from '@/components/lead/LeadAnalyzingState';
import { SignalMeter } from '@/components/lead/SignalMeter';

interface LeadIntelligenceProps {
  sessionId?: string | null;
  onSessionCreated?: (sessionId: string) => void;
}

function deriveLeadPhase(opts: {
  loading: boolean;
  result: LeadAnalyzeResponse | null;
}): string {
  if (opts.loading) return 'ANALYZING REQUIREMENTS';
  if (!opts.result) return 'READY';
  const status = opts.result.workflow_status;
  if (status === 'complete') {
    const n = opts.result.recommended_suppliers?.length ?? 0;
    return n > 0 ? 'RESULTS AVAILABLE' : 'COMPLETE';
  }
  if (status === 'needs_info') return 'NEEDS INFO';
  return status.replace(/_/g, ' ').toUpperCase();
}

export const LeadIntelligence: React.FC<LeadIntelligenceProps> = ({
  sessionId,
  onSessionCreated,
}) => {
  const [requirement, setRequirement] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LeadAnalyzeResponse | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<'helpful' | 'not_helpful' | null>(null);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const reduceMotion = useReducedMotion();

  const analyze = async (text?: string) => {
    const req = (text ?? requirement).trim();
    if (!req) {
      toast('Enter a buyer requirement first', 'error');
      return;
    }
    setRequirement(req);
    setLoading(true);
    setResult(null);
    setFeedbackRating(null);
    setFeedbackComment('');
    setFeedbackSent(false);
    try {
      const response = await fetch(`${API_BASE}/marketplace/lead/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          requirement: req,
          session_id: sessionId || undefined,
        }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || 'Lead analysis failed');
      }
      const data: LeadAnalyzeResponse = await response.json();
      setResult(data);
      if (data.session_id && onSessionCreated) {
        onSessionCreated(data.session_id);
      }
      if (data.workflow_status === 'complete') {
        toast(
          `Found ${data.recommended_suppliers?.length ?? 0} supplier recommendations`,
          'success'
        );
      } else if (data.workflow_status === 'needs_info') {
        toast(data.validation_result?.message || 'More information needed', 'error');
      } else if (data.error) {
        toast(data.error, 'error');
      }
    } catch (err: any) {
      toast(err.message || 'Lead analysis failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (rating: 'helpful' | 'not_helpful') => {
    if (!result?.run_id || feedbackSending || feedbackSent) return;
    setFeedbackRating(rating);
    setFeedbackSending(true);
    try {
      await submitWorkflowFeedback(result.run_id, rating, feedbackComment.trim() || undefined);
      setFeedbackSent(true);
      toast(rating === 'helpful' ? 'Thanks for the feedback' : 'Feedback recorded — we will improve', 'success');
    } catch (err: any) {
      toast(err.message || 'Could not save feedback', 'error');
      setFeedbackRating(null);
    } finally {
      setFeedbackSending(false);
    }
  };

  const extracted = result?.extracted_requirement;
  const validation = result?.validation_result;
  const nodes = result?.node_executions || [];
  const suppliers = result?.recommended_suppliers || [];
  const phase = deriveLeadPhase({ loading, result });

  return (
    <div className="flex h-full w-full flex-col bg-transparent text-foreground">
      {/* Module header */}
      <header className="mm-system-bar sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border/80 px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <div className="type-section-label text-primary">Lead intelligence</div>
          <h1 className="mt-0.5 flex items-center gap-2 text-sm font-semibold tracking-tight sm:text-base">
            <Radar className="h-4 w-4 text-primary" strokeWidth={1.75} />
            AI-powered opportunity discovery
          </h1>
        </div>
        <span className="inline-flex shrink-0 items-center gap-2 type-mono text-[10px] tracking-[0.12em] text-muted-foreground">
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              loading ? 'bg-warning mm-signal-pulse' :
              result?.workflow_status === 'complete' ? 'bg-success' :
              result?.workflow_status === 'needs_info' ? 'bg-warning' :
              result ? 'bg-destructive/80' : 'bg-primary/70'
            )}
          />
          {phase}
        </span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6">
          {/* Opportunity brief */}
          <section className="surface-command relative overflow-hidden">
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-2">
              <div className="flex items-center gap-2">
                <span className="type-mono text-[10px] text-primary/80">OPPORTUNITY BRIEF</span>
                <span className="text-border">//</span>
                <span className="type-meta">
                  {loading ? 'PROCESSING' : 'AWAITING INPUT'}
                </span>
              </div>
              <Target className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
            </div>

            <div className="space-y-4 px-4 py-4">
              <p className="type-meta">
                Describe your target customer or buyer requirement. MarketMind extracts signals,
                matches products, and ranks suppliers.
              </p>
              <div className="flex gap-2">
                <span className="mt-2 select-none font-mono text-sm text-primary/70" aria-hidden>
                  ›
                </span>
                <textarea
                  value={requirement}
                  onChange={(e) => setRequirement(e.target.value)}
                  rows={4}
                  placeholder='e.g. "I need 500 solar panels delivered to Jaipur within two weeks."'
                  className="w-full resize-y border border-border/80 bg-background/40 px-3 py-2.5 font-mono text-[13px] text-foreground placeholder:font-sans placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/25"
                  disabled={loading}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                {LEAD_EXAMPLE_REQUIREMENTS.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    disabled={loading}
                    onClick={() => analyze(ex)}
                    className="mm-micro-control border border-border bg-background/30 px-2.5 py-1.5 text-left text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
                  >
                    <span className="mr-1 text-primary/60">›</span>
                    {ex}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => analyze()}
                disabled={loading || !requirement.trim()}
                className={cn(
                  'mm-analyze-btn inline-flex items-center justify-center gap-2 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em]',
                  'bg-primary text-primary-foreground hover:bg-primary/90',
                  'disabled:cursor-not-allowed disabled:opacity-40',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50'
                )}
              >
                {loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Radar className="h-3.5 w-3.5" strokeWidth={1.75} />
                )}
                {loading ? 'Scanning…' : 'Scan opportunities'}
              </button>
            </div>
          </section>

          {/* Empty / ready */}
          {!loading && !result && (
            <section className="mm-empty-ready relative overflow-hidden px-5 py-10 text-center">
              {!reduceMotion && <IntelligenceSignal mode="once" className="top-0" />}
              <div className="type-section-label text-primary">Opportunity radar ready</div>
              <h2 className="mt-2 text-lg font-semibold tracking-tight">
                Paste a buyer enquiry to discover high-value suppliers
              </h2>
              <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground leading-relaxed">
                Supported signals: product, quantity, location, delivery timing, and buyer intent —
                then ranked supplier recommendations with transparent match scores.
              </p>
              <div className="mt-4 type-mono text-[10px] text-muted-foreground/80">
                › SIGNAL DETECTED → REQUIREMENTS UNDERSTOOD → LEADS EVALUATED
              </div>
            </section>
          )}

          {loading && <LeadAnalyzingState requirement={requirement} />}

          {result && (
            <div className="mm-analysis-flow relative space-y-6">
              {/* Completion signal */}
              <motion.div
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.24 }}
                className={cn(
                  'relative overflow-hidden border px-4 py-3 text-sm',
                  result.workflow_status === 'complete'
                    ? 'border-success/30 bg-success/10 text-foreground'
                    : result.workflow_status === 'needs_info'
                      ? 'border-warning/30 bg-warning/10'
                      : 'border-destructive/30 bg-destructive/10'
                )}
              >
                {!reduceMotion && (
                  <IntelligenceSignal
                    mode={result.workflow_status === 'complete' ? 'complete' : 'error'}
                  />
                )}
                <div className="flex items-start gap-2">
                  {result.workflow_status === 'complete' ? (
                    <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  )}
                  <div>
                    <div className="type-section-label text-[10px] text-muted-foreground">
                      Analysis completion
                    </div>
                    <div className="mt-0.5 font-semibold capitalize">
                      Status: {result.workflow_status.replace(/_/g, ' ')}
                    </div>
                    {(result.error || validation?.message) && (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {result.error || validation?.message}
                      </div>
                    )}
                    {validation?.missing_fields?.length ? (
                      <div className="mt-1 text-xs">
                        Missing: {validation.missing_fields.join(', ')}
                      </div>
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                      {result.latency_ms != null && (
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {result.latency_ms < 1000
                            ? `${Math.round(result.latency_ms)} ms`
                            : `${(result.latency_ms / 1000).toFixed(1)} s`}
                        </span>
                      )}
                      {result.run_id && (
                        <span className="font-mono">run {result.run_id.slice(0, 8)}…</span>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>

              {/* Real node executions */}
              {nodes.length > 0 && (
                <section className="space-y-3">
                  <h3 className="type-section-label flex items-center gap-1.5 text-muted-foreground">
                    <Activity className="h-3.5 w-3.5" />
                    System nodes ({nodes.length})
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {nodes.map((n) => (
                      <div
                        key={`${n.execution_order}-${n.node_name}`}
                        className="border border-border/70 bg-background/25 px-2.5 py-1.5 text-[11px]"
                      >
                        <span className="font-medium">
                          {n.execution_order}. {n.node_name}
                        </span>
                        <span className="ml-2 type-mono text-muted-foreground">
                          {Math.round(n.duration_ms)} ms · {n.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Extracted requirement — signals understood */}
              {extracted && (
                <motion.section
                  initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, delay: reduceMotion ? 0 : 0.06 }}
                  className="space-y-3"
                >
                  <div className="type-section-label text-primary">Requirements understood</div>
                  <h3 className="text-sm font-semibold tracking-tight">Buyer requirement analysis</h3>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      { label: 'Product', value: extracted.product_name, icon: Package },
                      { label: 'Category', value: extracted.product_category, icon: Package },
                      {
                        label: 'Quantity',
                        value:
                          extracted.quantity != null
                            ? `${extracted.quantity}${extracted.unit ? ` ${extracted.unit}` : ''}`
                            : null,
                        icon: Package,
                      },
                      {
                        label: 'Location',
                        value: [extracted.city, extracted.state].filter(Boolean).join(', ') || null,
                        icon: MapPin,
                      },
                      { label: 'Intent', value: extracted.buyer_intent, icon: Target },
                      { label: 'Delivery', value: extracted.delivery_time, icon: Clock },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="border border-border/70 bg-background/20 px-3 py-2.5"
                      >
                        <div className="flex items-center gap-1.5 type-meta text-[10px]">
                          <item.icon className="h-3 w-3" strokeWidth={1.75} />
                          {item.label}
                        </div>
                        <div className="mt-1 text-sm font-medium">
                          {item.value || <span className="text-muted-foreground">—</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                  {typeof extracted.confidence_score === 'number' && (
                    <div className="flex items-center gap-3">
                      <span className="type-meta">Extraction confidence</span>
                      <SignalMeter score={extracted.confidence_score} size="sm" />
                    </div>
                  )}
                </motion.section>
              )}

              {/* Product matches */}
              {result.matched_products?.length > 0 && (
                <motion.section
                  initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, delay: reduceMotion ? 0 : 0.1 }}
                  className="space-y-3"
                >
                  <div className="type-section-label text-primary">Market matches</div>
                  <h3 className="text-sm font-semibold tracking-tight">
                    Product matches ({result.matched_products.length})
                  </h3>
                  <div className="overflow-x-auto border border-border/70">
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead className="border-b border-border bg-secondary/40">
                        <tr>
                          <th className="px-3 py-2 type-section-label text-[10px]">Product</th>
                          <th className="px-3 py-2 type-section-label text-[10px]">Category</th>
                          <th className="px-3 py-2 type-section-label text-[10px]">Price</th>
                          <th className="px-3 py-2 type-section-label text-[10px]">Match</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.matched_products.map((p) => (
                          <tr
                            key={p.product_id}
                            className="mm-micro-row border-t border-border/50"
                          >
                            <td className="px-3 py-2.5">
                              <div className="font-medium">{p.name}</div>
                              <div className="text-[10px] text-muted-foreground">{p.match_reason}</div>
                            </td>
                            <td className="px-3 py-2.5 text-muted-foreground">
                              {p.category_name || '—'}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-xs">
                              {p.price != null ? `₹${Number(p.price).toLocaleString()}` : '—'}
                            </td>
                            <td className="px-3 py-2.5">
                              <SignalMeter score={p.match_score} size="sm" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </motion.section>
              )}

              {/* Opportunity signals */}
              {suppliers.length > 0 && (
                <section className="space-y-3">
                  <div className="flex flex-wrap items-end justify-between gap-2">
                    <div>
                      <div className="type-section-label text-primary">
                        High-value opportunities
                      </div>
                      <h3 className="mt-1 text-sm font-semibold tracking-tight">
                        Ranked opportunity signals ({suppliers.length})
                      </h3>
                    </div>
                    {result.ranking_formula && (
                      <div className="max-w-md text-right type-meta text-[10px]">
                        {result.ranking_formula}
                      </div>
                    )}
                  </div>
                  <div className="space-y-2">
                    {suppliers.map((s, i) => (
                      <OpportunitySignal
                        key={s.supplier_id}
                        supplier={s}
                        index={i}
                        prioritized={i === 0}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Feedback — same behavior */}
              {result.run_id && (
                <section className="border border-border/70 bg-background/20 p-4 space-y-3">
                  <h3 className="type-section-label text-muted-foreground">
                    Was this recommendation helpful?
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={feedbackSending || feedbackSent}
                      onClick={() => sendFeedback('helpful')}
                      className={cn(
                        'mm-micro-control inline-flex items-center gap-1.5 border px-3 py-2 text-xs font-medium disabled:opacity-50',
                        feedbackRating === 'helpful'
                          ? 'border-success/40 bg-success/15 text-success'
                          : 'border-border hover:bg-muted'
                      )}
                    >
                      <ThumbsUp className="h-3.5 w-3.5" /> Helpful
                    </button>
                    <button
                      type="button"
                      disabled={feedbackSending || feedbackSent}
                      onClick={() => sendFeedback('not_helpful')}
                      className={cn(
                        'mm-micro-control inline-flex items-center gap-1.5 border px-3 py-2 text-xs font-medium disabled:opacity-50',
                        feedbackRating === 'not_helpful'
                          ? 'border-destructive/40 bg-destructive/15 text-destructive'
                          : 'border-border hover:bg-muted'
                      )}
                    >
                      <ThumbsDown className="h-3.5 w-3.5" /> Not Helpful
                    </button>
                  </div>
                  {!feedbackSent && (
                    <textarea
                      value={feedbackComment}
                      onChange={(e) => setFeedbackComment(e.target.value)}
                      rows={2}
                      placeholder="Optional comment…"
                      disabled={feedbackSending}
                      className="w-full resize-y border border-border bg-background/40 px-3 py-2 text-xs placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                  )}
                  {feedbackSent && (
                    <p className="text-[11px] text-muted-foreground">Thanks — your feedback was saved.</p>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LeadIntelligence;
