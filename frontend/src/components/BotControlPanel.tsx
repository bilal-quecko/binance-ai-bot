import { useId, useState } from 'react';

import { badgeTone, classNames, formatDateTime } from '../lib/format';
import { canStartBot } from '../lib/bot-controls';
import type { BotStatusResponse, SpotSymbolItem } from '../lib/types';

interface BotControlPanelProps {
  searchQuery: string;
  selectedSymbol: string;
  hasValidSelection: boolean;
  symbolResults: SpotSymbolItem[];
  symbolsLoading: boolean;
  symbolsError: string | null;
  status: BotStatusResponse;
  actionLoading: boolean;
  actionError: string | null;
  onSearchChange: (value: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onClearSelection: () => void;
  onStart: () => void;
  onStop: () => void;
  onPauseResume: () => void;
  onReset: () => void;
}

export function BotControlPanel({
  searchQuery,
  selectedSymbol,
  hasValidSelection,
  symbolResults,
  symbolsLoading,
  symbolsError,
  status,
  actionLoading,
  actionError,
  onSearchChange,
  onSelectSymbol,
  onClearSelection,
  onStart,
  onStop,
  onPauseResume,
  onReset,
}: BotControlPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxId = useId();
  const canStart = hasValidSelection && canStartBot(selectedSymbol, status.state, actionLoading);
  const canStop = status.state !== 'stopped' && !actionLoading;
  const canPauseResume = (status.state === 'running' || status.state === 'paused') && !actionLoading;
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
        <div>
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
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Selected symbol</p>
              <p className="mt-2 text-lg font-semibold text-white">{selectedLabel}</p>
              <p className="mt-1 text-xs text-slate-400">{hasValidSelection ? 'Ready to start with selected symbol' : 'Pick a symbol from the dropdown to enable start'}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Current bot status</p>
              <p className="mt-2 text-lg font-semibold text-white">{status.state}</p>
              <p className="mt-1 text-xs text-slate-400">Timeframe {status.timeframe} | paper only</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Started</p>
              <p className="mt-2 text-sm text-slate-200">{formatDateTime(status.started_at)}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Last market event</p>
              <p className="mt-2 text-sm text-slate-200">{formatDateTime(status.last_event_time)}</p>
            </div>
          </div>

          {status.last_error ? <p className="text-sm text-rose-300">{status.last_error}</p> : null}
          {actionError ? <p className="text-sm text-rose-300">{actionError}</p> : null}

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
        </div>
      </div>
    </section>
  );
}
