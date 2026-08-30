import React, { useRef, useEffect, useState } from 'react';
import { AppSidebar } from '@/components/layout/AppSidebar';
import { RightSidebar } from '@/components/layout/RightSidebar';
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
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Toast portal */}
      <Toaster />

      {/* Left Sidebar */}
      <AppSidebar {...sidebarProps} />

      {/* Re-open tab when sidebar is collapsed */}
      {isLeftSidebarCollapsed && (
        <button
          onClick={onToggleLeftSidebar}
          className="fixed left-0 top-1/2 z-30 -translate-y-1/2 grid h-10 w-6 place-items-center rounded-r-lg border border-l-0 border-border bg-sidebar/80 text-muted-foreground hover:bg-sidebar hover:text-foreground transition-colors"
          aria-label="Open sidebar"
        >
          <PanelLeftOpen className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Main content */}
      <main className="flex min-w-0 flex-1 flex-col h-screen overflow-hidden relative">

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
          <>
            {/* Top bar */}
            {hasDataset && (
              <div className="shrink-0 sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-6 py-3 backdrop-blur-xl">
                <div className="min-w-0">
                  <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    {datasetName || 'dataset.csv'} · {rowCount.toLocaleString()} rows
                  </div>
                  <h1 className="truncate text-sm font-semibold sm:text-base">
                    {chatHistory.some(m => m.role === 'assistant')
                      ? chatHistory.filter(m => m.role === 'assistant').slice(-1)[0]?.report?.title || 'Data Analysis'
                      : 'Ready for questions'}
                  </h1>
                </div>
                <div className="hidden items-center gap-2 sm:flex">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 px-2.5 py-1 text-[11px] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" /> Live
                  </span>
                  {latestModel && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
                      <Sparkles className="h-3 w-3" /> {latestModel}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Chat / Upload area */}
            <div className="scrollbar-thin flex-1 overflow-y-auto">
              {!hasDataset ? (
                /* Upload / demo state */
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
                /* Chat feed */
                <div className="mx-auto w-full max-w-4xl px-4 pt-6 pb-48">
                  {/* Empty state with sample questions */}
                  {chatHistory.length === 0 && !isAnalyzing && (
                    <div className="flex flex-col items-center justify-center py-12 px-6 space-y-6 max-w-2xl mx-auto text-center">
                      <div className="rounded-full bg-primary/10 p-4 border border-primary/20">
                        <Sparkles className="h-8 w-8 text-primary" />
                      </div>
                      <div className="space-y-2">
                        <h3 className="text-lg font-semibold tracking-tight text-foreground">
                          Explore marketplace intelligence
                        </h3>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {tables && tables.length > 1
                            ? `Demo loaded with ${tables.length} tables · ${rowCount.toLocaleString()} total rows. Try a sample question:`
                            : 'Ask questions to discover insights in your dataset. Try a sample:'}
                        </p>
                      </div>
                      <div className="grid w-full gap-2 sm:grid-cols-2 text-left">
                        {MARKETPLACE_SAMPLE_QUESTIONS.map((q) => (
                          <button
                            key={q}
                            type="button"
                            onClick={() => handleSubmitQuestion(q)}
                            disabled={isAnalyzing}
                            className="rounded-xl border border-border bg-card/50 px-3.5 py-3 text-left text-xs leading-relaxed text-foreground/90 transition-colors hover:border-primary/40 hover:bg-primary/5 disabled:opacity-50"
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Messages */}
                  <div className="space-y-10">
                    {chatHistory.map((msg, i) => (
                      <div key={i} className="animate-fade-in">
                        {msg.role === 'user' && <UserMessage text={msg.content || ''} />}
                        {msg.role === 'assistant' && msg.report && (
                          <div className="mt-6">
                            <Report payload={{ report: msg.report, debug: msg.debug }} />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Analyzing state */}
                  {isAnalyzing && (
                    <div className="mt-8 space-y-6 animate-fade-in">
                      {question && <UserMessage text={question} />}
                      <div className="flex items-center gap-4 glass-card rounded-2xl p-5 text-muted-foreground shadow-sm border border-border/50 hover:shadow-md transition-all duration-300">
                        <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/10 text-purple-500">
                          <Loader2 className="h-5 w-5 animate-spin" />
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-foreground">Agent is analyzing...</div>
                          <div className="text-xs text-muted-foreground mt-0.5 animate-pulse">
                            {sidebarTrace.find(t => t.status === "running")?.step 
                              ? (sidebarTrace.find(t => t.status === "running")?.step === "Understanding dataset" ? "Understanding your dataset..." :
                                 sidebarTrace.find(t => t.status === "running")?.step === "Planning analysis" ? "Planning the analysis..." :
                                 sidebarTrace.find(t => t.status === "running")?.step === "Generating" ? "Generating..." :
                                 sidebarTrace.find(t => t.status === "running")?.step === "Executing query" ? "Executing query..." :
                                 sidebarTrace.find(t => t.status === "running")?.step === "Validating results" ? "Validating results..." :
                                 sidebarTrace.find(t => t.status === "running")?.step === "Generating report" ? "Preparing report..." : "Analyzing...")
                              : "Preparing analysis..."}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            {/* Composer */}
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
          </>
        )}
      </main>

      {/* Right sidebar (workspace only) */}
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
  );
};
