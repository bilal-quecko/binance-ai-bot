import { useCallback, useEffect, useMemo, useState } from 'react';

import { AIEvaluationCard } from './components/AIEvaluationCard';
import { AIHistorySection } from './components/AIHistorySection';
import { AutoRefreshSelector } from './components/AutoRefreshSelector';
import { BotControlPanel } from './components/BotControlPanel';
import { DataStateIndicator } from './components/DataStateIndicator';
import { MetricCard } from './components/MetricCard';
import { PerformanceAnalyticsSection } from './components/PerformanceAnalyticsSection';
import { SectionCard } from './components/SectionCard';
import { StatePanel } from './components/StatePanel';
import {
  getAISignalEvaluation,
  getAISignal,
  getAISignalHistory,
  getBotStatus,
  getHealth,
  getPerformanceAnalytics,
  getSymbols,
  getWorkstation,
  pauseBot,
  resetBotSession,
  resumeBot,
  startBot,
  stopBot,
} from './lib/api';
import { badgeTone, classNames, formatCurrency, formatDateTime, formatDecimal, pnlTone } from './lib/format';
import type {
  AIOutcomeEvaluationResponse,
  AISignalHistoryResponse,
  AISignalSummary,
  AutoRefreshIntervalSeconds,
  BotStatusResponse,
  HealthResponse,
  PerformanceAnalyticsResponse,
  SpotSymbolItem,
  WorkstationResponse,
} from './lib/types';

interface RemoteState<T> {
  data: T;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

type WorkstationTab = 'signal' | 'auto-trade';

const INITIAL_BOT_STATUS: BotStatusResponse = {
  state: 'stopped',
  symbol: null,
  timeframe: '1m',
  paper_only: true,
  started_at: null,
  last_event_time: null,
  last_error: null,
};

const INITIAL_WORKSTATION: WorkstationResponse | null = null;
const INITIAL_AI_SIGNAL: AISignalSummary | null = null;
const INITIAL_AI_HISTORY: AISignalHistoryResponse = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  data_state: 'waiting_for_runtime',
  status_message: 'Start the live runtime for the selected symbol to generate advisory history.',
};
const INITIAL_AI_EVALUATION: AIOutcomeEvaluationResponse | null = null;
const INITIAL_PERFORMANCE: PerformanceAnalyticsResponse | null = null;

function createRemoteState<T>(data: T): RemoteState<T> {
  return {
    data,
    loading: true,
    refreshing: false,
    error: null,
  };
}

function setPending<T>(current: RemoteState<T>): RemoteState<T> {
  if (current.loading) {
    return current;
  }
  if (current.data === null) {
    return { ...current, loading: true, error: null };
  }
  return { ...current, refreshing: true, error: null };
}

function describeSignal(side: string | null | undefined): string {
  if (side === 'BUY') {
    return 'Entry setup is active';
  }
  if (side === 'SELL') {
    return 'Exit condition is active';
  }
  return 'No active action';
}

function App() {
  const [tab, setTab] = useState<WorkstationTab>('signal');
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState<AutoRefreshIntervalSeconds>(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const [health, setHealth] = useState<RemoteState<HealthResponse | null>>(createRemoteState<HealthResponse | null>(null));
  const [botStatus, setBotStatus] = useState<RemoteState<BotStatusResponse>>(createRemoteState(INITIAL_BOT_STATUS));
  const [workstation, setWorkstation] = useState<RemoteState<WorkstationResponse | null>>(createRemoteState(INITIAL_WORKSTATION));
  const [aiSignal, setAiSignal] = useState<RemoteState<AISignalSummary | null>>(createRemoteState(INITIAL_AI_SIGNAL));
  const [aiHistory, setAiHistory] = useState<RemoteState<AISignalHistoryResponse>>(createRemoteState(INITIAL_AI_HISTORY));
  const [aiEvaluation, setAiEvaluation] = useState<RemoteState<AIOutcomeEvaluationResponse | null>>(createRemoteState(INITIAL_AI_EVALUATION));
  const [performanceAnalytics, setPerformanceAnalytics] = useState<RemoteState<PerformanceAnalyticsResponse | null>>(createRemoteState(INITIAL_PERFORMANCE));
  const [symbolResults, setSymbolResults] = useState<RemoteState<SpotSymbolItem[]>>(createRemoteState<SpotSymbolItem[]>([]));

  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [symbolSearch, setSymbolSearch] = useState('');
  const [botActionLoading, setBotActionLoading] = useState(false);
  const [botActionError, setBotActionError] = useState<string | null>(null);

  const loadSymbols = useCallback(async (query: string) => {
    setSymbolResults((current) => ({ ...current, loading: current.data.length === 0, refreshing: current.data.length > 0, error: null }));
    try {
      const symbols = await getSymbols(query, 10);
      setSymbolResults({ data: symbols, loading: false, refreshing: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load tradable Spot symbols.';
      setSymbolResults((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const refreshWorkspace = useCallback(async (symbol: string) => {
    setHealth((current) => setPending(current));
    setBotStatus((current) => setPending(current));
    if (symbol.trim().length > 0) {
      setWorkstation((current) => setPending(current));
      setAiSignal((current) => setPending(current));
      setAiHistory((current) => setPending(current));
      setAiEvaluation((current) => setPending(current));
      setPerformanceAnalytics((current) => setPending(current));
    } else {
      setWorkstation({ data: null, loading: false, refreshing: false, error: null });
      setAiSignal({ data: null, loading: false, refreshing: false, error: null });
      setAiHistory({ data: INITIAL_AI_HISTORY, loading: false, refreshing: false, error: null });
      setAiEvaluation({ data: null, loading: false, refreshing: false, error: null });
      setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
    }

    try {
      const [healthData, botStatusData, workstationData, aiSignalData, aiHistoryData, aiEvaluationData, performanceData] = await Promise.all([
        getHealth(),
        getBotStatus(),
        symbol.trim().length > 0 ? getWorkstation(symbol) : Promise.resolve<WorkstationResponse | null>(null),
        symbol.trim().length > 0 ? getAISignal(symbol) : Promise.resolve<AISignalSummary | null>(null),
        symbol.trim().length > 0
          ? getAISignalHistory(symbol, { limit: INITIAL_AI_HISTORY.limit, offset: 0 })
          : Promise.resolve<AISignalHistoryResponse>(INITIAL_AI_HISTORY),
        symbol.trim().length > 0 ? getAISignalEvaluation(symbol) : Promise.resolve<AIOutcomeEvaluationResponse | null>(null),
        symbol.trim().length > 0 ? getPerformanceAnalytics(symbol) : Promise.resolve<PerformanceAnalyticsResponse | null>(null),
      ]);
      setHealth({ data: healthData, loading: false, refreshing: false, error: null });
      setBotStatus({ data: botStatusData, loading: false, refreshing: false, error: null });
      setWorkstation({ data: workstationData, loading: false, refreshing: false, error: null });
      setAiSignal({ data: aiSignalData, loading: false, refreshing: false, error: null });
      setAiHistory({ data: aiHistoryData, loading: false, refreshing: false, error: null });
      setAiEvaluation({ data: aiEvaluationData, loading: false, refreshing: false, error: null });
      setPerformanceAnalytics({ data: performanceData, loading: false, refreshing: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh workstation state.';
      setHealth((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      setBotStatus((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      if (symbol.trim().length > 0) {
        setWorkstation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiSignal((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiHistory((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiEvaluation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setPerformanceAnalytics((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      }
    }
  }, []);

  useEffect(() => {
    void loadSymbols(symbolSearch);
  }, [loadSymbols, symbolSearch]);

  useEffect(() => {
    void refreshWorkspace(selectedSymbol);
  }, [refreshWorkspace, selectedSymbol]);

  useEffect(() => {
    if (autoRefreshSeconds === 0 || selectedSymbol.trim().length === 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refreshWorkspace(selectedSymbol);
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshSeconds, refreshWorkspace, selectedSymbol]);

  const handleSymbolSearchChange = useCallback((value: string) => {
    setSymbolSearch(value);
    if (value.trim().toUpperCase() !== selectedSymbol) {
      setSelectedSymbol('');
    }
    setBotActionError(null);
  }, [selectedSymbol]);

  const handleSelectSymbol = useCallback((symbol: string) => {
    setSelectedSymbol(symbol);
    setSymbolSearch(symbol);
    setBotActionError(null);
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedSymbol('');
    setSymbolSearch('');
    setBotActionError(null);
    setWorkstation({ data: null, loading: false, refreshing: false, error: null });
    setAiSignal({ data: null, loading: false, refreshing: false, error: null });
    setAiHistory({ data: INITIAL_AI_HISTORY, loading: false, refreshing: false, error: null });
    setAiEvaluation({ data: null, loading: false, refreshing: false, error: null });
    setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
  }, []);

  const runBotAction = useCallback(async (action: () => Promise<BotStatusResponse>) => {
    setBotActionLoading(true);
    setBotActionError(null);
    try {
      const nextStatus = await action();
      setBotStatus({ data: nextStatus, loading: false, refreshing: false, error: null });
      if (nextStatus.symbol) {
        setSelectedSymbol(nextStatus.symbol);
        setSymbolSearch(nextStatus.symbol);
      }
      await refreshWorkspace(nextStatus.symbol ?? selectedSymbol);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to update the paper bot.';
      setBotActionError(message);
    } finally {
      setBotActionLoading(false);
    }
  }, [refreshWorkspace, selectedSymbol]);

  const handleResetSession = useCallback(async () => {
    setBotActionLoading(true);
    setBotActionError(null);
    try {
      const nextStatus = await resetBotSession();
      setBotStatus({ data: nextStatus, loading: false, refreshing: false, error: null });
      setWorkstation({ data: null, loading: false, refreshing: false, error: null });
      setAiSignal({ data: null, loading: false, refreshing: false, error: null });
      setAiHistory({ data: INITIAL_AI_HISTORY, loading: false, refreshing: false, error: null });
      setAiEvaluation({ data: null, loading: false, refreshing: false, error: null });
      setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to reset the paper session.';
      setBotActionError(message);
    } finally {
      setBotActionLoading(false);
    }
  }, []);

  const effectiveWorkstation = useMemo(() => {
    if (workstation.data?.symbol === selectedSymbol) {
      return workstation.data;
    }
    return null;
  }, [selectedSymbol, workstation.data]);
  const effectiveAiSignal = useMemo(() => {
    if (aiSignal.data?.symbol === selectedSymbol) {
      return aiSignal.data;
    }
    return null;
  }, [aiSignal.data, selectedSymbol]);

  const trendLabel = effectiveWorkstation?.trend_bias ?? 'Waiting for live data';
  const workstationDataState = effectiveWorkstation?.data_state ?? 'waiting_for_runtime';
  const workstationStatusMessage = effectiveWorkstation?.status_message ?? (selectedSymbol ? `Start or attach the live runtime for ${selectedSymbol} to populate symbol-scoped workstation data.` : 'Select one symbol to populate the workstation.');
  const signalExplanation = effectiveWorkstation?.explanation ?? 'Select a symbol, then start or pause the live paper runtime to populate live signal state.';
  const refreshLabel = autoRefreshSeconds === 0 ? 'Off' : `${autoRefreshSeconds}s`;

  return (
    <div className="min-h-screen bg-transparent text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <header className="rounded-3xl border border-slate-800/80 bg-slate-950/70 p-6 shadow-glow backdrop-blur">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-sky-300">Binance AI Bot</p>
              <h1 className="mt-2 text-3xl font-semibold text-white">Single-Symbol Paper Trading Workstation</h1>
              <p className="mt-3 max-w-3xl text-sm text-slate-400">
                Use one live Binance Spot symbol at a time. Signal mode shows the current market state and strategy bias. Auto Trade mode controls the paper runtime and current paper position.
              </p>
            </div>
            <div className="grid gap-3 text-sm text-slate-400 sm:justify-items-end">
              <div className="flex items-center gap-2">
                <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(health.data?.status ?? 'unknown'))}>
                  {health.data?.status ?? 'loading'}
                </span>
                <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
                  {botStatus.data.paper_only ? 'paper only' : 'live'}
                </span>
              </div>
              <div className="flex flex-col gap-2 sm:items-end">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Auto refresh</span>
                <AutoRefreshSelector value={autoRefreshSeconds} onChange={setAutoRefreshSeconds} />
              </div>
              <p>Last updated {formatDateTime(lastUpdatedAt?.toISOString() ?? null)}</p>
              <p>Refresh interval {refreshLabel}</p>
              <button
                type="button"
                onClick={() => void refreshWorkspace(selectedSymbol)}
                className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 font-medium text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20"
              >
                Refresh workspace
              </button>
            </div>
          </div>
        </header>

        <BotControlPanel
          searchQuery={symbolSearch}
          selectedSymbol={selectedSymbol}
          hasValidSelection={selectedSymbol.length > 0}
          symbolResults={symbolResults.data}
          symbolsLoading={symbolResults.loading || symbolResults.refreshing}
          symbolsError={symbolResults.error}
          status={botStatus.data}
          actionLoading={botActionLoading}
          actionError={botActionError ?? botStatus.error}
          onSearchChange={handleSymbolSearchChange}
          onSelectSymbol={handleSelectSymbol}
          onClearSelection={handleClearSelection}
          onStart={() => void runBotAction(() => startBot(selectedSymbol))}
          onStop={() => void runBotAction(stopBot)}
          onPauseResume={() => void runBotAction(() => (botStatus.data.state === 'paused' ? resumeBot() : pauseBot()))}
          onReset={() => void handleResetSession()}
        />

        <div className="flex flex-wrap gap-2">
          {([
            ['signal', 'Signal'],
            ['auto-trade', 'Auto Trade'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={classNames(
                'rounded-xl border px-4 py-2 text-sm font-medium transition',
                tab === value ? 'border-sky-400/40 bg-sky-400/10 text-sky-100' : 'border-slate-800 bg-slate-900/80 text-slate-300 hover:border-slate-600 hover:text-white',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {selectedSymbol.length === 0 ? (
          <StatePanel
            title="Select a symbol"
            message="Choose one Binance Spot USDT pair from the selector above. The workstation stays neutral until a symbol is selected."
            tone="empty"
          />
        ) : workstation.error ? (
          <StatePanel title="Workstation unavailable" message={workstation.error} tone="error" />
        ) : null}

        {tab === 'signal' ? (
          <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
            <SectionCard
              title="Signal"
              description="Live symbol context plus persisted advisory history for the selected symbol."
              action={workstation.refreshing || workstation.loading || aiSignal.refreshing || aiHistory.refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
            >
              {selectedSymbol.length === 0 ? (
                <StatePanel title="No symbol selected" message="Pick a symbol to load live signal state." tone="empty" />
              ) : (
                <div className="space-y-5">
                  <DataStateIndicator dataState={workstationDataState} message={workstationStatusMessage} />

                  {effectiveWorkstation === null || effectiveWorkstation.is_runtime_symbol === false ? (
                    <StatePanel
                      title="Live signal idle"
                      message="The selected symbol is not currently connected to the live runtime. Start the paper runtime to generate fresh live AI snapshots, or review the persisted AI history below."
                      tone="empty"
                    />
                  ) : (
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <MetricCard label="Selected Symbol" value={effectiveWorkstation.symbol} helper={`Runtime ${effectiveWorkstation.runtime_status.state}`} />
                        <MetricCard
                          label="Live Price"
                          value={effectiveWorkstation.last_price ? formatCurrency(effectiveWorkstation.last_price) : '-'}
                          helper={formatDateTime(effectiveWorkstation.last_market_event)}
                        />
                        <MetricCard label="Trend / Bias" value={trendLabel} helper={effectiveWorkstation.feature?.regime ?? 'No regime yet'} />
                        <MetricCard
                          label="Current Candle"
                          value={effectiveWorkstation.current_candle ? formatCurrency(effectiveWorkstation.current_candle.close) : '-'}
                          helper={effectiveWorkstation.current_candle ? `${effectiveWorkstation.current_candle.timeframe} candle` : 'Waiting for kline'}
                        />
                      </div>

                      <div className="grid gap-4 lg:grid-cols-2">
                        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Entry Signal</p>
                          <div className="mt-3 flex items-center gap-3">
                            <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(effectiveWorkstation.entry_signal?.side ?? 'HOLD'))}>
                              {effectiveWorkstation.entry_signal?.side ?? 'HOLD'}
                            </span>
                            <span className="text-sm text-slate-400">{describeSignal(effectiveWorkstation.entry_signal?.side)}</span>
                          </div>
                          <p className="mt-3 text-sm text-slate-300">{effectiveWorkstation.entry_signal?.reason_codes.join(', ') || 'No entry context yet'}</p>
                        </div>

                        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Exit Signal</p>
                          <div className="mt-3 flex items-center gap-3">
                            <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(effectiveWorkstation.exit_signal?.side ?? 'HOLD'))}>
                              {effectiveWorkstation.exit_signal?.side ?? 'HOLD'}
                            </span>
                            <span className="text-sm text-slate-400">{describeSignal(effectiveWorkstation.exit_signal?.side)}</span>
                          </div>
                          <p className="mt-3 text-sm text-slate-300">{effectiveWorkstation.exit_signal?.reason_codes.join(', ') || 'No exit context yet'}</p>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Short Explanation</p>
                        <p className="mt-3 text-sm leading-6 text-slate-300">{signalExplanation}</p>
                      </div>

                      <div className="grid gap-4 lg:grid-cols-2">
                        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Candle Summary</p>
                          {effectiveWorkstation.current_candle ? (
                            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-200">
                              <div><span className="text-slate-500">Open</span><p>{formatCurrency(effectiveWorkstation.current_candle.open)}</p></div>
                              <div><span className="text-slate-500">High</span><p>{formatCurrency(effectiveWorkstation.current_candle.high)}</p></div>
                              <div><span className="text-slate-500">Low</span><p>{formatCurrency(effectiveWorkstation.current_candle.low)}</p></div>
                              <div><span className="text-slate-500">Close</span><p>{formatCurrency(effectiveWorkstation.current_candle.close)}</p></div>
                              <div><span className="text-slate-500">Volume</span><p>{formatDecimal(effectiveWorkstation.current_candle.volume)}</p></div>
                              <div><span className="text-slate-500">Window</span><p>{formatDateTime(effectiveWorkstation.current_candle.close_time)}</p></div>
                            </div>
                          ) : (
                            <StatePanel title="Waiting for candle" message="No live candle has been received yet for this symbol." tone="empty" />
                          )}
                        </div>

                        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Feature Snapshot</p>
                          {effectiveWorkstation.feature ? (
                            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-200">
                              <div><span className="text-slate-500">EMA Fast</span><p>{formatCurrency(effectiveWorkstation.feature.ema_fast ?? 0)}</p></div>
                              <div><span className="text-slate-500">EMA Slow</span><p>{formatCurrency(effectiveWorkstation.feature.ema_slow ?? 0)}</p></div>
                              <div><span className="text-slate-500">ATR</span><p>{formatDecimal(effectiveWorkstation.feature.atr ?? 0)}</p></div>
                              <div><span className="text-slate-500">Spread</span><p>{formatDecimal(effectiveWorkstation.feature.bid_ask_spread ?? 0)}</p></div>
                              <div><span className="text-slate-500">Mid Price</span><p>{formatCurrency(effectiveWorkstation.feature.mid_price ?? 0)}</p></div>
                              <div><span className="text-slate-500">Book Imbalance</span><p>{formatDecimal(effectiveWorkstation.feature.order_book_imbalance ?? 0)}</p></div>
                            </div>
                          ) : (
                            <StatePanel title="Waiting for features" message="More candle history is needed before the feature engine can derive trend and volatility state." tone="empty" />
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">AI Signal</p>
                    {aiSignal.error ? (
                      <StatePanel title="AI signal unavailable" message={aiSignal.error} tone="error" />
                    ) : effectiveAiSignal ? (
                      <div className="mt-3 space-y-4">
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                          <MetricCard label="Bias" value={effectiveAiSignal.bias} helper="Probable market direction" />
                          <MetricCard label="Confidence" value={`${effectiveAiSignal.confidence}%`} helper={formatDateTime(effectiveAiSignal.timestamp)} />
                          <MetricCard label="Entry Setup" value={effectiveAiSignal.entry_signal ? 'Yes' : 'No'} helper="Potential entry present" />
                          <MetricCard label="Exit Setup" value={effectiveAiSignal.exit_signal ? 'Yes' : 'No'} helper="Potential exit present" />
                          <MetricCard label="Suggested Action" value={effectiveAiSignal.suggested_action} helper="Advisory only" />
                        </div>
                        <p className="text-sm leading-6 text-slate-300">{effectiveAiSignal.explanation}</p>
                      </div>
                    ) : aiSignal.loading ? (
                      <StatePanel title="Loading AI signal" message="Reading the latest persisted advisory snapshot for the selected symbol." tone="loading" />
                    ) : (
                      <StatePanel title="AI signal unavailable" message="No persisted AI advisory snapshot exists yet for the selected symbol." tone="empty" />
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <AIHistorySection
                      symbol={selectedSymbol}
                      history={aiHistory.data.items}
                      loading={aiHistory.loading}
                      refreshing={aiHistory.refreshing}
                      error={aiHistory.error}
                      dataState={aiHistory.data.data_state}
                      statusMessage={aiHistory.data.status_message}
                    />
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <AIEvaluationCard
                      symbol={selectedSymbol}
                      evaluation={aiEvaluation.data}
                      loading={aiEvaluation.loading}
                      refreshing={aiEvaluation.refreshing}
                      error={aiEvaluation.error}
                      dataState={aiEvaluation.data?.data_state ?? workstationDataState}
                      statusMessage={aiEvaluation.data?.status_message ?? workstationStatusMessage}
                    />
                  </div>
                </div>
              )}
            </SectionCard>

            <SectionCard title="Runtime Overview" description="Current symbol-scoped runtime state without mixing in old persisted summaries.">
              {selectedSymbol.length === 0 ? (
                <StatePanel title="No symbol selected" message="Select one symbol to populate the workstation." tone="empty" />
              ) : (
                <div className="grid gap-4">
                  <MetricCard label="Runtime Status" value={botStatus.data.state} helper={`Timeframe ${botStatus.data.timeframe}`} />
                  <MetricCard label="Selected Symbol" value={selectedSymbol} helper={effectiveWorkstation?.is_runtime_symbol ? 'Connected to live runtime' : 'Not running for this symbol'} />
                  <MetricCard label="Last Market Event" value={formatDateTime(effectiveWorkstation?.last_market_event ?? botStatus.data.last_event_time)} helper="Latest live market timestamp" />
                  <MetricCard label="Session Error" value={botStatus.data.last_error ?? '-'} helper="Most recent runtime error, if any" />
                </div>
              )}
            </SectionCard>
          </div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
            <SectionCard
              title="Auto Trade"
              description="Paper-only runtime control and current position for the selected symbol."
              action={effectiveWorkstation && (workstation.refreshing || workstation.loading) ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
            >
              {selectedSymbol.length === 0 ? (
                <StatePanel title="No symbol selected" message="Pick a symbol first, then use the controls above." tone="empty" />
              ) : (
                <div className="space-y-5">
                  <DataStateIndicator dataState={workstationDataState} message={workstationStatusMessage} />
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <MetricCard label="Runtime Status" value={botStatus.data.state} helper={`Paper only - ${selectedSymbol}`} />
                    <MetricCard label="Last Action" value={effectiveWorkstation?.last_action?.signal_side ?? 'Waiting'} helper={formatDateTime(effectiveWorkstation?.last_action?.event_time ?? null)} />
                    <MetricCard label="Last Market Event" value={formatDateTime(effectiveWorkstation?.last_market_event ?? botStatus.data.last_event_time)} helper="Most recent live event" />
                    <MetricCard label="Session PnL" value={formatCurrency(effectiveWorkstation?.total_pnl ?? '0')} tone={Number(effectiveWorkstation?.total_pnl ?? '0') >= 0 ? 'positive' : 'negative'} />
                  </div>

                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Paper Position</p>
                      {effectiveWorkstation?.current_position ? (
                        <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-200">
                          <div><span className="text-slate-500">Quantity</span><p>{formatDecimal(effectiveWorkstation.current_position.quantity)}</p></div>
                          <div><span className="text-slate-500">Avg Entry</span><p>{formatCurrency(effectiveWorkstation.current_position.avg_entry_price)}</p></div>
                          <div><span className="text-slate-500">Realized PnL</span><p className={pnlTone(effectiveWorkstation.current_position.realized_pnl)}>{formatCurrency(effectiveWorkstation.current_position.realized_pnl)}</p></div>
                          <div><span className="text-slate-500">Quote Asset</span><p>{effectiveWorkstation.current_position.quote_asset}</p></div>
                        </div>
                      ) : (
                        <StatePanel title="No open paper position" message="The selected symbol does not currently have an open paper position." tone="empty" />
                      )}
                    </div>

                    <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Last Action Details</p>
                      {effectiveWorkstation?.last_action ? (
                        <div className="mt-3 space-y-3 text-sm text-slate-200">
                          <div>
                            <span className="text-slate-500">Signal</span>
                            <p>{effectiveWorkstation.last_action.signal_side} - {effectiveWorkstation.last_action.signal_reasons.join(', ')}</p>
                          </div>
                          <div>
                            <span className="text-slate-500">Execution</span>
                            <p>{effectiveWorkstation.last_action.execution_status ?? 'Not executed'}{effectiveWorkstation.last_action.execution_reasons.length > 0 ? ` - ${effectiveWorkstation.last_action.execution_reasons.join(', ')}` : ''}</p>
                          </div>
                        </div>
                      ) : (
                        <StatePanel title="No action yet" message="No processed cycle has produced an action for the selected symbol in this session." tone="empty" />
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Session Notes</p>
                    <p className="mt-3 text-sm leading-6 text-slate-300">
                      Start begins live market-data ingestion and paper decisioning for the selected symbol. Pause keeps the runtime connected but stops automatic trading decisions, which gives you a signal-only monitoring mode. Reset Session clears persisted paper-session history so stale data does not mix with the next run.
                    </p>
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <PerformanceAnalyticsSection
                      symbol={selectedSymbol}
                      analytics={performanceAnalytics.data}
                      loading={performanceAnalytics.loading}
                      refreshing={performanceAnalytics.refreshing}
                      error={performanceAnalytics.error}
                    />
                  </div>
                </div>
              )}
            </SectionCard>

            <SectionCard title="Status" description="Quick single-symbol health checks for the current workstation.">
              <div className="grid gap-4">
                <MetricCard label="API Health" value={health.data?.status ?? 'loading'} helper={health.data?.mode ?? 'paper'} />
                <MetricCard label="Runtime Symbol" value={botStatus.data.symbol ?? '-'} helper={`Selected ${selectedSymbol || '-'}`} />
                <MetricCard label="Selected Symbol Session" value={effectiveWorkstation?.is_runtime_symbol ? 'Live' : 'Idle'} helper={effectiveWorkstation?.is_runtime_symbol ? 'Receiving live updates' : 'No current runtime for selected symbol'} />
                <MetricCard label="Realized PnL" value={formatCurrency(effectiveWorkstation?.realized_pnl ?? '0')} tone={Number(effectiveWorkstation?.realized_pnl ?? '0') >= 0 ? 'positive' : 'negative'} />
              </div>
            </SectionCard>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
