import { classNames, formatCurrency, formatDateTime, formatDecimal } from '../lib/format';
import type { FuturesOpportunityScanResponse, FuturesPaperSignalResponse } from '../lib/types';
import { StatePanel } from './StatePanel';

interface FuturesScannerFilters {
  maxSymbols: number;
  minOpportunityScore: number;
  includeWeakEvidence: boolean;
  horizon: string;
  includeAvoid: boolean;
}

interface FuturesPaperScannerSectionProps {
  scan: FuturesOpportunityScanResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  filters: FuturesScannerFilters;
  onFiltersChange: (filters: FuturesScannerFilters) => void;
  onRefresh: () => void;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.replace(/_/g, ' ');
}

function cardTone(direction: FuturesPaperSignalResponse['direction']): string {
  if (direction === 'long') {
    return 'border-emerald-500/30 bg-emerald-500/10';
  }
  if (direction === 'short') {
    return 'border-rose-500/30 bg-rose-500/10';
  }
  return 'border-slate-800 bg-slate-950/60';
}

function badgeTone(direction: FuturesPaperSignalResponse['direction']): string {
  if (direction === 'long') {
    return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100';
  }
  if (direction === 'short') {
    return 'border-rose-400/40 bg-rose-400/10 text-rose-100';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-200';
}

function SignalCard({ signal }: { signal: FuturesPaperSignalResponse }) {
  return (
    <article className={classNames('rounded-lg border p-4', cardTone(signal.direction))}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={classNames('rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]', badgeTone(signal.direction))}>
              {signal.direction}
            </span>
            <h3 className="text-lg font-semibold text-white">{signal.symbol}</h3>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-300">{signal.reason}</p>
        </div>
        <div className="text-right text-xs text-slate-400">
          <p className="text-lg font-semibold text-white">{signal.opportunity_score}</p>
          <p>opportunity score</p>
          <p className="mt-1">{signal.confidence}% confidence</p>
          <p className="mt-1">{formatDateTime(signal.timestamp)}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
        <div><span className="text-slate-500">Price</span><p>{signal.current_price ? formatCurrency(signal.current_price) : '-'}</p></div>
        <div><span className="text-slate-500">Trend</span><p>{humanize(signal.trend)}</p></div>
        <div><span className="text-slate-500">Momentum</span><p>{humanize(signal.momentum)}</p></div>
        <div><span className="text-slate-500">Horizon</span><p>{signal.best_horizon}</p></div>
        <div><span className="text-slate-500">Evidence</span><p>{humanize(signal.evidence_strength)}</p></div>
        <div><span className="text-slate-500">Risk</span><p>{signal.risk_grade}</p></div>
        <div><span className="text-slate-500">Stop</span><p>{signal.suggested_stop_loss ? formatDecimal(signal.suggested_stop_loss) : '-'}</p></div>
        <div><span className="text-slate-500">Take Profit</span><p>{signal.suggested_take_profit ? formatDecimal(signal.suggested_take_profit) : '-'}</p></div>
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-3 xl:grid-cols-6">
        <p>Trend {signal.trend_score}</p>
        <p>Momentum {signal.momentum_score}</p>
        <p>Direction {signal.direction_score}</p>
        <p>Volatility {signal.volatility_quality_score}</p>
        <p>Liquidity {signal.liquidity_score}</p>
        <p>Validation {signal.validation_score ?? '-'}</p>
      </div>

      <div className="mt-4 grid gap-3 text-xs text-slate-400 lg:grid-cols-2">
        <p>{signal.invalidation_hint ?? 'No invalidation level is available yet.'}</p>
        <p>{signal.liquidation_safety_note}</p>
      </div>
      {signal.warnings.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {signal.warnings.slice(0, 3).map((warning) => (
            <span key={warning} className="rounded-full border border-amber-400/25 px-3 py-1 text-xs text-amber-100">
              {warning}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function CandidateGroup({ title, items, empty }: { title: string; items: FuturesPaperSignalResponse[]; empty: string }) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      {items.length === 0 ? (
        <StatePanel title={empty} message="No high-quality candidates matched the current filters." tone="empty" />
      ) : (
        <div className="grid gap-3">
          {items.map((signal) => <SignalCard key={`${signal.symbol}-${signal.direction}`} signal={signal} />)}
        </div>
      )}
    </div>
  );
}

function ScannerProgress({
  active,
  scan,
  maxSymbols,
}: {
  active: boolean;
  scan: FuturesOpportunityScanResponse | null;
  maxSymbols: number;
}) {
  if (!active) {
    return null;
  }
  const scanned = scan?.scanned_count ?? 0;
  const phase = scan ? 'Refreshing Binance candles and rankings' : 'Preparing symbol universe';
  return (
    <div className="mb-5 rounded-lg border border-sky-400/25 bg-sky-400/10 p-4 text-sm text-sky-100">
      <div className="flex flex-wrap items-center gap-3">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-transparent" />
        <div>
          <p className="font-semibold">{phase}</p>
          <p className="mt-1 text-xs text-sky-200">Scanned {scanned} / {maxSymbols} symbols. Existing partial results stay visible while the next scan runs.</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-sky-200 sm:grid-cols-2 lg:grid-cols-4">
        <span>Fetching Binance candles</span>
        <span>Analyzing trend and momentum</span>
        <span>Ranking LONG candidates</span>
        <span>Ranking SHORT candidates</span>
      </div>
    </div>
  );
}

export function FuturesPaperScannerSection({
  scan,
  loading,
  refreshing,
  error,
  filters,
  onFiltersChange,
  onRefresh,
}: FuturesPaperScannerSectionProps) {
  if (error) {
    return <StatePanel title="Futures paper scanner unavailable" message={error} tone="error" />;
  }
  if (loading && !scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <ScannerProgress active scan={scan} maxSymbols={filters.maxSymbols} />
        <StatePanel title="Loading futures paper scanner" message="Scanning symbols for advisory long/short paper opportunities." tone="loading" />
      </section>
    );
  }
  if (!scan) {
    return <StatePanel title="No futures paper scan yet" message="Refresh the scanner to rank paper-only long/short opportunities." tone="empty" />;
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Futures Paper Scanner</p>
          <h2 className="mt-2 text-xl font-semibold text-white">Long/Short Opportunity Intelligence</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            Paper Futures Mode - Advisory Only - No Real Orders - Long/Short Simulation
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
            {scan.scan_state}
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing || loading}
            className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing || loading ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Min Opportunity</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.minOpportunityScore}
            onChange={(event) => onFiltersChange({ ...filters, minOpportunityScore: Number(event.target.value) })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          />
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Max Symbols</span>
          <input
            type="number"
            min={1}
            max={50}
            value={filters.maxSymbols}
            onChange={(event) => onFiltersChange({ ...filters, maxSymbols: Number(event.target.value) })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          />
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Horizon</span>
          <select
            value={filters.horizon}
            onChange={(event) => onFiltersChange({ ...filters, horizon: event.target.value })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="7d">7d</option>
          </select>
        </label>
        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={filters.includeWeakEvidence}
              onChange={(event) => onFiltersChange({ ...filters, includeWeakEvidence: event.target.checked })}
            />
            Include weak evidence
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={filters.includeAvoid}
              onChange={(event) => onFiltersChange({ ...filters, includeAvoid: event.target.checked })}
            />
            Include WAIT/AVOID
          </label>
        </div>
      </div>

      <ScannerProgress active={loading || refreshing} scan={scan} maxSymbols={filters.maxSymbols} />

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Scanned</span><p className="mt-1 text-lg font-semibold text-white">{scan.scanned_count}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">LONG</span><p className="mt-1 text-lg font-semibold text-emerald-300">{scan.long_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">SHORT</span><p className="mt-1 text-lg font-semibold text-rose-300">{scan.short_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Max Leverage</span><p className="mt-1 text-lg font-semibold text-white">{scan.max_leverage_suggestion}</p></div>
      </div>

      {scan.warnings.length > 0 ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          {scan.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-2">
        <CandidateGroup title="Top LONG Candidates" items={scan.long_candidates} empty="No LONG candidates" />
        <CandidateGroup title="Top SHORT Candidates" items={scan.short_candidates} empty="No SHORT candidates" />
      </div>

      <div className="mt-5">
        <CandidateGroup title="WAIT / AVOID" items={scan.neutral_candidates.slice(0, 6)} empty="No neutral candidates" />
      </div>
    </section>
  );
}
