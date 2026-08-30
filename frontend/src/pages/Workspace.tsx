import React, { useRef, useEffect, useState } from 'react';
import { AppSidebar } from '@/components/layout/AppSidebar';
import { RightSidebar } from '@/components/layout/RightSidebar';
import { AppHeader } from '@/components/layout/AppHeader';
import { ContentViewport } from '@/components/layout/ContentViewport';
import { deriveSystemStatus } from '@/components/layout/SystemStatus';
import { AnalysisPipeline } from '@/components/analysis/AnalysisPipeline';
import { Report } from '@/components/report/Report';
import { UserMessage } from '@/components/chat/UserMessage';
import { ChatComposer } from '@/components/chat/ChatComposer';
import { Toaster } from '@/components/ui/Toaster';
import { Sparkles, Loader2, PanelLeftOpen, Store } from 'lucide-react';
import { UploadZone } from '@/components/ui/UploadZone';
import { Analytics } from './Analytics';
import { LeadIntelligence } from './LeadIntelligence';
import { AgentMonitoring } from './AgentMonitoring';
import { MARKETPLACE_SAMPLE_QUESTIONS } from '@/lib/marketplace';
import type { ChatMessage } from '@/types/index';

interface WorkspaceProps {
  session: any;
  hasDataset: boolean;
  datasetName?: string;
  rowCount: number;
  columns: any[];
  tables?: string[];
  isUploading: boolean;
  isLoadingDemo?: boolean;
  uploadError: string | null;
  handleFileUpload: (file: File) => void;
  onLoadMarketplaceDemo?: () => void;
  onUploadClick: () => void;
  history: any[];
  onSelectHistory: (id: string) => void;
  selectedHistoryId?: string;
  isLeftSidebarCollapsed: boolean;
  onToggleLeftSidebar: () => void;
  isRightSidebarCollapsed: boolean;
  onToggleRightSidebar: () => void;
  sidebarTrace: any[];
  sessionQueries: any[];
  latestAssistantMsg: any;
  latestRowCount: number | undefined;
  chatHistory: ChatMessage[];
  question: string;
  isAnalyzing: boolean;
  setQuestion: (q: string) => void;
  handleAnalyze: (e: React.FormEvent, q?: string) => void;
  activeTab: 'analysis' | 'metrics';
  setActiveTab: (tab: 'analysis' | 'metrics') => void;
  isDark: boolean;
  onThemeToggle: () => void;
}

export const Workspace: React.FC<WorkspaceProps> = ({
  session, hasDataset, datasetName, rowCount, columns, tables,
  isUploading, isLoadingDemo, uploadError, handleFileUpload, onLoadMarketplaceDemo, onUploadClick,
  history, onSelectHistory, selectedHistoryId,
  isLeftSidebarCollapsed, onToggleLeftSidebar,
  isRightSidebarCollapsed, onToggleRightSidebar,
  sidebarTrace, sessionQueries, latestAssistantMsg,
  chatHistory, question, isAnalyzing, setQuestion, handleAnalyze,
  activeTab, setActiveTab,
  isDark: _isDark,
  onThemeToggle: _onThemeToggle,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [activePath, setActivePath] = useState('/');

  // Sync activePath ↔ activeTab (analytics only; lead is independent)
  useEffect(() => {
    if (activeTab === 'metrics' && activePath !== '/analytics') setActivePath('/analytics');
    if (activeTab === 'analysis' && activePath === '/analytics') setActivePath('/');
  }, [activeTab]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (chatHistory.length > 0 || isAnalyzing) {
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [chatHistory, isAnalyzing]);

  const handleSetActivePath = (path: string) => {
    setActivePath(path);
    if (path === '/analytics') setActiveTab('metrics');
    else if (path === '/' || path === '/lead' || path === '/monitoring') setActiveTab('analysis');
  };

  const handleSubmitQuestion = (text: string) => {
    setQuestion(text);
    setTimeout(() => {
      handleAnalyze({ preventDefault: () => {} } as React.FormEvent, text);
    }, 0);
  };

  const latestModel = latestAssistantMsg?.model;
  const latestProvider = latestAssistantMsg?.provider;
  const statusKind = deriveSystemStatus({ isAnalyzing, hasDataset });

  const lastAssistant = [...chatHistory].reverse().find((m) => m.role === 'assistant' && m.report);
  const analysisPhase: 'loaded' | 'ready' | 'running' | 'complete' | 'error' = (() => {
    if (isAnalyzing) return 'running';
    if (lastAssistant?.report?.report_type === 'FAILURE' || lastAssistant?.success === false) return 'error';
    if (lastAssistant?.report) return 'complete';
    if (hasDataset && chatHistory.length === 0) return 'ready';
    return hasDataset ? 'loaded' : 'loaded';
  })();

  const sidebarProps = {
    hasDataset,
    datasetName,
    rowCount,
    columns,
    tables,
    history,
    onUpload: onUploadClick,
    onSelectHistory,
    selectedHistoryId,
    activePath,
    setActivePath: handleSetActivePath,
    isCollapsed: isLeftSidebarCollapsed,
    onToggleCollapse: onToggleLeftSidebar,
    isAnalyzing,
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-transparent text-foreground">
      <Toaster />

      <AppSidebar {...sidebarProps} />

      {isLeftSidebarCollapsed && (
        <button
          onClick={onToggleLeftSidebar}
          className="fixed left-0 top-1/2 z-30 -translate-y-1/2 grid h-10 w-6 place-items-center rounded-r-md border border-l-0 border-border bg-sidebar/85 text-muted-foreground hover:bg-sidebar hover:text-foreground transition-colors"
          aria-label="Open sidebar"
        >
          <PanelLeftOpen className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Main command column */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <AppHeader
          activePath={activePath}
          statusKind={statusKind}
          datasetName={datasetName}
          rowCount={rowCount}
          hasDataset={hasDataset}
          model={latestModel}
        />

        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
          <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-transparent">
            <ContentViewport moduleKey={activePath}>
              {/* ── Analytics ── */}
              {activePath === '/analytics' && (
                <div className="flex-1 overflow-y-auto">
                  <Analytics sessionQueries={sessionQueries} sessionId={session?.session_id} />
                </div>
              )}

              {/* ── Lead Intelligence ── */}
              {activePath === '/lead' && (
                <div className="flex-1 overflow-hidden">
                  <LeadIntelligence sessionId={session?.session_id} />
                </div>
              )}

              {/* ── Agent Monitoring ── */}
              {activePath === '/monitoring' && (
                <div className="flex-1 overflow-hidden">
                  <AgentMonitoring />
                </div>
              )}

              {/* ── Workspace / Chat ── */}
              {activePath === '/' && (
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-mm-phase={analysisPhase}>
                  {/* Context strip — real session/report state only */}
                  {hasDataset && (
                    <div className="shrink-0 flex items-center justify-between gap-3 border-b border-border/50 px-4 py-2 sm:px-6">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium tracking-tight text-foreground">
                          {chatHistory.some(m => m.role === 'assistant')
                            ? chatHistory.filter(m => m.role === 'assistant').slice(-1)[0]?.report?.title || 'Data Analysis'
                            : 'Ready for questions'}
                        </p>
                      </div>
                      <span className="hidden type-mono text-[10px] text-muted-foreground sm:inline">
                        {analysisPhase === 'running' && 'ANALYSIS RUNNING'}
                        {analysisPhase === 'complete' && 'ANALYSIS COMPLETE'}
                        {analysisPhase === 'error' && 'NO RESULT'}
                        {analysisPhase === 'ready' && 'QUESTION READY'}
                        {analysisPhase === 'loaded' && 'DATASET LOADED'}
                      </span>
                    </div>
                  )}

                  <div className="scrollbar-thin flex-1 overflow-y-auto">
                    {!hasDataset ? (
                      <div className="flex h-full min-h-[calc(100vh-4rem)] flex-col items-center justify-center p-8">
                        <div className="max-w-[580px] w-full space-y-8 animate-fade-in">
                          <div className="text-center space-y-3">
                            <div className="mx-auto w-16 h-16 grid place-items-center rounded-2xl bg-[image:var(--gradient-primary)] shadow-[var(--shadow-glow)] mb-4">
                              <Sparkles className="h-8 w-8 text-primary-foreground" />
                            </div>
                            <h1 className="text-3xl font-bold tracking-tight">MarketMind AI</h1>
                            <p className="text-sm font-medium text-primary">
                              Agentic B2B Marketplace Intelligence Platform
                            </p>
                            <p className="text-base text-muted-foreground max-w-md mx-auto leading-relaxed">
                              Load the marketplace demo or upload a CSV. Ask about buyers, suppliers, products, leads, and orders in plain English.
                            </p>
                          </div>

                          {onLoadMarketplaceDemo && (
                            <button
                              type="button"
                              onClick={onLoadMarketplaceDemo}
                              disabled={isUploading || isLoadingDemo}
                              className="group flex w-full items-center justify-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-4 py-3.5 text-sm font-semibold text-primary transition-all hover:bg-primary hover:text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {isLoadingDemo ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Store className="h-4 w-4" />
                              )}
                              {isLoadingDemo ? 'Loading marketplace demo…' : 'Load Marketplace Demo'}
                            </button>
                          )}

                          <div className="relative flex items-center gap-3 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <div className="h-px flex-1 bg-border" />
                            <span>or upload your CSV</span>
                            <div className="h-px flex-1 bg-border" />
                          </div>

                          <UploadZone
                            onFileSelect={handleFileUpload}
                            loading={isUploading}
                            accept=".csv"
                            disabled={isLoadingDemo}
                          />
                          {uploadError && (
                            <div className="text-sm font-medium text-destructive bg-destructive/10 border border-destructive/20 rounded-xl p-4 text-center">
                              {uploadError}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="mx-auto w-full max-w-4xl px-4 pt-6 pb-48">
                        {chatHistory.length === 0 && !isAnalyzing && (
                          <div className="mm-empty-ready relative mx-auto max-w-2xl overflow-hidden px-6 py-10 text-center">
                            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/35 to-transparent" aria-hidden />
                            <div className="type-section-label text-primary">Intelligence system ready</div>
                            <h3 className="mt-3 text-lg font-semibold tracking-tight text-foreground">
                              Dataset loaded — awaiting command
                            </h3>
                            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                              {tables && tables.length > 1
                                ? `Demo loaded with ${tables.length} tables · ${rowCount.toLocaleString()} total rows. Enter a query below or try a sample:`
                                : 'Ask questions to discover insights in your dataset. Try a sample:'}
                            </p>
                            <div className="mt-2 type-mono text-[10px] text-muted-foreground/80">
                              › QUERY // QUESTION READY
                            </div>
                            <div className="mt-6 grid w-full gap-2 sm:grid-cols-2 text-left">
                              {MARKETPLACE_SAMPLE_QUESTIONS.map((q) => (
                                <button
                                  key={q}
                                  type="button"
                                  onClick={() => handleSubmitQuestion(q)}
                                  disabled={isAnalyzing}
                                  className="mm-micro-control border border-border bg-background/30 px-3.5 py-3 text-left text-xs leading-relaxed text-foreground/90 hover:bg-primary/5 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
                                >
                                  <span className="mr-1.5 text-primary/70">›</span>
                                  {q}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="space-y-10">
                          {chatHistory.map((msg, i) => (
                            <div key={i} className="animate-fade-in">
                              {msg.role === 'user' && <UserMessage text={msg.content || ''} />}
                              {msg.role === 'assistant' && msg.report && (
                                <div className="mt-6">
                                  <Report
                                    payload={{
                                      report: msg.report,
                                      debug: msg.debug,
                                      model: msg.model,
                                      provider: msg.provider,
                                    }}
                                  />
                                </div>
                              )}
                            </div>
                          ))}
                        </div>

                        {isAnalyzing && (
                          <div className="mt-8 space-y-6 animate-fade-in">
                            {question && <UserMessage text={question} />}
                            <AnalysisPipeline
                              trace={sidebarTrace}
                              isAnalyzing={isAnalyzing}
                              activeStatus={latestAssistantMsg?.success}
                              question={question}
                            />
                          </div>
                        )}
                        <div ref={bottomRef} />
                      </div>
                    )}
                  </div>

                  {hasDataset && (
                    <div className="shrink-0 sticky bottom-0 z-20 border-t border-border bg-background/80 px-4 py-3 backdrop-blur-xl sm:px-6">
                      <div className="mx-auto max-w-4xl">
                        <ChatComposer
                          onSubmit={handleSubmitQuestion}
                          disabled={isAnalyzing}
                          model={latestModel}
                        />
                        <div className="mt-2 text-center text-[10px] text-muted-foreground">
                          MarketMind AI can make mistakes. Always verify critical decisions.
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </ContentViewport>
          </main>

          {hasDataset && activePath === '/' && (
            <RightSidebar
              trace={sidebarTrace}
              activeExecutionTime={latestAssistantMsg?.executionTime}
              activeRetryCount={latestAssistantMsg?.retryCount}
              activeModel={latestModel}
              activeProvider={latestProvider}
              activeStatus={latestAssistantMsg?.success}
              isCollapsed={isRightSidebarCollapsed}
              onToggleCollapse={onToggleRightSidebar}
              isAnalyzing={isAnalyzing}
              latestReport={latestAssistantMsg?.report}
            />
          )}
        </div>
      </div>
    </div>
  );
};
