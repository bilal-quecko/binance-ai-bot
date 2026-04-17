import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { HorizontalBars } from './components/HorizontalBars';
import { LineChart } from './components/LineChart';
import { MetricCard } from './components/MetricCard';
import { PaginationControls } from './components/PaginationControls';
import { SectionCard } from './components/SectionCard';
import { StatePanel } from './components/StatePanel';
import {
  getEquity,
  getEvents,
  getFills,
  getHealth,
  getMetrics,
  getPositions,
  getRecentDailyPnl,
  getSymbolSummaries,
  getTrades,
} from './lib/api';
import { badgeTone, classNames, formatCurrency, formatDateTime, formatDecimal, pnlTone } from './lib/format';
import type {
  DailyPnlPoint,
  EquityResponse,
  EventItem,
  FillItem,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  PaginatedResponse,
  PositionItem,
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

function createAsyncState<T>(data: T): AsyncState<T> {
  return {
    data,
    loading: true,
    error: null,
  };
}

function App() {
  const [health, setHealth] = useState<AsyncState<HealthResponse | null>>(createAsyncState<HealthResponse | null>(null));
  const [metrics, setMetrics] = useState<AsyncState<MetricsResponse>>(createAsyncState(INITIAL_METRICS));
  const [equity, setEquity] = useState<AsyncState<EquityResponse>>(createAsyncState(INITIAL_EQUITY));
  const [positions, setPositions] = useState<AsyncState<PositionItem[]>>(createAsyncState<PositionItem[]>([]));
  const [summaries, setSummaries] = useState<AsyncState<SymbolSummaryItem[]>>(createAsyncState<SymbolSummaryItem[]>([]));
  const [dailyPnl, setDailyPnl] = useState<AsyncState<DailyPnlPoint[]>>(createAsyncState<DailyPnlPoint[]>([]));
  const [summarySymbols, setSummarySymbols] = useState('');

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
    setMetrics((current) => ({ ...current, loading: true, error: null }));
    setEquity((current) => ({ ...current, loading: true, error: null }));
    setPositions((current) => ({ ...current, loading: true, error: null }));
    setSummaries((current) => ({ ...current, loading: true, error: null }));
    setDailyPnl((current) => ({ ...current, loading: true, error: null }));

    const summarySymbolList = symbolsInput
      .split(',')
      .map((symbol) => symbol.trim())
      .filter((symbol) => symbol.length > 0);

    try {
      const [healthData, metricsData, equityData, positionsData, summaryData, pnlSeries] = await Promise.all([
        getHealth(),
        getMetrics(),
        getEquity(),
        getPositions(),
        getSymbolSummaries(summarySymbolList),
        getRecentDailyPnl(7),
      ]);
      setHealth({ data: healthData, loading: false, error: null });
      setMetrics({ data: metricsData, loading: false, error: null });
      setEquity({ data: equityData, loading: false, error: null });
      setPositions({ data: positionsData, loading: false, error: null });
      setSummaries({ data: summaryData, loading: false, error: null });
      setDailyPnl({ data: pnlSeries, loading: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading overview data.';
      setHealth((current) => ({ ...current, loading: false, error: message }));
      setMetrics((current) => ({ ...current, loading: false, error: message }));
      setEquity((current) => ({ ...current, loading: false, error: message }));
      setPositions((current) => ({ ...current, loading: false, error: message }));
      setSummaries((current) => ({ ...current, loading: false, error: message }));
      setDailyPnl((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  const loadTrades = useCallback(async (filters: HistoryFilters) => {
    setTrades((current) => ({ ...current, loading: true, error: null }));
    try {
      const tradeData = await getTrades(filters);
      setTrades({ data: tradeData, loading: false, error: null });
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
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error while loading events.';
      setEvents((current) => ({ ...current, loading: false, error: message }));
    }
  }, []);

  useEffect(() => {
    void loadOverview(summarySymbols);
  }, [loadOverview, summarySymbols]);

  useEffect(() => {
    void loadTrades(tradeFilters);
  }, [loadTrades, tradeFilters]);

  useEffect(() => {
    void loadFills(fillFilters);
  }, [fillFilters, loadFills]);

  useEffect(() => {
    void loadEvents(eventFilters);
  }, [eventFilters, loadEvents]);

  const summaryBarItems = useMemo(
    () => summaries.data.map((item) => ({ label: item.symbol, value: Number(item.realized_pnl) })),
    [summaries.data],
  );

  const dailyPnlValues = dailyPnl.data.map((point) => point.value);
  const dailyPnlLabels = dailyPnl.data.map((point) => point.day);

  const refreshAll = () => {
    void loadOverview(summarySymbols);
    void loadTrades(tradeFilters);
    void loadFills(fillFilters);
    void loadEvents(eventFilters);
  };

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
            <button
              type="button"
              onClick={refreshAll}
              className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 font-medium text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20"
            >
              Refresh data
            </button>
          </div>
        </header>

        {health.error ? <StatePanel title="API error" message={health.error} tone="error" /> : null}

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
            helper={`Max win streak ${metrics.data.max_winning_streak} - max loss streak ${metrics.data.max_losing_streak}`}
          />
        </section>

        <div className="grid gap-6 xl:grid-cols-[1.5fr,1fr]">
          <SectionCard title="Daily PnL Trend" description="Last 7 UTC days using the existing /daily-pnl endpoint.">
            {dailyPnl.loading ? (
              <StatePanel title="Loading" message="Fetching recent daily PnL values." />
            ) : dailyPnl.error ? (
              <StatePanel title="Chart unavailable" message={dailyPnl.error} tone="error" />
            ) : (
              <LineChart title="Daily PnL" values={dailyPnlValues} labels={dailyPnlLabels} stroke="#38bdf8" fill="#38bdf8" />
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
        </div>

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

        <div className="grid gap-6 xl:grid-cols-3">
          <SectionCard title="Current Positions" description="Open exposure from the latest persisted position snapshots.">
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

          <SectionCard title="System Health" description="FastAPI health and monitoring backend readiness.">
            {health.loading ? (
              <StatePanel title="Loading" message="Checking backend health endpoint." />
            ) : health.error ? (
              <StatePanel title="Backend unavailable" message={health.error} tone="error" />
            ) : health.data ? (
              <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">App name</span>
                  <span className="font-medium text-white">{health.data.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Mode</span>
                  <span className="font-medium text-white">{health.data.mode}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Storage</span>
                  <span className="font-medium text-white">{health.data.storage}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Status</span>
                  <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(health.data.status))}>
                    {health.data.status}
                  </span>
                </div>
              </div>
            ) : null}
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


