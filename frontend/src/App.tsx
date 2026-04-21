import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActivityFeed } from './components/ActivityFeed';
import { AutoRefreshSelector } from './components/AutoRefreshSelector';
import { BotControlPanel } from './components/BotControlPanel';
import { BotIntelligencePanel } from './components/BotIntelligencePanel';
import { CompactDeltaCard } from './components/CompactDeltaCard';
import { HorizontalBars } from './components/HorizontalBars';
import { MetricCard } from './components/MetricCard';
import { PaginationControls } from './components/PaginationControls';
import { RangeSelector } from './components/RangeSelector';
import { SectionCard } from './components/SectionCard';
import { StatePanel } from './components/StatePanel';
import { TimeSeriesChart } from './components/TimeSeriesChart';
import {
  getAllTrades,
  getBotStatus,
  getDrawdown,
  getEquity,
  getEquityHistory,
  getEvents,
  getFills,
  getHealth,
  getMetrics,
  getPnlHistory,
  getPositions,
  getRecentEvents,
  getSymbols,
  pauseBot,
  resumeBot,
  startBot,
  stopBot,
  getSymbolSummaries,
  getTrades,
} from './lib/api';
import { badgeTone, classNames, formatCurrency, formatDateTime, formatDecimal, formatShortDateTime, pnlTone } from './lib/format';
import { resolveRangeFilters } from './lib/history';
import {
  deriveActivityFeed,
  deriveBotIntelligence,
  deriveNarrative,
  deriveTrustMetrics,
  type ActivityFeedEntry,
  type BotIntelligence,
  type DerivedNarrative,
  type TrustMetricsSummary,
} from './lib/insights';
import type {
  AutoRefreshIntervalSeconds,
  DrawdownResponse,
  EquityHistoryPoint,
  EquityResponse,
  BotStatusResponse,
  EventItem,
  FillItem,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  PaginatedResponse,
  PnlHistoryResponse,
  PositionItem,
  RangePreset,
  SpotSymbolItem,
  SymbolSummaryItem,
  TradeItem,
} from './lib/types';

interface AsyncState<T> {
  data: T;
  loading: boolean;
  error: string | null;
}

const DEFAULT_PAGE_SIZE = 10;
const DEFAULT_FILTERS: HistoryFilters = {
  symbol: '',
  startDate: '',
  endDate: '',
  limit: DEFAULT_PAGE_SIZE,
  offset: 0,
};

const INITIAL_METRICS: MetricsResponse = {
  total_trades: 0,
  win_rate: '0',
  realized_pnl: '0',
  average_pnl_per_trade: '0',
  current_equity: '0',
  max_winning_streak: 0,
  max_losing_streak: 0,
};

const INITIAL_EQUITY: EquityResponse = {
  snapshot_time: null,
  equity: '0',
  total_pnl: '0',
  realized_pnl: '0',
  cash_balance: '0',
};

const INITIAL_BOT_STATUS: BotStatusResponse = {
  state: 'stopped',
  symbol: null,
  timeframe: '1m',
  paper_only: true,
  started_at: null,
  last_event_time: null,
  last_error: null,
};

const INITIAL_BOT_INTELLIGENCE: BotIntelligence = {
  currentState: 'Watching',
  lastAction: 'Waiting',
  lastSymbol: '-',
  reasonForLastAction: 'No recent action recorded',
  currentTrendBias: 'Neutral',
  riskState: 'Idle',
};

const INITIAL_NARRATIVE: DerivedNarrative = {
  label: 'Derived summary',
  text: 'Derived summary: no recent persisted decision is available yet, so the bot is still waiting for a validated setup.',
};

const INITIAL_TRUST_METRICS: TrustMetricsSummary = {
  winningTrades: 0,
  losingTrades: 0,
  avgGain: 0,
  avgLoss: 0,
  sampleSize: 0,
  sampleSizeConfidence: 'Low',
};

const INITIAL_PNL_HISTORY: PnlHistoryResponse = {
  points: [],
  daily: [],
};

const INITIAL_DRAWDOWN: DrawdownResponse = {
  current_drawdown: '0',
  current_drawdown_pct: '0',
  max_drawdown: '0',
  max_drawdown_pct: '0',
  points: [],
};

function createAsyncState<T>(data: T): AsyncState<T> {
  return {
    data,
    loading: true,
    error: null,
  };
}

function formatSignedCurrency(value: number): string {
  if (value > 0) {
    return `+${formatCurrency(value)}`;
  }
  return formatCurrency(value);
}

function App() {
  const [health, setHealth] = useState<AsyncState<HealthResponse | null>>(createAsyncState<HealthResponse | null>(null));
  const [botStatus, setBotStatus] = useState<AsyncState<BotStatusResponse>>(createAsyncState(INITIAL_BOT_STATUS));
  const [metrics, setMetrics] = useState<AsyncState<MetricsResponse>>(createAsyncState(INITIAL_METRICS));
  const [equity, setEquity] = useState<AsyncState<EquityResponse>>(createAsyncState(INITIAL_EQUITY));
  const [positions, setPositions] = useState<AsyncState<PositionItem[]>>(createAsyncState<PositionItem[]>([]));
  const [summaries, setSummaries] = useState<AsyncState<SymbolSummaryItem[]>>(createAsyncState<SymbolSummaryItem[]>([]));
  const [botIntelligence, setBotIntelligence] = useState<AsyncState<BotIntelligence>>(createAsyncState(INITIAL_BOT_INTELLIGENCE));
  const [narrative, setNarrative] = useState<AsyncState<DerivedNarrative>>(createAsyncState(INITIAL_NARRATIVE));
  const [activityFeed, setActivityFeed] = useState<AsyncState<ActivityFeedEntry[]>>(createAsyncState<ActivityFeedEntry[]>([]));
  const [trustMetrics, setTrustMetrics] = useState<AsyncState<TrustMetricsSummary>>(createAsyncState(INITIAL_TRUST_METRICS));
  const [historyPreset, setHistoryPreset] = useState<RangePreset>('ALL');
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState<AutoRefreshIntervalSeconds>(10);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [equityHistory, setEquityHistory] = useState<AsyncState<EquityHistoryPoint[]>>(createAsyncState<EquityHistoryPoint[]>([]));
  const [pnlHistory, setPnlHistory] = useState<AsyncState<PnlHistoryResponse>>(createAsyncState(INITIAL_PNL_HISTORY));
  const [drawdown, setDrawdown] = useState<AsyncState<DrawdownResponse>>(createAsyncState(INITIAL_DRAWDOWN));
  const [summarySymbols, setSummarySymbols] = useState('');
  const [symbolSearch, setSymbolSearch] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [symbolResults, setSymbolResults] = useState<AsyncState<SpotSymbolItem[]>>(createAsyncState<SpotSymbolItem[]>([]));
  const [botActionError, setBotActionError] = useState<string | null>(null);
  const [botActionLoading, setBotActionLoading] = useState(false);

  const [tradeFilters, setTradeFilters] = useState<HistoryFilters>(DEFAULT_FILTERS);
  const [fillFilters, setFillFilters] = useState<HistoryFilters>(DEFAULT_FILTERS);
  const [eventFilters, setEventFilters] = useState<HistoryFilters>(DEFAULT_FILTERS);

  const [trades, setTrades] = useState<AsyncState<PaginatedResponse<TradeItem>>>(
    createAsyncState<PaginatedResponse<TradeItem>>({ items: [], total: 0, limit: DEFAULT_PAGE_SIZE, offset: 0 }),
  );
  const [fills, setFills] = useState<AsyncState<PaginatedResponse<FillItem>>>(
    createAsyncState<PaginatedResponse<FillItem>>({ items: [], total: 0, limit: DEFAULT_PAGE_SIZE, offset: 0 }),
  );
  const [events, setEvents] = useState<AsyncState<PaginatedResponse<EventItem>>>(
    createAsyncState<PaginatedResponse<EventItem>>({ items: [], total: 0, limit: DEFAULT_PAGE_SIZE, offset: 0 }),
  );

  const loadOverview = useCallback(async (symbolsInput: string) => {
    setHealth((current) => ({ ...current, loading: true, error: null }));
    setBotStatus((current) => ({ ...current, loading: true, error: null }));
    setMetrics((current) => ({ ...current, loading: true, error: null }));
    setEquity((current) => ({ ...current, loading: true, error: null }));
    setPositions((current) => ({ ...current, loading: true, error: null }));
    setSummaries((current) => ({ ...current, loading: true, error: null }));

    const summarySymbolList = symbolsInput
      .split(',')
      .map((symbol) => symbol.trim())
      .filter((symbol) => symbol.length > 0);

    try {
      const [healthData, botStatusData, metricsData, equityData, positionsData, summaryData] = await Promise.all([
        getHealth(),
        getBotStatus(),
        getMetrics(),
        getEquity(),
        getPositions(),
        getSymbolSummaries(summarySymbolList),
      ]);
      setHealth({ data: healthData, loading: false, error: null });
      setBotStatus({ data: botStatusData, loading: false, error: null });
      setMetrics({ data: metricsData, loading: false, error: null });
      setEquity({ data: equityData, loading: false, error: null });
      setPositions({ data: positionsData, loading: false, error: null });
      setSummaries({ data: summaryData, loading: false, error: null });
      if (!selectedSymbol && botStatusData.symbol) {
        setSelectedSymbol(botStatusData.symbol);
        setSymbolSearch(botStatusData.symbol);
      }
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading overview data.';
      setHealth((current) => ({ ...current, loading: false, error: message }));
      setBotStatus((current) => ({ ...current, loading: false, error: message }));
      setMetrics((current) => ({ ...current, loading: false, error: message }));
      setEquity((current) => ({ ...current, loading: false, error: message }));
      setPositions((current) => ({ ...current, loading: false, error: message }));
      setSummaries((current) => ({ ...current, loading: false, error: message }));
    }
  }, [selectedSymbol]);

  const loadHistory = useCallback(async (preset: RangePreset) => {
    setEquityHistory((current) => ({ ...current, loading: true, error: null }));
    setPnlHistory((current) => ({ ...current, loading: true, error: null }));
    setDrawdown((current) => ({ ...current, loading: true, error: null }));

    const filters = resolveRangeFilters(preset);

    try {
      const [equityHistoryData, pnlHistoryData, drawdownData] = await Promise.all([
        getEquityHistory(filters),
        getPnlHistory(filters),
        getDrawdown(filters),
      ]);
      setEquityHistory({ data: equityHistoryData, loading: false, error: null });
      setPnlHistory({ data: pnlHistoryData, loading: false, error: null });
      setDrawdown({ data: drawdownData, loading: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading historical performance.';
      setEquityHistory((current) => ({ ...current, loading: false, error: message }));
      setPnlHistory((current) => ({ ...current, loading: false, error: message }));
      setDrawdown((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadTrades = useCallback(async (filters: HistoryFilters) => {
    setTrades((current) => ({ ...current, loading: true, error: null }));
    try {
      const tradeData = await getTrades(filters);
      setTrades({ data: tradeData, loading: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading trades.';
      setTrades((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadFills = useCallback(async (filters: HistoryFilters) => {
    setFills((current) => ({ ...current, loading: true, error: null }));
    try {
      const fillData = await getFills(filters);
      setFills({ data: fillData, loading: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading fills.';
      setFills((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadEvents = useCallback(async (filters: HistoryFilters) => {
    setEvents((current) => ({ ...current, loading: true, error: null }));
    try {
      const eventData = await getEvents(filters);
      setEvents({ data: eventData, loading: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading events.';
      setEvents((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadExplainability = useCallback(async (currentPositions: PositionItem[]) => {
    setBotIntelligence((current) => ({ ...current, loading: true, error: null }));
    setNarrative((current) => ({ ...current, loading: true, error: null }));
    setActivityFeed((current) => ({ ...current, loading: true, error: null }));
    setTrustMetrics((current) => ({ ...current, loading: true, error: null }));

    try {
      const [allTrades, recentEvents] = await Promise.all([getAllTrades(), getRecentEvents(10)]);
      const intelligence = deriveBotIntelligence(currentPositions, allTrades, recentEvents);
      const summaryNarrative = deriveNarrative(recentEvents);
      const trust = deriveTrustMetrics(allTrades);
      const feed = deriveActivityFeed(recentEvents);

      setBotIntelligence({ data: intelligence, loading: false, error: null });
      setNarrative({ data: summaryNarrative, loading: false, error: null });
      setActivityFeed({ data: feed, loading: false, error: null });
      setTrustMetrics({ data: trust, loading: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading bot explainability.';
      setBotIntelligence((current) => ({ ...current, loading: false, error: message }));
      setNarrative((current) => ({ ...current, loading: false, error: message }));
      setActivityFeed((current) => ({ ...current, loading: false, error: message }));
      setTrustMetrics((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadSymbols = useCallback(async (query: string) => {
    setSymbolResults((current) => ({ ...current, loading: true, error: null }));
    try {
      const symbols = await getSymbols(query, 10);
      setSymbolResults({ data: symbols, loading: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading symbols.';
      setSymbolResults((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const handleSymbolSearchChange = useCallback((value: string) => {
    setSymbolSearch(value);
    if (value.trim().toUpperCase() !== selectedSymbol) {
      setSelectedSymbol('');
    }
  }, [selectedSymbol]);

  const handleSelectSymbol = useCallback((symbol: string) => {
    setSelectedSymbol(symbol);
    setSymbolSearch(symbol);
    setBotActionError(null);
  }, []);

  useEffect(() => {
    void loadOverview(summarySymbols);
  }, [loadOverview, summarySymbols]);

  useEffect(() => {
    void loadExplainability(positions.data);
  }, [loadExplainability, positions.data]);

  useEffect(() => {
    void loadHistory(historyPreset);
  }, [historyPreset, loadHistory]);

  useEffect(() => {
    void loadTrades(tradeFilters);
  }, [loadTrades, tradeFilters]);

  useEffect(() => {
    void loadFills(fillFilters);
  }, [fillFilters, loadFills]);

  useEffect(() => {
    void loadEvents(eventFilters);
  }, [eventFilters, loadEvents]);

  useEffect(() => {
    void loadSymbols(symbolSearch);
  }, [loadSymbols, symbolSearch]);

  const summaryBarItems = useMemo(
    () => summaries.data.map((item) => ({ label: item.symbol, value: Number(item.realized_pnl) })),
    [summaries.data],
  );

  const equityHistoryLabels = useMemo(() => equityHistory.data.map((point) => point.snapshot_time), [equityHistory.data]);
  const equityHistoryValues = useMemo(() => equityHistory.data.map((point) => Number(point.equity)), [equityHistory.data]);
  const pnlHistoryLabels = useMemo(() => pnlHistory.data.points.map((point) => point.snapshot_time), [pnlHistory.data.points]);
  const realizedPnlValues = useMemo(() => pnlHistory.data.points.map((point) => Number(point.realized_pnl)), [pnlHistory.data.points]);
  const totalPnlValues = useMemo(() => pnlHistory.data.points.map((point) => Number(point.total_pnl)), [pnlHistory.data.points]);
  const drawdownLabels = useMemo(() => drawdown.data.points.map((point) => point.snapshot_time), [drawdown.data.points]);
  const drawdownValues = useMemo(() => drawdown.data.points.map((point) => Number(point.drawdown_pct) * -1), [drawdown.data.points]);
  const historyError = equityHistory.error ?? pnlHistory.error ?? drawdown.error;
  const historyLoading = equityHistory.loading || pnlHistory.loading || drawdown.loading;

  const latestTradeSummary = useMemo(() => {
    return summaries.data.reduce<SymbolSummaryItem | null>((latest, item) => {
      if (!item.last_trade_time) {
        return latest;
      }
      if (latest === null || !latest.last_trade_time) {
        return item;
      }
      return new Date(item.last_trade_time) > new Date(latest.last_trade_time) ? item : latest;
    }, null);
  }, [summaries.data]);

  const equityDelta = useMemo(() => {
    if (equityHistory.data.length < 2) {
      return 0;
    }
    const latest = Number(equityHistory.data[equityHistory.data.length - 1]?.equity ?? 0);
    const previous = Number(equityHistory.data[equityHistory.data.length - 2]?.equity ?? 0);
    return latest - previous;
  }, [equityHistory.data]);

  const realizedPnlDelta = useMemo(() => {
    if (pnlHistory.data.points.length < 2) {
      return 0;
    }
    const latest = Number(pnlHistory.data.points[pnlHistory.data.points.length - 1]?.realized_pnl ?? 0);
    const previous = Number(pnlHistory.data.points[pnlHistory.data.points.length - 2]?.realized_pnl ?? 0);
    return latest - previous;
  }, [pnlHistory.data.points]);

  const refreshAll = useCallback(async () => {
    await Promise.all([
      loadOverview(summarySymbols),
      loadExplainability(positions.data),
      loadHistory(historyPreset),
      loadTrades(tradeFilters),
      loadFills(fillFilters),
      loadEvents(eventFilters),
    ]);
  }, [eventFilters, fillFilters, historyPreset, loadEvents, loadExplainability, loadFills, loadHistory, loadOverview, loadTrades, positions.data, summarySymbols, tradeFilters]);

  const runBotAction = useCallback(async (action: () => Promise<BotStatusResponse>) => {
    setBotActionLoading(true);
    setBotActionError(null);
    try {
      const nextStatus = await action();
      setBotStatus({ data: nextStatus, loading: false, error: null });
      if (nextStatus.symbol) {
        setSelectedSymbol(nextStatus.symbol);
        setSymbolSearch(nextStatus.symbol);
      }
      await refreshAll();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while updating the live paper bot.';
      setBotActionError(message);
    } finally {
      setBotActionLoading(false);
    }
  }, [refreshAll]);

  useEffect(() => {
    if (autoRefreshSeconds === 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refreshAll();
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshSeconds, refreshAll]);

  return (
    <div className="min-h-screen bg-transparent text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 rounded-3xl border border-slate-800/80 bg-slate-950/70 p-6 shadow-glow backdrop-blur lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-sky-300">Binance AI Bot</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">Paper Trading Dashboard</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              Read-only monitoring for the paper bot. Tables, symbol drill-down, and performance metrics are sourced from the FastAPI monitoring API.
            </p>
          </div>
          <div className="flex flex-col items-start gap-3 text-sm sm:items-end">
            <div className="flex items-center gap-2">
              <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(health.data?.status ?? 'unknown'))}>
                {health.data?.status ?? 'loading'}
              </span>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
                {health.data?.mode ?? 'paper'}
              </span>
            </div>
            <div className="grid gap-3 sm:justify-items-end">
              <div className="flex flex-col gap-2 sm:items-end">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Chart range</span>
                <RangeSelector value={historyPreset} onChange={setHistoryPreset} />
              </div>
              <div className="flex flex-col gap-2 sm:items-end">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Auto refresh</span>
                <AutoRefreshSelector value={autoRefreshSeconds} onChange={setAutoRefreshSeconds} />
              </div>
              <div className="text-xs text-slate-400">
                <p>Last updated {formatDateTime(lastUpdatedAt?.toISOString() ?? null)}</p>
                <p>{autoRefreshSeconds === 0 ? 'Auto-refresh paused' : `Refreshing every ${autoRefreshSeconds}s`}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void refreshAll()}
              className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 font-medium text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20"
            >
              Refresh data
            </button>
          </div>
        </header>

        {health.error ? <StatePanel title="API error" message={health.error} tone="error" /> : null}

        <BotControlPanel
          searchQuery={symbolSearch}
          selectedSymbol={selectedSymbol}
          hasValidSelection={selectedSymbol.length > 0}
          symbolResults={symbolResults.data}
          symbolsLoading={symbolResults.loading}
          symbolsError={symbolResults.error}
          status={botStatus.data}
          actionLoading={botActionLoading}
          actionError={botActionError}
          onSearchChange={handleSymbolSearchChange}
          onSelectSymbol={handleSelectSymbol}
          onStart={() => void runBotAction(() => startBot(selectedSymbol))}
          onStop={() => void runBotAction(stopBot)}
          onPauseResume={() => void runBotAction(() => (botStatus.data.state === 'paused' ? resumeBot() : pauseBot()))}
        />

        {botIntelligence.loading || narrative.loading ? (
          <StatePanel title="Loading intelligence" message="Summarizing the bot's latest actions and risk posture." />
        ) : botIntelligence.error || narrative.error ? (
          <StatePanel title="Intelligence unavailable" message={botIntelligence.error ?? narrative.error ?? 'Unable to derive the latest summary.'} tone="error" />
        ) : (
          <BotIntelligencePanel intelligence={botIntelligence.data} narrative={narrative.data} />
        )}

        <div className="grid gap-6 xl:grid-cols-[1.3fr,0.9fr]">
          <SectionCard
            title="Live Activity Feed"
            description="Recent bot decisions and execution steps, ordered from newest to oldest so the latest move is easy to understand."
          >
            {activityFeed.loading ? (
              <StatePanel title="Loading activity" message="Fetching recent bot decisions and execution events." />
            ) : activityFeed.error ? (
              <StatePanel title="Activity unavailable" message={activityFeed.error} tone="error" />
            ) : (
              <ActivityFeed items={activityFeed.data} />
            )}
          </SectionCard>

          <SectionCard
            title="Trust Metrics"
            description="A quick confidence read based on closed paper trades, how often the bot wins, and the average size of gains versus losses."
          >
            {trustMetrics.loading ? (
              <StatePanel title="Loading trust metrics" message="Calculating win/loss quality from persisted trade history." />
            ) : trustMetrics.error ? (
              <StatePanel title="Trust metrics unavailable" message={trustMetrics.error} tone="error" />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <CompactDeltaCard
                  label="Winning Trades"
                  value={String(trustMetrics.data.winningTrades)}
                  helper={`${trustMetrics.data.sampleSize} closed trades observed`}
                  tone="positive"
                />
                <CompactDeltaCard
                  label="Losing Trades"
                  value={String(trustMetrics.data.losingTrades)}
                  helper={`${trustMetrics.data.sampleSize} closed trades observed`}
                  tone={trustMetrics.data.losingTrades > 0 ? 'negative' : 'default'}
                />
                <CompactDeltaCard
                  label="Avg Gain"
                  value={formatSignedCurrency(trustMetrics.data.avgGain)}
                  helper="Average realized PnL on winners"
                  tone={trustMetrics.data.avgGain > 0 ? 'positive' : 'default'}
                />
                <CompactDeltaCard
                  label="Avg Loss"
                  value={formatSignedCurrency(trustMetrics.data.avgLoss)}
                  helper="Average realized PnL on losers"
                  tone={trustMetrics.data.avgLoss < 0 ? 'negative' : 'default'}
                />
                <CompactDeltaCard
                  label="Sample Size Confidence"
                  value={trustMetrics.data.sampleSizeConfidence}
                  helper={`${trustMetrics.data.sampleSize} closed trades backing this read`}
                  tone={trustMetrics.data.sampleSize >= 10 ? 'positive' : 'default'}
                />
              </div>
            )}
          </SectionCard>
        </div>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Current Equity"
            value={formatCurrency(equity.data.equity)}
            helper={`Snapshot ${formatDateTime(equity.data.snapshot_time)}`}
          />
          <MetricCard
            label="Realized PnL"
            value={formatCurrency(metrics.data.realized_pnl)}
            helper={`Avg per close ${formatCurrency(metrics.data.average_pnl_per_trade)}`}
            tone={Number(metrics.data.realized_pnl) >= 0 ? 'positive' : 'negative'}
          />
          <MetricCard
            label="Win Rate"
            value={`${formatDecimal(metrics.data.win_rate, { maximumFractionDigits: 1 })}%`}
            helper={`Total executed trades ${metrics.data.total_trades}`}
          />
          <MetricCard
            label="Open Positions"
            value={String(positions.data.length)}
            helper={`Max win streak ${metrics.data.max_winning_streak} | max loss streak ${metrics.data.max_losing_streak}`}
          />
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <CompactDeltaCard
            label="Equity Change"
            value={formatSignedCurrency(equityDelta)}
            helper={equity.data.snapshot_time ? `vs previous snapshot | ${formatShortDateTime(equity.data.snapshot_time)}` : 'Waiting for equity history'}
            delta={equityDelta > 0 ? 'Up' : equityDelta < 0 ? 'Down' : 'Flat'}
            tone={equityDelta > 0 ? 'positive' : equityDelta < 0 ? 'negative' : 'default'}
          />
          <CompactDeltaCard
            label="Realized PnL Change"
            value={formatSignedCurrency(realizedPnlDelta)}
            helper={pnlHistory.data.points.length > 0 ? `Latest close ${formatShortDateTime(pnlHistory.data.points[pnlHistory.data.points.length - 1]?.snapshot_time ?? null)}` : 'Waiting for realized PnL history'}
            delta={realizedPnlDelta > 0 ? 'Gain' : realizedPnlDelta < 0 ? 'Loss' : 'Flat'}
            tone={realizedPnlDelta > 0 ? 'positive' : realizedPnlDelta < 0 ? 'negative' : 'default'}
          />
          <CompactDeltaCard
            label="Peak-to-Trough Drop"
            value={`${formatDecimal(Number(drawdown.data.current_drawdown_pct), { maximumFractionDigits: 2 })}%`}
            helper={`Worst ${formatDecimal(Number(drawdown.data.max_drawdown_pct), { maximumFractionDigits: 2 })}% | ${formatCurrency(drawdown.data.max_drawdown)}`}
            delta={Number(drawdown.data.current_drawdown) > 0 ? 'Active' : 'Recovered'}
            tone={Number(drawdown.data.current_drawdown) > 0 ? 'negative' : 'default'}
          />
          <CompactDeltaCard
            label="Last Trade"
            value={formatDateTime(latestTradeSummary?.last_trade_time ?? null)}
            helper={latestTradeSummary ? `${latestTradeSummary.symbol} | ${latestTradeSummary.total_trades} trades` : 'No executed trades persisted yet'}
            delta={latestTradeSummary?.symbol}
            tone="default"
          />
        </section>

        <SectionCard
          title="Historical Performance"
          description="Real persisted curves from /equity/history, /pnl/history, and /drawdown, with labels phrased for end users rather than developers."
        >
          {historyLoading ? (
            <StatePanel title="Loading" message="Fetching persisted equity, PnL, and peak-to-trough drop history." />
          ) : historyError ? (
            <StatePanel title="History unavailable" message={historyError} tone="error" />
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  label="Range"
                  value={historyPreset}
                  helper={equityHistory.data.length > 0 ? `${equityHistory.data.length} equity snapshots` : 'No persisted points'}
                />
                <MetricCard
                  label="Worst Peak-to-Trough Drop"
                  value={`${formatDecimal(Number(drawdown.data.max_drawdown_pct), { maximumFractionDigits: 2 })}%`}
                  helper={formatCurrency(drawdown.data.max_drawdown)}
                  tone={Number(drawdown.data.max_drawdown) === 0 ? 'default' : 'negative'}
                />
                <MetricCard
                  label="Current Peak-to-Trough Drop"
                  value={`${formatDecimal(Number(drawdown.data.current_drawdown_pct), { maximumFractionDigits: 2 })}%`}
                  helper={formatCurrency(drawdown.data.current_drawdown)}
                  tone={Number(drawdown.data.current_drawdown) === 0 ? 'default' : 'negative'}
                />
                <MetricCard
                  label="Historical Snapshots"
                  value={String(pnlHistory.data.points.length)}
                  helper={`${pnlHistory.data.daily.length} daily aggregates`}
                />
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <TimeSeriesChart
                  title="Equity Curve"
                  subtitle="Persisted account equity snapshots"
                  labels={equityHistoryLabels}
                  series={[{ key: 'equity', label: 'Equity', color: '#38bdf8', values: equityHistoryValues, format: 'currency' }]}
                />
                <TimeSeriesChart
                  title="Realized PnL Curve"
                  subtitle="Closed-trade profit and loss over time"
                  labels={pnlHistoryLabels}
                  series={[{ key: 'realized-pnl', label: 'Realized PnL', color: '#22c55e', values: realizedPnlValues, format: 'currency' }]}
                />
                <TimeSeriesChart
                  title="Total PnL Curve"
                  subtitle="Realized plus mark-to-market paper PnL"
                  labels={pnlHistoryLabels}
                  series={[{ key: 'total-pnl', label: 'Total PnL', color: '#a855f7', values: totalPnlValues, format: 'currency' }]}
                />
                <TimeSeriesChart
                  title="Peak-to-Trough Drop Curve"
                  subtitle="Largest decline from the running equity peak"
                  labels={drawdownLabels}
                  series={[{ key: 'drawdown', label: 'Peak-to-Trough Drop %', color: '#fb7185', values: drawdownValues, format: 'percent' }]}
                />
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Symbol PnL Breakdown" description="Realized PnL per symbol from /summary/symbols.">
          <div className="mb-4 flex flex-col gap-3">
            <label className="text-sm text-slate-400">
              Filter symbols (comma-separated)
              <input
                value={summarySymbols}
                onChange={(event) => setSummarySymbols(event.target.value)}
                placeholder="BTCUSDT,ETHUSDT"
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400"
              />
            </label>
          </div>
          {summaries.loading ? (
            <StatePanel title="Loading" message="Fetching symbol summary data." />
          ) : summaries.error ? (
            <StatePanel title="Summary unavailable" message={summaries.error} tone="error" />
          ) : (
            <HorizontalBars items={summaryBarItems} />
          )}
        </SectionCard>

        <SectionCard title="Symbol Summary" description="Per-symbol performance and open exposure for drill-down.">
          {summaries.loading ? (
            <StatePanel title="Loading" message="Fetching symbol summary data." />
          ) : summaries.error ? (
            <StatePanel title="Summary unavailable" message={summaries.error} tone="error" />
          ) : summaries.data.length === 0 ? (
            <StatePanel title="No data" message="No symbols matched the current summary filter." tone="empty" />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-800 text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                    <th className="pb-3 pr-4">Symbol</th>
                    <th className="pb-3 pr-4">Trades</th>
                    <th className="pb-3 pr-4">Win Rate</th>
                    <th className="pb-3 pr-4">Realized PnL</th>
                    <th className="pb-3 pr-4">Open Qty</th>
                    <th className="pb-3 pr-4">Open Exposure</th>
                    <th className="pb-3">Last Trade</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-900/80 text-slate-200">
                  {summaries.data.map((summary) => (
                    <tr key={summary.symbol}>
                      <td className="py-3 pr-4 font-medium text-white">{summary.symbol}</td>
                      <td className="py-3 pr-4">{summary.total_trades}</td>
                      <td className="py-3 pr-4">{formatDecimal(summary.win_rate)}%</td>
                      <td className={classNames('py-3 pr-4', pnlTone(summary.realized_pnl))}>{formatCurrency(summary.realized_pnl)}</td>
                      <td className="py-3 pr-4">{formatDecimal(summary.open_quantity)}</td>
                      <td className="py-3 pr-4">{formatCurrency(summary.open_exposure)}</td>
                      <td className="py-3">{formatDateTime(summary.last_trade_time)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
          <SectionCard title="Current Positions" description="Open paper positions from the latest persisted position snapshots.">
            {positions.loading ? (
              <StatePanel title="Loading" message="Fetching open positions." />
            ) : positions.error ? (
              <StatePanel title="Positions unavailable" message={positions.error} tone="error" />
            ) : positions.data.length === 0 ? (
              <StatePanel title="No open positions" message="The paper broker currently has no open positions." tone="empty" />
            ) : (
              <div className="space-y-3">
                {positions.data.map((position) => (
                  <div key={`${position.symbol}-${position.snapshot_time}`} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-white">{position.symbol}</p>
                        <p className="mt-1 text-xs text-slate-500">{formatDateTime(position.snapshot_time)}</p>
                      </div>
                      <span className="rounded-full bg-sky-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-sky-200">
                        {formatDecimal(position.quantity)} {position.quote_asset}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-slate-500">Avg entry</p>
                        <p className="mt-1 font-medium text-slate-100">{formatCurrency(position.avg_entry_price)}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Realized PnL</p>
                        <p className={classNames('mt-1 font-medium', pnlTone(position.realized_pnl))}>{formatCurrency(position.realized_pnl)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Equity Snapshot" description="Latest stored account-level equity and balances.">
            {equity.loading ? (
              <StatePanel title="Loading" message="Fetching latest equity snapshot." />
            ) : equity.error ? (
              <StatePanel title="Equity unavailable" message={equity.error} tone="error" />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <MetricCard label="Equity" value={formatCurrency(equity.data.equity)} helper={formatDateTime(equity.data.snapshot_time)} />
                <MetricCard
                  label="Total PnL"
                  value={formatCurrency(equity.data.total_pnl)}
                  tone={Number(equity.data.total_pnl) >= 0 ? 'positive' : 'negative'}
                />
                <MetricCard label="Cash Balance" value={formatCurrency(equity.data.cash_balance)} helper="USDT balance equivalent" />
                <MetricCard
                  label="Realized PnL"
                  value={formatCurrency(equity.data.realized_pnl)}
                  tone={Number(equity.data.realized_pnl) >= 0 ? 'positive' : 'negative'}
                />
              </div>
            )}
          </SectionCard>
        </div>

        <HistorySection
          title="Trades"
          description="Paginated trade history with symbol and date filters."
          filters={tradeFilters}
          onFiltersChange={setTradeFilters}
          onReload={() => void loadTrades(tradeFilters)}
          loading={trades.loading}
          error={trades.error}
          total={trades.data.total}
          limit={trades.data.limit}
          offset={trades.data.offset}
          onPrevious={() => setTradeFilters((current) => ({ ...current, offset: Math.max(current.offset - current.limit, 0) }))}
          onNext={() => setTradeFilters((current) => ({ ...current, offset: current.offset + current.limit }))}
        >
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800 text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                  <th className="pb-3 pr-4">Time</th>
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4">Side</th>
                  <th className="pb-3 pr-4">Fill Price</th>
                  <th className="pb-3 pr-4">Filled Qty</th>
                  <th className="pb-3 pr-4">Realized PnL</th>
                  <th className="pb-3 pr-4">Decision</th>
                  <th className="pb-3">Reasons</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900/70 text-slate-200">
                {trades.data.items.map((trade) => (
                  <tr key={trade.order_id}>
                    <td className="py-3 pr-4">{formatDateTime(trade.event_time)}</td>
                    <td className="py-3 pr-4 font-medium text-white">{trade.symbol}</td>
                    <td className="py-3 pr-4">
                      <span className={classNames('rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(trade.side))}>{trade.side}</span>
                    </td>
                    <td className="py-3 pr-4">{formatCurrency(trade.fill_price)}</td>
                    <td className="py-3 pr-4">{formatDecimal(trade.filled_quantity)}</td>
                    <td className={classNames('py-3 pr-4', pnlTone(trade.realized_pnl))}>{formatCurrency(trade.realized_pnl)}</td>
                    <td className="py-3 pr-4">
                      <span className={classNames('rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(trade.risk_decision))}>{trade.risk_decision}</span>
                    </td>
                    <td className="py-3">{trade.reason_codes.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </HistorySection>

        <HistorySection
          title="Fills"
          description="Execution fills with filterable symbol and date constraints."
          filters={fillFilters}
          onFiltersChange={setFillFilters}
          onReload={() => void loadFills(fillFilters)}
          loading={fills.loading}
          error={fills.error}
          total={fills.data.total}
          limit={fills.data.limit}
          offset={fills.data.offset}
          onPrevious={() => setFillFilters((current) => ({ ...current, offset: Math.max(current.offset - current.limit, 0) }))}
          onNext={() => setFillFilters((current) => ({ ...current, offset: current.offset + current.limit }))}
        >
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800 text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                  <th className="pb-3 pr-4">Time</th>
                  <th className="pb-3 pr-4">Order</th>
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4">Side</th>
                  <th className="pb-3 pr-4">Price</th>
                  <th className="pb-3 pr-4">Qty</th>
                  <th className="pb-3 pr-4">Fee</th>
                  <th className="pb-3">Realized PnL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900/70 text-slate-200">
                {fills.data.items.map((fill) => (
                  <tr key={fill.order_id}>
                    <td className="py-3 pr-4">{formatDateTime(fill.event_time)}</td>
                    <td className="py-3 pr-4 font-medium text-white">{fill.order_id}</td>
                    <td className="py-3 pr-4">{fill.symbol}</td>
                    <td className="py-3 pr-4">
                      <span className={classNames('rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(fill.side))}>{fill.side}</span>
                    </td>
                    <td className="py-3 pr-4">{formatCurrency(fill.fill_price)}</td>
                    <td className="py-3 pr-4">{formatDecimal(fill.filled_quantity)}</td>
                    <td className="py-3 pr-4">{formatCurrency(fill.fee_paid)}</td>
                    <td className={classNames('py-3', pnlTone(fill.realized_pnl))}>{formatCurrency(fill.realized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </HistorySection>

        <HistorySection
          title="Runner Events"
          description="Execution lifecycle events for frontend-friendly audit trails."
          filters={eventFilters}
          onFiltersChange={setEventFilters}
          onReload={() => void loadEvents(eventFilters)}
          loading={events.loading}
          error={events.error}
          total={events.data.total}
          limit={events.data.limit}
          offset={events.data.offset}
          onPrevious={() => setEventFilters((current) => ({ ...current, offset: Math.max(current.offset - current.limit, 0) }))}
          onNext={() => setEventFilters((current) => ({ ...current, offset: current.offset + current.limit }))}
        >
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800 text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                  <th className="pb-3 pr-4">Time</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4">Message</th>
                  <th className="pb-3">Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900/70 text-slate-200">
                {events.data.items.map((eventItem, index) => (
                  <tr key={`${eventItem.event_time}-${eventItem.event_type}-${index}`}>
                    <td className="py-3 pr-4">{formatDateTime(eventItem.event_time)}</td>
                    <td className="py-3 pr-4">
                      <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                        {eventItem.event_type}
                      </span>
                    </td>
                    <td className="py-3 pr-4 font-medium text-white">{eventItem.symbol}</td>
                    <td className="py-3 pr-4">{eventItem.message}</td>
                    <td className="py-3">
                      <pre className="max-w-xl overflow-x-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-300">
                        {JSON.stringify(eventItem.payload, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </HistorySection>

        <SectionCard title="System Status" description="Useful operational context, kept subtle so trading behavior stays the focus.">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <CompactDeltaCard label="App" value={health.data?.name ?? 'Loading'} helper="Monitoring API identity" />
            <CompactDeltaCard label="Mode" value={health.data?.mode ?? 'paper'} helper="Paper-only execution" />
            <CompactDeltaCard label="Storage" value={health.data?.storage ?? 'sqlite'} helper="Local persistence backend" />
            <CompactDeltaCard label="API Status" value={health.data?.status ?? 'loading'} helper="Monitoring health" tone={health.data?.status === 'ok' ? 'positive' : 'default'} />
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

interface HistorySectionProps {
  title: string;
  description: string;
  filters: HistoryFilters;
  onFiltersChange: Dispatch<SetStateAction<HistoryFilters>>;
  onReload: () => void;
  loading: boolean;
  error: string | null;
  total: number;
  limit: number;
  offset: number;
  onPrevious: () => void;
  onNext: () => void;
  children: ReactNode;
}

function HistorySection({
  title,
  description,
  filters,
  onFiltersChange,
  onReload,
  loading,
  error,
  total,
  limit,
  offset,
  onPrevious,
  onNext,
  children,
}: HistorySectionProps) {
  return (
    <SectionCard
      title={title}
      description={description}
      action={
        <button
          type="button"
          onClick={onReload}
          className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500"
        >
          Refresh section
        </button>
      }
    >
      <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <label className="text-sm text-slate-400">
          Symbol
          <input
            value={filters.symbol}
            onChange={(event) => onFiltersChange((current) => ({ ...current, symbol: event.target.value, offset: 0 }))}
            placeholder="BTCUSDT"
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400"
          />
        </label>
        <label className="text-sm text-slate-400">
          Start date
          <input
            type="date"
            value={filters.startDate}
            onChange={(event) => onFiltersChange((current) => ({ ...current, startDate: event.target.value, offset: 0 }))}
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400"
          />
        </label>
        <label className="text-sm text-slate-400">
          End date
          <input
            type="date"
            value={filters.endDate}
            onChange={(event) => onFiltersChange((current) => ({ ...current, endDate: event.target.value, offset: 0 }))}
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400"
          />
        </label>
        <label className="text-sm text-slate-400">
          Page size
          <select
            value={filters.limit}
            onChange={(event) => onFiltersChange((current) => ({ ...current, limit: Number(event.target.value), offset: 0 }))}
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400"
          >
            {[10, 25, 50].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={() => onFiltersChange({ ...DEFAULT_FILTERS })}
            className="w-full rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500"
          >
            Reset filters
          </button>
        </div>
      </div>

      {loading ? <StatePanel title="Loading" message={`Fetching ${title.toLowerCase()}.`} /> : null}
      {error ? <StatePanel title="Request failed" message={error} tone="error" /> : null}
      {!loading && !error && total === 0 ? <StatePanel title="No results" message="No rows match the current filters." tone="empty" /> : null}
      {!loading && !error && total > 0 ? (
        <div className="space-y-4">
          {children}
          <PaginationControls total={total} limit={limit} offset={offset} onPrevious={onPrevious} onNext={onNext} />
        </div>
      ) : null}
    </SectionCard>
  );
}

export default App;


