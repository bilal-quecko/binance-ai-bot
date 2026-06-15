import { StatePanel } from './StatePanel';
import { formatDateTime, formatDecimal } from '../lib/format';
import type { ScannerValidationGroupPerformance, ScannerValidationReportResponse } from '../lib/types';

interface ScannerValidationReportSectionProps {
  report: ScannerValidationReportResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  evaluating: boolean;
  evaluateMessage: string | null;
  evaluateError: string | null;
  onRefresh: () => void;
  onEvaluate: () => void;
}

function pct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Collect signals';
  }
  return `${formatDecimal(value)}%`;
}

function signedPct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Collect signals';
  }
  const numeric = Number(value);
  return `${numeric > 0 ? '+' : ''}${formatDecimal(value)}%`;
}

function conclusionTone(conclusion: string): string {
  if (conclusion === 'strong' || conclusion === 'promising') {
    return 'text-emerald-300';
  }
  if (conclusion === 'weak') {
    return 'text-rose-300';
  }
  if (conclusion === 'mixed') {
    return 'text-amber-300';
  }
  return 'text-slate-300';
}

function GroupList({ title, items }: { title: string; items: ScannerValidationGroupPerformance[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Validation appears after enough paper signals are evaluated.</p>
        ) : (
          items.map((item) => (
            <div key={item.name} className="grid grid-cols-[1fr,auto,auto] items-center gap-3 text-sm">
              <span className="font-medium text-slate-200">{item.name}</span>
              <span className="text-slate-400">{item.sample_size} samples</span>
              <span className="text-right text-slate-300">{signedPct(item.average_net_return)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function ScannerValidationReportSection({
  report,
  loading,
  refreshing,
  error,
  evaluating,
  evaluateMessage,
  evaluateError,
  onRefresh,
  onEvaluate,
}: ScannerValidationReportSectionProps) {
  if (error) {
    return <StatePanel title="Scanner validation unavailable" message={error} tone="error" />;
  }
  if (loading && !report) {
    return <StatePanel title="Loading scanner validation report" message="Reading paper validation snapshots and estimated net returns." tone="loading" />;
  }
  if (!report) {
    return <StatePanel title="No scanner validation report" message="Run the Futures Paper Scanner to start collecting paper validation snapshots." tone="empty" />;
  }

  const baseline = report.scanner_vs_random_baseline;
  const tpSl = report.stop_loss_take_profit_analysis;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Scanner Validation Report</p>
          <p className="mt-1 text-sm text-slate-400">
            Futures Paper Scanner paper validation using estimated net return.
          </p>
          <p className="mt-1 text-xs text-slate-500">Updated {formatDateTime(report.generated_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onEvaluate}
            disabled={evaluating}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {evaluating ? 'Evaluating...' : 'Evaluate Pending Results'}
          </button>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing || evaluating}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {evaluateMessage ? <p className="text-sm text-emerald-300">{evaluateMessage}</p> : null}
      {evaluateError ? <p className="text-sm text-rose-300">{evaluateError}</p> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total scanner signals" value={report.total_snapshots} helper="paper validation snapshots" />
        <Metric label="Evaluated signals" value={report.evaluated_snapshots} helper="LONG/SHORT outcomes" />
        <Metric label="Pending signals" value={report.pending_snapshots} helper="waiting for horizons" />
        <Metric label="Conclusion" value={report.conclusion.replace(/_/g, ' ')} helper="sample-size gated" tone={conclusionTone(report.conclusion)} />
        <Metric label="Win rate" value={pct(report.win_rate)} helper="paper validation only" />
        <Metric label="Expectancy" value={signedPct(report.expectancy)} helper="estimated net return" />
        <Metric label="Average win" value={signedPct(report.average_win)} helper="estimated net return" />
        <Metric label="Average loss" value={signedPct(report.average_loss)} helper="estimated net return" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Scanner vs Random Baseline</p>
          <div className="mt-3 grid gap-3 text-sm text-slate-300">
            <Row label="Scanner sample" value={`${baseline.scanner_sample_size} signals`} />
            <Row label="Random baseline sample" value={`${baseline.random_baseline_sample_size} signals`} />
            <Row label="Scanner estimated net return" value={signedPct(baseline.scanner_average_net_return)} />
            <Row label="Random estimated net return" value={signedPct(baseline.random_baseline_average_net_return)} />
            <Row label="Edge vs random" value={signedPct(baseline.edge_vs_random)} />
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">TP / SL Analysis</p>
          <div className="mt-3 grid gap-3 text-sm text-slate-300">
            <Row label="Sample" value={`${tpSl.sample_size} signals`} />
            <Row label="TP hit rate" value={pct(tpSl.take_profit_hit_rate)} />
            <Row label="SL hit rate" value={pct(tpSl.stop_loss_hit_rate)} />
            <Row label="Neither hit rate" value={pct(tpSl.neither_hit_rate)} />
            <Row label="TP first" value={tpSl.take_profit_first} />
            <Row label="SL first" value={tpSl.stop_loss_first} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <GroupList title="Opportunity Score Buckets" items={report.opportunity_score_bucket_performance} />
        <GroupList title="LONG vs SHORT" items={report.direction_performance} />
        <GroupList title="Horizons" items={report.horizon_performance} />
        <GroupList title="Best Symbols" items={report.best_symbols} />
        <GroupList title="Worst Symbols" items={report.worst_symbols} />
        <GroupList title="Best Regimes" items={report.best_regimes} />
      </div>

      {report.weak_conditions.length > 0 || report.warnings.length > 0 ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-200">Validation Warnings</p>
          <div className="mt-3 space-y-1 text-sm text-amber-100">
            {[...report.weak_conditions, ...report.warnings].map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value, helper, tone }: { label: string; value: string | number; helper: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`mt-2 text-xl font-semibold ${tone ?? 'text-white'}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-200">{value}</span>
    </div>
  );
}
