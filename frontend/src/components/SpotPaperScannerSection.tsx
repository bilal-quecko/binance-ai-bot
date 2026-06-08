import { classNames, formatCurrency, formatDateTime, formatDecimal } from '../lib/format';
import type {
  SpotOpportunityScanJobResponse,
  SpotOpportunityScanResponse,
  SpotOpportunitySignalResponse,
} from '../lib/types';
import { AdvancedDetailsPro } from './AdvancedDetailsPro';
import { StatePanel } from './StatePanel';

interface SpotScannerFilters {
  maxSymbols: number;
  minOpportunityScore: number;
  minConfidence: number;
  horizon: string;
  includeAvoid: boolean;
}

interface SpotPaperScannerSectionProps {
  scan: SpotOpportunityScanResponse | null;
  scanJob: SpotOpportunityScanJobResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  filters: SpotScannerFilters;
  onFiltersChange: (filters: SpotScannerFilters) => void;
  onViewSignal: (symbol: string) => void;
  onSimulate: (signal: SpotOpportunitySignalResponse) => void;
  onRefresh: () => void;
  onCancelScan: () => void;
}

function humanize(value: string | null | undefined): string {
  return value ? value.replace(/_/g, ' ') : '-';
}

function actionTone(action: SpotOpportunitySignalResponse['action']): string {
  if (action === 'buy_candidate') {
    return 'border-emerald-400/35 bg-emerald-400/10 text-emerald-100';
  }
  if (action === 'exit_watch') {
    return 'border-amber-400/35 bg-amber-400/10 text-amber-100';
  }
  if (action === 'avoid') {
    return 'border-slate-700 bg-slate-900/70 text-slate-300';
  }
  return 'border-sky-400/35 bg-sky-400/10 text-sky-100';
}

function cardTone(action: SpotOpportunitySignalResponse['action']): string {
  if (action === 'buy_candidate') {
    return 'border-emerald-400/30 bg-emerald-400/10 shadow-greenGlow';
  }
  if (action === 'exit_watch') {
    return 'border-amber-400/30 bg-amber-400/10';
  }
  return 'border-borderSoft bg-cardBg/75';
}

function isActiveJob(job: SpotOpportunityScanJobResponse | null): boolean {
  return !!job && !['completed', 'failed', 'cancelled'].includes(job.status);
}

function ScannerProgress({
  active,
  scan,
  scanJob,
  maxSymbols,
}: {
  active: boolean;
  scan: SpotOpportunityScanResponse | null;
  scanJob: SpotOpportunityScanJobResponse | null;
  maxSymbols: number;
}) {
  if (!active) {
    return null;
  }
  if (scanJob && !['completed', 'failed', 'cancelled'].includes(scanJob.status)) {
    const total = scanJob.total_symbols || maxSymbols;
    return (
      <div className="mb-5 rounded-lg border border-sky-400/25 bg-sky-400/10 p-4 text-sm text-sky-100">
        <div className="flex flex-wrap items-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-transparent" />
          <div>
            <p className="font-semibold">Spot scan started</p>
            <p className="mt-1 text-xs text-sky-200">
              Scanned {scanJob.scanned_symbols}/{total}
              {scanJob.current_symbol ? ` - ${scanJob.current_symbol}` : ''} - {humanize(scanJob.current_phase)}
            </p>
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-900">
          <div
            className="h-full rounded-full bg-sky-300 transition-all"
            style={{ width: `${Math.max(4, Math.min(100, total > 0 ? (scanJob.scanned_symbols / total) * 100 : 4))}%` }}
          />
        </div>
      </div>
    );
  }
  if (scan) {
    return (
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-sky-200 border-t-transparent" />
        Updating Spot scanner
      </div>
    );
  }
  return null;
}

function SpotSignalCard({
  signal,
  onViewSignal,
  onSimulate,
}: {
  signal: SpotOpportunitySignalResponse;
  onViewSignal: (symbol: string) => void;
  onSimulate: (signal: SpotOpportunitySignalResponse) => void;
}) {
  const canSimulate = signal.action === 'buy_candidate' || signal.action === 'watch';
  return (
    <article className={classNames('rounded-lg border p-4 shadow-sm', cardTone(signal.action))}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-textPrimary">{signal.symbol}</h3>
            <span className={classNames('rounded-md border px-3 py-1 text-xs font-semibold uppercase', actionTone(signal.action))}>
              {humanize(signal.action)}
            </span>
            <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1 text-xs font-semibold text-textSecondary">
              Validation {signal.validation_score !== null ? `${signal.validation_score}%` : 'pending'}
            </span>
            <span className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-300">
              Paper Only
            </span>
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-textSecondary">{signal.reason}</p>
        </div>
        <div className="grid min-w-40 grid-cols-2 gap-3 text-right">
          <div className="rounded-md border border-borderSoft bg-panelBg/70 p-3">
            <p className="text-2xl font-semibold text-textPrimary">{signal.opportunity_score}</p>
            <p className="text-xs text-textMuted">Score</p>
          </div>
          <div className="rounded-md border border-borderSoft bg-panelBg/70 p-3">
            <p className="text-2xl font-semibold text-textPrimary">{signal.confidence}%</p>
            <p className="text-xs text-textMuted">Confidence</p>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 text-sm text-textSecondary sm:grid-cols-2 lg:grid-cols-5">
        <div><span className="text-textMuted">Spot Price</span><p className="font-semibold text-textPrimary">{signal.current_price ? formatCurrency(signal.current_price) : '-'}</p></div>
        <div><span className="text-textMuted">Entry</span><p>{signal.suggested_entry_zone ?? '-'}</p></div>
        <div><span className="text-textMuted">Stop</span><p>{signal.suggested_stop_loss ? formatDecimal(signal.suggested_stop_loss) : '-'}</p></div>
        <div><span className="text-textMuted">Take Profit</span><p>{signal.suggested_take_profit ? formatDecimal(signal.suggested_take_profit) : '-'}</p></div>
        <div><span className="text-textMuted">Risk</span><p>{signal.risk_grade}</p></div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onViewSignal(signal.symbol)}
          className="rounded-md border border-accentPurple/35 bg-accentPurple/15 px-3 py-2 text-sm font-medium text-violet-100 transition hover:border-accentPurple hover:bg-accentPurple/25"
        >
          View Signal
        </button>
        <button
          type="button"
          disabled={!canSimulate}
          onClick={() => onSimulate(signal)}
          className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-2 text-sm font-medium text-textSecondary transition hover:border-borderMedium hover:text-textPrimary disabled:cursor-not-allowed disabled:opacity-50"
        >
          Simulate Spot Paper Trade
        </button>
        <span className="text-xs text-textMuted">Spot only | Advisory only | No real orders</span>
      </div>

      <AdvancedDetailsPro>
        <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
          <div><span className="text-slate-500">Trend</span><p>{humanize(signal.trend)}</p></div>
          <div><span className="text-slate-500">Momentum</span><p>{humanize(signal.momentum)}</p></div>
          <div><span className="text-slate-500">Regime</span><p>{humanize(signal.regime)}</p></div>
          <div><span className="text-slate-500">Evidence</span><p>{humanize(signal.evidence_strength)}</p></div>
          <div><span className="text-slate-500">Trend Score</span><p>{signal.trend_score}</p></div>
          <div><span className="text-slate-500">Momentum Score</span><p>{signal.momentum_score}</p></div>
          <div><span className="text-slate-500">Structure Score</span><p>{signal.structure_score}</p></div>
          <div><span className="text-slate-500">Eligibility Score</span><p>{signal.eligibility_score}</p></div>
          <div><span className="text-slate-500">Data Source</span><p>{humanize(signal.data_source)}</p></div>
          <div><span className="text-slate-500">Scan Time</span><p>{formatDateTime(signal.timestamp)}</p></div>
        </div>
        {signal.warnings.length > 0 ? (
          <div className="mt-3 space-y-1 text-xs text-amber-200">
            {signal.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        ) : null}
      </AdvancedDetailsPro>
    </article>
  );
}

function CandidateGroup({
  title,
  items,
  empty,
  onViewSignal,
  onSimulate,
}: {
  title: string;
  items: SpotOpportunitySignalResponse[];
  empty: string;
  onViewSignal: (symbol: string) => void;
  onSimulate: (signal: SpotOpportunitySignalResponse) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      {items.length === 0 ? (
        <StatePanel title={empty} message="No Spot candidates matched the current filters." tone="empty" />
      ) : (
        <div className="grid gap-3">
          {items.map((signal) => (
            <SpotSignalCard
              key={`${signal.symbol}-${signal.action}`}
              signal={signal}
              onViewSignal={onViewSignal}
              onSimulate={onSimulate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function SpotPaperScannerSection({
  scan,
  scanJob,
  loading,
  refreshing,
  error,
  filters,
  onFiltersChange,
  onViewSignal,
  onSimulate,
  onRefresh,
  onCancelScan,
}: SpotPaperScannerSectionProps) {
  const activeJob = isActiveJob(scanJob);
  if (error && !scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <StatePanel title="No Spot scanner results yet" message={error} tone="empty" />
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing || loading || activeJob}
          className="mt-4 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Retry Spot Scanner
        </button>
      </section>
    );
  }
  if (loading && !scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <ScannerProgress active scan={scan} scanJob={scanJob} maxSymbols={filters.maxSymbols} />
        <StatePanel title="Loading Spot scanner" message="Scanning Binance Spot USDT symbols for paper-only buy/watch opportunities." tone="loading" />
        {activeJob ? (
          <button type="button" onClick={onCancelScan} className="mt-4 rounded-lg border border-amber-400/35 bg-amber-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-amber-100">
            Cancel Scan
          </button>
        ) : null}
      </section>
    );
  }
  if (!scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <StatePanel title="No Spot scanner results yet" message="Run the Spot scanner to rank buy candidates, watch names, and avoid symbols." tone="empty" />
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing || loading || activeJob}
          className="mt-4 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Run Spot Scanner
        </button>
      </section>
    );
  }

  const candidateCount = scan.buy_candidates.length + scan.watch_candidates.length + scan.exit_watch_candidates.length + scan.avoid_candidates.length;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">Spot Paper Scanner</p>
          <h2 className="mt-2 text-xl font-semibold text-white">Buy Candidate Intelligence</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            Spot Paper Mode - Advisory Only - No Real Orders - Buy/Watch/Avoid Ranking
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">{scan.scan_state}</span>
          {error ? <span className="rounded-full border border-amber-400/35 bg-amber-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-amber-100">last refresh failed</span> : null}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing || loading || activeJob}
            className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {activeJob || refreshing || loading ? 'Scanning...' : 'Refresh'}
          </button>
          {activeJob ? (
            <button type="button" onClick={onCancelScan} className="rounded-lg border border-amber-400/35 bg-amber-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-amber-100">
              Cancel Scan
            </button>
          ) : null}
        </div>
      </div>

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-2 xl:grid-cols-5">
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Min Opportunity</span>
          <input type="number" min={0} max={100} value={filters.minOpportunityScore} onChange={(event) => onFiltersChange({ ...filters, minOpportunityScore: Number(event.target.value) })} className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white" />
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Min Confidence</span>
          <input type="number" min={0} max={100} value={filters.minConfidence} onChange={(event) => onFiltersChange({ ...filters, minConfidence: Number(event.target.value) })} className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white" />
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Max Symbols</span>
          <select value={filters.maxSymbols} onChange={(event) => onFiltersChange({ ...filters, maxSymbols: Number(event.target.value) })} className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white">
            <option value={20}>20 symbols</option>
            <option value={50}>50 symbols</option>
            <option value={100}>100 symbols</option>
          </select>
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Horizon</span>
          <select value={filters.horizon} onChange={(event) => onFiltersChange({ ...filters, horizon: event.target.value })} className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white">
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="7d">7d</option>
          </select>
        </label>
        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={filters.includeAvoid} onChange={(event) => onFiltersChange({ ...filters, includeAvoid: event.target.checked })} />
            Include AVOID
          </label>
        </div>
      </div>

      <ScannerProgress active={loading || refreshing || activeJob} scan={scan} scanJob={scanJob} maxSymbols={filters.maxSymbols} />

      {scan.warnings.length > 0 ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          {scan.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Scanned</span><p className="mt-1 text-lg font-semibold text-white">{scan.scanned_count}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">BUY</span><p className="mt-1 text-lg font-semibold text-emerald-300">{scan.buy_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">WATCH</span><p className="mt-1 text-lg font-semibold text-sky-300">{scan.watch_candidates.length + scan.exit_watch_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Candidates</span><p className="mt-1 text-lg font-semibold text-white">{candidateCount}</p></div>
      </div>

      <AdvancedDetailsPro>
        <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
          <div><span className="text-slate-500">Data Source</span><p>{humanize(scan.data_source)}</p></div>
          <div><span className="text-slate-500">Quote Asset</span><p>{scan.quote_asset}</p></div>
          <div><span className="text-slate-500">Symbol Count</span><p>{scan.symbol_count}</p></div>
          <div><span className="text-slate-500">Persisted Candidates</span><p>{scan.persisted_candidate_count}</p></div>
          <div><span className="text-slate-500">Last Successful Scan</span><p>{scan.latest_successful_scanner_at ? formatDateTime(scan.latest_successful_scanner_at) : '-'}</p></div>
          <div><span className="text-slate-500">Latest Error</span><p>{scan.latest_error ?? '-'}</p></div>
        </div>
      </AdvancedDetailsPro>

      <div className="grid gap-5 xl:grid-cols-2">
        <CandidateGroup title="Top BUY Candidates" items={scan.buy_candidates} empty="No BUY candidates" onViewSignal={onViewSignal} onSimulate={onSimulate} />
        <CandidateGroup title="WATCH" items={[...scan.watch_candidates, ...scan.exit_watch_candidates]} empty="No WATCH candidates" onViewSignal={onViewSignal} onSimulate={onSimulate} />
      </div>

      {filters.includeAvoid ? (
        <div className="mt-5">
          <CandidateGroup title="AVOID" items={scan.avoid_candidates.slice(0, 6)} empty="No AVOID candidates" onViewSignal={onViewSignal} onSimulate={onSimulate} />
        </div>
      ) : null}
    </section>
  );
}
