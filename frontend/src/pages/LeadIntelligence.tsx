import React, { useState } from 'react';
import {
  Sparkles,
  Loader2,
  Target,
  Package,
  MapPin,
  Clock,
  BadgeCheck,
  AlertTriangle,
  Star,
  ThumbsUp,
  ThumbsDown,
  Activity,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import type { LeadAnalyzeResponse } from '@/types/lead';
import { LEAD_EXAMPLE_REQUIREMENTS } from '@/types/lead';
import { submitWorkflowFeedback } from '@/services/observability';
import { API_BASE } from '@/lib/api';
import { cn } from '@/lib/utils';

interface LeadIntelligenceProps {
  sessionId?: string | null;
  onSessionCreated?: (sessionId: string) => void;
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

  return (
    <div className="flex h-full w-full flex-col bg-background text-foreground">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/70 px-6 py-3 backdrop-blur-xl">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            MarketMind AI
          </div>
          <h1 className="text-sm font-semibold sm:text-base flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            Lead Intelligence
          </h1>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
          <Sparkles className="h-3 w-3" /> Requirement → Suppliers
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl space-y-6 px-6 py-8">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Buyer requirement
            </div>
            <h2 className="mt-1 text-2xl font-bold tracking-tight">
              Match buyers to the right suppliers
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Paste an unstructured B2B enquiry. MarketMind extracts the requirement, finds
              matching products, and ranks suppliers with a transparent score.
            </p>
          </div>

          <div className="glass-card rounded-2xl border border-border p-4 space-y-4">
            <textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              rows={4}
              placeholder='e.g. "I need 500 solar panels delivered to Jaipur within two weeks."'
              className="w-full resize-y rounded-xl border border-border bg-background/60 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
              disabled={loading}
            />
            <div className="flex flex-wrap gap-2">
              {LEAD_EXAMPLE_REQUIREMENTS.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  disabled={loading}
                  onClick={() => analyze(ex)}
                  className="rounded-lg border border-border bg-secondary/40 px-2.5 py-1.5 text-left text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => analyze()}
              disabled={loading || !requirement.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-[image:var(--gradient-primary)] px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-[var(--shadow-glow)] transition-transform hover:scale-[1.01] active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Target className="h-4 w-4" />}
              {loading ? 'Analyzing requirement…' : 'Analyze Requirement'}
            </button>
          </div>

          {result && (
            <div className="space-y-6 animate-fade-in">
              {/* Status banner */}
              <div
                className={cn(
                  'rounded-xl border px-4 py-3 text-sm',
                  result.workflow_status === 'complete'
                    ? 'border-success/30 bg-success/10 text-foreground'
                    : result.workflow_status === 'needs_info'
                      ? 'border-amber-500/30 bg-amber-500/10'
                      : 'border-destructive/30 bg-destructive/10'
                )}
              >
                <div className="flex items-start gap-2">
                  {result.workflow_status === 'complete' ? (
                    <BadgeCheck className="mt-0.5 h-4 w-4 text-success shrink-0" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500 shrink-0" />
                  )}
                  <div>
                    <div className="font-semibold capitalize">
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
              </div>

              {/* Nodes executed */}
              {nodes.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5" />
                    Nodes Executed ({nodes.length})
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {nodes.map((n) => (
                      <div
                        key={`${n.execution_order}-${n.node_name}`}
                        className="rounded-lg border border-border bg-card/40 px-2.5 py-1.5 text-[11px]"
                      >
                        <span className="font-medium">{n.execution_order}. {n.node_name}</span>
                        <span className="ml-2 text-muted-foreground">
                          {Math.round(n.duration_ms)} ms · {n.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Extracted requirement */}
              {extracted && (
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Buyer Requirement Analysis
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
                        className="rounded-xl border border-border bg-card/40 px-3.5 py-3"
                      >
                        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                          <item.icon className="h-3 w-3" />
                          {item.label}
                        </div>
                        <div className="mt-1 text-sm font-medium">
                          {item.value || <span className="text-muted-foreground">—</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                  {typeof extracted.confidence_score === 'number' && (
                    <div className="text-[11px] text-muted-foreground">
                      Extraction confidence: {(extracted.confidence_score * 100).toFixed(0)}%
                    </div>
                  )}
                </section>
              )}

              {/* Product matches */}
              {result.matched_products?.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Product Matches ({result.matched_products.length})
                  </h3>
                  <div className="overflow-hidden rounded-xl border border-border">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-secondary/50 text-[11px] uppercase tracking-wider text-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 font-medium">Product</th>
                          <th className="px-3 py-2 font-medium">Category</th>
                          <th className="px-3 py-2 font-medium">Price</th>
                          <th className="px-3 py-2 font-medium">Match</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.matched_products.map((p) => (
                          <tr key={p.product_id} className="border-t border-border/60">
                            <td className="px-3 py-2.5">
                              <div className="font-medium">{p.name}</div>
                              <div className="text-[10px] text-muted-foreground">{p.match_reason}</div>
                            </td>
                            <td className="px-3 py-2.5 text-muted-foreground">
                              {p.category_name || '—'}
                            </td>
                            <td className="px-3 py-2.5">
                              {p.price != null ? `₹${Number(p.price).toLocaleString()}` : '—'}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-xs">
                              {(p.match_score * 100).toFixed(0)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* Recommended suppliers */}
              {result.recommended_suppliers?.length > 0 && (
                <section className="space-y-3">
                  <div className="flex items-end justify-between gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Recommended Suppliers ({result.recommended_suppliers.length})
                    </h3>
                    {result.ranking_formula && (
                      <div className="max-w-md text-right text-[10px] text-muted-foreground">
                        {result.ranking_formula}
                      </div>
                    )}
                  </div>
                  <div className="space-y-3">
                    {result.recommended_suppliers.map((s) => (
                      <div
                        key={s.supplier_id}
                        className="rounded-xl border border-border bg-card/40 p-4 transition-colors hover:border-primary/30"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary/15 text-xs font-bold text-primary">
                                #{s.rank}
                              </span>
                              <h4 className="truncate text-sm font-semibold">{s.name}</h4>
                              {s.verified && (
                                <span className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
                                  <BadgeCheck className="h-3 w-3" /> Verified
                                </span>
                              )}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                              <span className="inline-flex items-center gap-1">
                                <MapPin className="h-3 w-3" />
                                {[s.city, s.state].filter(Boolean).join(', ') || '—'}
                              </span>
                              <span className="inline-flex items-center gap-1">
                                <Star className="h-3 w-3 text-amber-400" />
                                {s.rating != null ? s.rating.toFixed(1) : '—'}
                              </span>
                              <span className="inline-flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {s.response_time_hours != null
                                  ? `${s.response_time_hours}h response`
                                  : 'Response N/A'}
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
                              {s.explanation}
                            </p>
                            {s.matching_products?.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {s.matching_products.slice(0, 4).map((name) => (
                                  <span
                                    key={name}
                                    className="rounded-md border border-border bg-background/50 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                  >
                                    {name}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                              Match score
                            </div>
                            <div className="text-xl font-bold text-primary">
                              {(s.final_score * 100).toFixed(0)}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* User feedback */}
              {result.run_id && (
                <section className="rounded-xl border border-border bg-card/40 p-4 space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Was this recommendation helpful?
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={feedbackSending || feedbackSent}
                      onClick={() => sendFeedback('helpful')}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50',
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
                        'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50',
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
                      className="w-full resize-y rounded-lg border border-border bg-background/60 px-3 py-2 text-xs placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
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
