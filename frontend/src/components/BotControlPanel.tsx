import { useId, useState } from 'react';

import { badgeTone, classNames, formatDateTime } from '../lib/format';
import { canStartBot } from '../lib/bot-controls';
import { SymbolCandlestickChart } from './SymbolCandlestickChart';
import type { BotStatusResponse, CandleHistoryResponse, SpotSymbolItem, TechnicalAnalysisResponse, TradingProfile } from '../lib/types';

interface BotControlPanelProps {
  searchQuery: string;
  selectedSymbol: string;
  hasValidSelection: boolean;
  tradingProfile: TradingProfile;
  onTradingProfileChange: (profile: TradingProfile) => void;
  symbolResults: SpotSymbolItem[];
  symbolsLoading: boolean;
  symbolsError: string | null;
  chart: CandleHistoryResponse | null;
  chartLoading: boolean;
  chartError: string | null;
  chartTimeframe: '1m' | '5m' | '15m' | '1h';
  onChartTimeframeChange: (timeframe: '1m' | '5m' | '15m' | '1h') => void;
  technicalAnalysis: TechnicalAnalysisResponse | null;
  status: BotStatusResponse;
  actionLoading: boolean;
  actionError: string | null;
  actionMessage: string | null;
  hasOpenPosition: boolean;
  onSearchChange: (value: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onClearSelection: () => void;
  onStart: () => void;
  onStop: () => void;
  onPauseResume: () => void;
  onManualBuy: () => void;
  onManualClose: () => void;
  onReset: () => void;
}

function persistenceLabel(state: BotStatusResponse['persistence']['persistence_state']): string {
  if (state === 'healthy') {
    return 'Healthy';
  }
  if (state === 'recovered_from_persistence') {
    return 'Recovered';
  }
  if (state === 'degraded_in_memory_only') {
    return 'In memory only';
  }
  return 'Unavailable';
}

export function BotControlPanel({
  searchQuery,
  selectedSymbol,
  hasValidSelection,
  tradingProfile,
  onTradingProfileChange,
  symbolResults,
  symbolsLoading,
  symbolsError,
  chart,
  chartLoading,
  chartError,
  chartTimeframe,
  onChartTimeframeChange,
  technicalAnalysis,
  status,
  actionLoading,
  actionError,
  actionMessage,
  hasOpenPosition,
  onSearchChange,
  onSelectSymbol,
  onClearSelection,
  onStart,
  onStop,
  onPauseResume,
  onManualBuy,
  onManualClose,
  onReset,
}: BotControlPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxId = useId();
  const canStart = hasValidSelection && canStartBot(selectedSymbol, status.state, actionLoading);
  const canStop = status.state !== 'stopped' && !actionLoading;
  const canPauseResume = (status.state === 'running' || status.state === 'paused') && !actionLoading;
  const canManualTrade = !actionLoading && selectedSymbol.length > 0 && status.symbol === selectedSymbol && (status.state === 'running' || status.state === 'paused');
  const pauseResumeLabel = status.state === 'paused' ? 'Resume' : 'Pause';
  const selectedLabel = selectedSymbol || status.symbol || '-';
  const showNoMatches = !symbolsLoading && !symbolsError && isOpen && searchQuery.trim().length > 0 && symbolResults.length === 0;
  const showEmptyPopularState = !symbolsLoading && !symbolsError && isOpen && searchQuery.trim().length === 0 && symbolResults.length === 0;

  return (
    <section className="rounded-2xl border border-slate-800/80 bg-slate-900/80 p-5 shadow-glow backdrop-blur">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Live Paper Controls</h2>
          <p className="mt-1 text-sm text-slate-400">Select one live Binance Spot USDT symbol, then start, pause, resume, or stop paper trading without enabling live order placement.</p>
        </div>
        <div className="shrink-0">
          <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(status.state === 'running' ? 'approve' : status.state === 'paused' ? 'HOLD' : status.state === 'error' ? 'reject' : 'skipped'))}>
            {status.state}
          </span>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <div className="space-y-4">
          <div
            className="relative"
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setIsOpen(false);
              }
            }}
          >
            <label className="text-sm text-slate-400">
              Search live Spot symbol
              <div className="relative mt-2">
                <input
                  role="combobox"
                  aria-autocomplete="list"
                  aria-expanded={isOpen}
                  aria-controls={listboxId}
                  value={searchQuery}
                  onFocus={() => {
                    setIsOpen(true);
                    setActiveIndex(0);
                  }}
                  onChange={(event) => {
                    setIsOpen(true);
                    setActiveIndex(0);
                    onSearchChange(event.target.value);
                  }}
                  onKeyDown={(event) => {
                    if (!isOpen || symbolResults.length === 0) {
                      if (event.key === 'ArrowDown') {
                        setIsOpen(true);
                      }
                      return;
                    }
                    if (event.key === 'ArrowDown') {
                      event.preventDefault();
                      setActiveIndex((current) => (current + 1) % symbolResults.length);
                      return;
                    }
                    if (event.key === 'ArrowUp') {
                      event.preventDefault();
                      setActiveIndex((current) => (current - 1 + symbolResults.length) % symbolResults.length);
                      return;
                    }
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      const nextSelection = symbolResults[activeIndex];
                      if (nextSelection) {
                        onSelectSymbol(nextSelection.symbol);
                        setIsOpen(false);
                      }
                      return;
                    }
                    if (event.key === 'Escape') {
                      setIsOpen(false);
                    }
                  }}
                  placeholder="BTCUSDT"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 pr-11 text-sm text-slate-100 outline-none transition focus:border-sky-400"
                />
                {searchQuery.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => {
                      onClearSelection();
                      setIsOpen(true);
                      setActiveIndex(0);
                    }}
                    className="absolute inset-y-0 right-2 my-auto h-7 rounded-lg px-2 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white"
                  >
                    Clear
                  </button>
                ) : null}
              </div>
            </label>

            {isOpen ? (
              <div
                id={listboxId}
                role="listbox"
                className="absolute z-20 mt-2 max-h-72 w-full overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950/95 p-2 shadow-2xl backdrop-blur"
              >
                {symbolsLoading ? (
                  <p className="px-3 py-3 text-sm text-slate-400">Loading live Spot symbols...</p>
                ) : symbolsError ? (
                  <p className="px-3 py-3 text-sm text-rose-300">{symbolsError}</p>
                ) : showNoMatches ? (
                  <p className="px-3 py-3 text-sm text-slate-400">No matching tradable USDT Spot pairs found.</p>
                ) : showEmptyPopularState ? (
                  <p className="px-3 py-3 text-sm text-slate-400">No active tradable USDT Spot pairs are available right now.</p>
                ) : (
                  <div className="space-y-1">
                    {symbolResults.map((item, index) => (
                      <button
                        key={item.symbol}
                        role="option"
                        aria-selected={selectedSymbol === item.symbol}
                        type="button"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          onSelectSymbol(item.symbol);
                          setIsOpen(false);
                        }}
                        className={classNames(
                          'flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left text-sm transition',
                          activeIndex === index
                            ? 'border-slate-700 bg-slate-900 text-white'
                            : '',
                          selectedSymbol === item.symbol
                            ? 'border-sky-400/50 bg-sky-400/10 text-sky-100'
                            : 'border-transparent bg-slate-900/70 text-slate-200 hover:border-slate-700 hover:bg-slate-900',
                        )}
                        onMouseEnter={() => setActiveIndex(index)}
                      >
                        <span className="font-medium">{item.symbol}</span>
                        <span className="text-xs uppercase tracking-[0.16em] text-slate-500">
                          {item.base_asset}/{item.quote_asset}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Chart timeframe</p>
                <p className="mt-1 text-sm text-slate-400">Recent closed candles with support, resistance, breakout, and reversal context.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {(['1m', '5m', '15m', '1h'] as const).map((timeframe) => (
                  <button
                    key={timeframe}
                    type="button"
                    onClick={() => onChartTimeframeChange(timeframe)}
                    className={classNames(
                      'rounded-xl border px-3 py-2 text-sm font-medium transition',
                      chartTimeframe === timeframe
                        ? 'border-sky-400/40 bg-sky-400/10 text-sky-100'
                        : 'border-slate-700 bg-slate-950/60 text-slate-300 hover:border-slate-500 hover:text-white',
                    )}
                  >
                    {timeframe}
                  </button>
                ))}
              </div>
            </div>

            <SymbolCandlestickChart
              symbol={selectedLabel === '-' ? '' : selectedLabel}
              timeframe={chartTimeframe}
              chart={chart}
              chartLoading={chartLoading}
              chartError={chartError}
              technicalAnalysis={technicalAnalysis}
            />
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trading profile</p>
              <div className="mt-2">
                <select
                  value={tradingProfile}
                  onChange={(event) => onTradingProfileChange(event.target.value as TradingProfile)}
                  disabled={actionLoading || status.state !== 'stopped'}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <option value="conservative">Conservative</option>
                  <option value="balanced">Balanced</option>
                  <option value="aggressive">Aggressive</option>
                </select>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {status.state === 'stopped'
                  ? 'Selected profile will be applied on the next start.'
                  : `Runtime is using ${status.trading_profile}. Stop the runtime to switch profiles.`}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Selected symbol</p>
              <p className="mt-2 text-lg font-semibold text-white">{selectedLabel}</p>
              <p className="mt-1 text-xs text-slate-400">{hasValidSelection ? 'Ready to start with selected symbol' : 'Pick a symbol from the dropdown to enable start'}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Current bot status</p>
              <p className="mt-2 text-lg font-semibold text-white">{status.state}</p>
              <p className="mt-1 text-xs text-slate-400">Mode {status.mode} | profile {status.trading_profile} | timeframe {status.timeframe} | paper only</p>
              <p className="mt-1 text-xs text-slate-500">
                {status.tuning_version_id
                  ? `Applied tuning ${status.tuning_version_id}`
                  : 'Using built-in profile defaults'}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Started</p>
              <p className="mt-2 text-sm text-slate-200">{formatDateTime(status.started_at)}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Session</p>
              <p className="mt-2 text-sm text-slate-200">{status.session_id ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Last market event</p>
              <p className="mt-2 text-sm text-slate-200">{formatDateTime(status.last_event_time)}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recovery state</p>
              <p className="mt-2 text-sm text-slate-200">
                {status.recovered_from_prior_session ? 'Recovered session' : 'Fresh session'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {status.broker_state_restored ? 'Broker state restored' : 'No recovered broker state'}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Persistence</p>
              <p className="mt-2 text-sm text-slate-200">{persistenceLabel(status.persistence.persistence_state)}</p>
              <p className="mt-1 text-xs text-slate-400">{status.persistence.persistence_message}</p>
            </div>
          </div>

          {status.last_error ? <p className="text-sm text-rose-300">{status.last_error}</p> : null}
          {status.recovery_message ? <p className="text-sm text-amber-300">{status.recovery_message}</p> : null}
          {actionError ? <p className="text-sm text-rose-300">{actionError}</p> : null}
          {actionMessage ? <p className="text-sm text-emerald-300">{actionMessage}</p> : null}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!canStart}
              onClick={onStart}
              className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-emerald-300 hover:bg-emerald-400/20"
            >
              Start
            </button>
            <button
              type="button"
              disabled={!canStop}
              onClick={onStop}
              className="rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-2 text-sm font-medium text-rose-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-rose-300 hover:bg-rose-400/20"
            >
              Stop
            </button>
            <button
              type="button"
              disabled={!canPauseResume}
              onClick={onPauseResume}
              className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm font-medium text-amber-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-amber-300 hover:bg-amber-400/20"
            >
              {pauseResumeLabel}
            </button>
            <button
              type="button"
              disabled={actionLoading}
              onClick={onReset}
              className="rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-slate-500 hover:text-white"
            >
              Reset Session
            </button>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Manual Paper Participation</p>
            <p className="mt-2 text-sm text-slate-400">
              Manual paper orders stay paper-only and still use the safe execution path when live runtime data is ready.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!canManualTrade}
                onClick={onManualBuy}
                className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-sm font-medium text-sky-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-sky-300 hover:bg-sky-400/20"
              >
                Buy Market
              </button>
              <button
                type="button"
                disabled={!canManualTrade || !hasOpenPosition}
                onClick={onManualClose}
                className="rounded-xl border border-violet-400/30 bg-violet-400/10 px-4 py-2 text-sm font-medium text-violet-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-violet-300 hover:bg-violet-400/20"
              >
                Sell / Close Position
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {canManualTrade
                ? hasOpenPosition
                  ? 'Manual buy and close are available for the active paper runtime.'
                  : 'Manual buy is available. Close activates after a paper position opens.'
                : 'Start or attach the live runtime for the selected symbol before manual paper trading can act.'}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
