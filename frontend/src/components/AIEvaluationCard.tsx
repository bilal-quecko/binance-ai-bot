import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { badgeTone, classNames, formatDateTime, formatDecimal, formatPercent } from '../lib/format';
import type { AIOutcomeEvaluationResponse } from '../lib/types';

interface AIEvaluationCardProps {
  symbol: string;
  evaluation: AIOutcomeEvaluationResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

export function AIEvaluationCard({ symbol, evaluation, loading, refreshing, error }: AIEvaluationCardProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to load AI outcome validation." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="AI evaluation unavailable" message={error} tone="error" />;
  }
  if (loading && evaluation === null) {
    return <StatePanel title="Loading AI evaluation" message="Computing directional outcome metrics for the selected symbol." tone="loading" />;
  }
  if (!evaluation || evaluation.horizons.every((item) => item.sample_size === 0)) {
    return <StatePanel title="No AI outcome data yet" message="Outcome validation appears after persisted AI snapshots have enough later candle data for 5m, 15m, or 1h comparisons." tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">AI Outcome Validation</p>
          <p className="mt-1 text-sm text-slate-400">How the persisted AI bias performed against later price movement for {evaluation.symbol}.</p>
        </div>
        <span className="text-xs text-slate-500">
          {refreshing ? 'Refreshing...' : `Updated ${formatDateTime(evaluation.generated_at)}`}
        </span>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {evaluation.horizons.map((item) => (
          <div key={item.horizon} className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-white">{item.horizon}</p>
              <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.sample_size > 0 ? 'ok' : 'hold'))}>
                {item.sample_size} samples
              </span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <MetricCard label="Directional Accuracy" value={`${formatDecimal(item.directional_accuracy_pct)}%`} helper="Bias vs later direction" />
              <MetricCard label="Confidence Calibration" value={`${formatDecimal(item.confidence_calibration_pct)}%`} helper="Confidence vs realized correctness" />
              <MetricCard label="False Positives" value={String(item.false_positive_count)} helper={`${formatDecimal(item.false_positive_rate_pct)}% of samples`} />
              <MetricCard label="False Reversals" value={String(item.false_reversal_count)} helper={`${formatDecimal(item.false_reversal_rate_pct)}% of samples`} />
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recent Evaluated Samples</p>
        <div className="mt-4 space-y-3">
          {evaluation.recent_samples.slice(0, 5).map((item) => (
            <div key={`${item.horizon}-${item.snapshot_time}`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-sm text-slate-300">
              <div className="flex flex-wrap items-center gap-2">
                <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.bias === item.observed_direction ? 'ok' : 'rejected'))}>
                  {item.horizon}
                </span>
                <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.suggested_action))}>
                  {item.suggested_action}
                </span>
                <span className="text-xs text-slate-500">{formatDateTime(item.snapshot_time)}</span>
              </div>
              <p className="mt-2 text-slate-200">
                Bias {item.bias}, observed {item.observed_direction}, return {formatPercent(item.return_pct, 2)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
