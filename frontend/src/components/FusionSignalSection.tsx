import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { classNames, formatDecimal } from '../lib/format';
import type { FusionSignalResponse } from '../lib/types';

interface FusionSignalSectionProps {
  symbol: string;
  signal: FusionSignalResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.split('_').join(' ');
}

function actionTone(action: FusionSignalResponse['final_signal']): string {
  if (action === 'long') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  }
  if (action === 'short' || action === 'exit_long') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
  }
  if (action === 'reduce_risk') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-200';
}

export function FusionSignalSection({
  symbol,
  signal,
  loading,
  refreshing,
  error,
}: FusionSignalSectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load the final fused signal."
        tone="empty"
      />
    );
  }

  if (loading && signal === null) {
    return (
      <StatePanel
        title="Loading final signal"
        message={`Combining technical, pattern, AI, sentiment, and readiness context for ${symbol}.`}
        tone="loading"
      />
    );
  }

  if (error) {
    return <StatePanel title="Final signal unavailable" message={error} tone="error" />;
  }

  if (signal === null) {
    return (
      <StatePanel
        title="Final signal unavailable"
        message={`No fused signal is available yet for ${symbol}.`}
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Final Signal</p>
          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">Advisory only - deterministic risk and execution still remain separate.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={signal.data_state} message={signal.status_message} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Direction" value={humanize(signal.final_signal).toUpperCase()} helper="Unified advisory decision" />
        <MetricCard label="Confidence" value={`${signal.confidence}%`} helper="Shaped by cross-layer agreement" />
        <MetricCard
          label="Expected Edge"
          value={signal.expected_edge_pct !== null ? `${formatDecimal(signal.expected_edge_pct)}%` : '-'}
          helper="Fee-aware edge estimate if available"
        />
        <MetricCard label="Preferred Horizon" value={signal.preferred_horizon} helper="Most credible current timeframe" />
        <MetricCard label="Risk Grade" value={humanize(signal.risk_grade)} helper="Current fused risk posture" />
        <MetricCard label="Alignment Score" value={`${signal.alignment_score}/100`} helper="How strongly inputs agree" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.9fr,1.1fr]">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Why Now</p>
          <div className="mt-3 flex items-center gap-3">
            <span className={classNames('rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', actionTone(signal.final_signal))}>
              {humanize(signal.final_signal).toUpperCase()}
            </span>
            <span className="text-sm text-slate-400">Best timeframe {signal.preferred_horizon}</span>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            {signal.top_reasons[0] ?? 'The fusion engine is still building its primary reason.'}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Top Reasons</p>
          {signal.top_reasons.length > 0 ? (
            <ul className="mt-3 space-y-2 text-sm text-slate-300">
              {signal.top_reasons.map((item) => (
                <li key={item} className="rounded-xl border border-slate-800/80 bg-slate-900/70 px-3 py-2">
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-slate-400">No fused reasons are available yet.</p>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Invalidation</p>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          {signal.invalidation_hint ?? 'No clear invalidation level is available yet for this fused setup.'}
        </p>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Warnings</p>
        {signal.warnings.length > 0 ? (
          <ul className="mt-3 space-y-2 text-sm text-slate-300">
            {signal.warnings.map((item) => (
              <li key={item} className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-amber-100">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-400">No major fused warnings are active.</p>
        )}
      </div>
    </div>
  );
}
