import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import type {
  ProfileCalibrationComparisonResponse,
  ProfileCalibrationResponse,
  TradingProfile,
} from '../lib/types';
import { formatCurrency, formatDecimal } from '../lib/format';

interface ProfileCalibrationSectionProps {
  symbol: string;
  calibration: ProfileCalibrationResponse | null;
  comparison: ProfileCalibrationComparisonResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  actionLoading: boolean;
  activeProfile: TradingProfile;
  onApply: (profile: TradingProfile, thresholds?: string[]) => void;
}

function actionTone(action: string): string {
  if (action === 'tighten') {
    return 'text-amber-300';
  }
  if (action === 'loosen') {
    return 'text-sky-300';
  }
  return 'text-emerald-300';
}

export function ProfileCalibrationSection({
  symbol,
  calibration,
  comparison,
  loading,
  refreshing,
  error,
  actionLoading,
  activeProfile,
  onApply,
}: ProfileCalibrationSectionProps) {
  if (loading && calibration === null) {
    return (
      <StatePanel
        title="Loading profile calibration"
        message={`Reviewing paper profile health for ${symbol}.`}
        tone="loading"
      />
    );
  }

  if (error) {
    return <StatePanel title="Profile calibration unavailable" message={error} tone="error" />;
  }

  if (!calibration) {
    return (
      <StatePanel
        title="No calibration data yet"
        message="Calibration appears after paper outcomes accumulate for the selected symbol."
        tone="empty"
      />
    );
  }

  const activeBadge = calibration.active_tuning;
  const pendingBadge = calibration.pending_tuning;
  const comparisonColumns =
    comparison !== null && comparison.before !== null && comparison.after !== null
      ? [
          { label: 'Before', metrics: comparison.before },
          { label: 'After', metrics: comparison.after },
        ]
      : [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Profile Calibration</p>
          <p className="mt-1 text-sm text-slate-400">
            Recommendations stay paper-only. Applying one schedules it for the next session.
          </p>
        </div>
        {refreshing ? <span className="text-xs text-slate-500">Refreshing...</span> : null}
      </div>

      {(activeBadge || pendingBadge) ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Applied tuning</p>
            {activeBadge ? (
              <div className="mt-2 text-sm text-slate-300">
                <p className="font-medium text-white">{activeBadge.version_id}</p>
                <p className="mt-1">Profile {activeBadge.profile}</p>
                <p className="mt-1 text-slate-400">Baseline {activeBadge.baseline_version_id ?? 'built-in defaults'}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-400">No applied tuning set is active for this symbol yet.</p>
            )}
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Pending next session</p>
            {pendingBadge ? (
              <div className="mt-2 text-sm text-slate-300">
                <p className="font-medium text-white">{pendingBadge.version_id}</p>
                <p className="mt-1">{pendingBadge.reason}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-400">No pending tuning is queued for the next paper session.</p>
            )}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        {calibration.recommendations.map((recommendation) => (
          <div key={recommendation.profile} className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-200">{recommendation.profile}</p>
                <p className="mt-1 text-xs text-slate-500">Health {recommendation.profile_health.replace(/_/g, ' ')}</p>
              </div>
              <span className={`rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${actionTone(recommendation.recommendation)}`}>
                {recommendation.recommendation}
              </span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <MetricCard label="Trades" value={String(recommendation.trade_count)} helper="Closed trades" />
              <MetricCard
                label="Expectancy"
                value={recommendation.expectancy ? formatCurrency(recommendation.expectancy) : '-'}
                helper="Per closed trade"
              />
              <MetricCard
                label="Fees"
                value={formatCurrency(recommendation.fees_paid)}
                helper={recommendation.win_rate ? `${formatDecimal(recommendation.win_rate)}% win rate` : 'No win-rate sample yet'}
              />
            </div>

            <div className="mt-4 space-y-3">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Reason</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">{recommendation.reason}</p>
              </div>

              {recommendation.sample_size_warning ? (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                  {recommendation.sample_size_warning}
                </div>
              ) : null}

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Affected Thresholds</p>
                {recommendation.affected_thresholds.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-400">No threshold change recommended yet.</p>
                ) : (
                  <div className="mt-2 space-y-2">
                    {recommendation.affected_thresholds.map((threshold) => (
                      <div key={threshold.threshold} className="flex items-center justify-between gap-3 text-sm text-slate-300">
                        <span>{threshold.threshold}</span>
                        <span className="text-slate-400">
                          {formatDecimal(threshold.current_value)} {'->'} {formatDecimal(threshold.suggested_value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Expected Impact</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">{recommendation.expected_impact}</p>
              </div>

              <button
                type="button"
                disabled={
                  actionLoading ||
                  recommendation.affected_thresholds.length === 0 ||
                  recommendation.profile !== activeProfile
                }
                onClick={() => onApply(recommendation.profile, recommendation.affected_thresholds.map((item) => item.threshold))}
                className="w-full rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-sm font-medium text-sky-100 transition disabled:cursor-not-allowed disabled:opacity-40 hover:border-sky-300 hover:bg-sky-400/20"
              >
                Apply to next session
              </button>
              {recommendation.profile !== activeProfile ? (
                <p className="text-xs text-slate-500">
                  Switch the selected trading profile to {recommendation.profile} to apply this recommendation.
                </p>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Before / After Comparison</p>
        {comparison === null ? (
          <p className="mt-3 text-sm text-slate-400">Apply a tuning set and run at least one follow-up session to compare it against the baseline.</p>
        ) : comparison.comparison_status !== 'ready' || comparison.before === null || comparison.after === null ? (
          <StatePanel
            title="Comparison not ready"
            message={comparison.status_message ?? 'Need baseline and tuned paper sessions before comparison is meaningful.'}
            tone="empty"
          />
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            {comparisonColumns.map(({ label, metrics }) => (
              <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-sm font-semibold text-white">{label}</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <MetricCard label="Sessions" value={String(metrics.session_count)} helper="Compared runs" />
                  <MetricCard label="Closed trades" value={String(metrics.trade_count)} helper="Completed exits" />
                  <MetricCard label="Expectancy" value={metrics.expectancy ? formatCurrency(metrics.expectancy) : '-'} helper="Per closed trade" />
                  <MetricCard label="Profit factor" value={metrics.profit_factor ? formatDecimal(metrics.profit_factor) : '-'} helper="Gross profit / gross loss" />
                  <MetricCard label="Win rate" value={metrics.win_rate ? `${formatDecimal(metrics.win_rate)}%` : '-'} helper="Closed trades only" />
                  <MetricCard label="Max drawdown" value={metrics.max_drawdown ? formatCurrency(metrics.max_drawdown) : '-'} helper="Realized PnL path" />
                  <MetricCard label="Fees paid" value={formatCurrency(metrics.fees_paid)} helper="All fills in scope" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
