import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import type { PaperTradeReviewResponse } from '../lib/types';
import { formatCurrency, formatDecimal, pnlTone } from '../lib/format';

interface PaperTradeReviewSectionProps {
  symbol: string;
  review: PaperTradeReviewResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

export function PaperTradeReviewSection({
  symbol,
  review,
  loading,
  refreshing,
  error,
}: PaperTradeReviewSectionProps) {
  if (loading && review === null) {
    return <StatePanel title="Loading paper trade review" message={`Building review analytics for ${symbol}.`} tone="loading" />;
  }

  if (error) {
    return <StatePanel title="Paper trade review unavailable" message={error} tone="error" />;
  }

  if (!review) {
    return <StatePanel title="No review data yet" message="Paper trade review appears after the selected symbol records runnable paper activity." tone="empty" />;
  }

  const positivePnl = Number(review.session.average_pnl ?? '0') >= 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Paper Trade Review</p>
          <p className="mt-1 text-sm text-slate-400">Evidence-based tuning for {symbol}.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-500">Refreshing...</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Trades / Hour" value={review.session.trades_per_hour ? formatDecimal(review.session.trades_per_hour) : '-'} helper="Executed paper cadence" />
        <MetricCard label="Win Rate" value={review.session.win_rate ? `${formatDecimal(review.session.win_rate)}%` : '-'} helper={`${review.session.total_closed_trades} closed trades`} />
        <MetricCard label="Avg PnL" value={review.session.average_pnl ? formatCurrency(review.session.average_pnl) : '-'} helper="Closed-trade average" tone={positivePnl ? 'positive' : 'negative'} />
        <MetricCard label="Fees Paid" value={formatCurrency(review.session.fees_paid)} helper={`Idle ${formatDuration(review.session.idle_duration_seconds)}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Blocker Frequency</p>
          {review.blockers.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">No blocker analytics have accumulated yet for this scope.</p>
          ) : (
            <div className="mt-3 space-y-3">
              {review.blockers.map((blocker) => (
                <div key={blocker.blocker_key} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-100">{blocker.label}</p>
                    <p className="text-sm font-semibold text-slate-200">{formatDecimal(blocker.frequency_pct)}%</p>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{blocker.count} blocked cycles</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Tuning Suggestions</p>
          <div className="mt-3 space-y-3">
            {review.suggestions.map((suggestion, index) => (
              <div key={`${suggestion.summary}-${index}`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-sm leading-6 text-slate-300">
                {suggestion.summary}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Profile Comparison</p>
          <div className="mt-3 space-y-2">
            {review.profiles.map((profile) => (
              <div key={profile.profile} className="grid grid-cols-[1.1fr,0.9fr,0.9fr,0.9fr] gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-sm">
                <div>
                  <p className="font-medium text-slate-100">{profile.profile}</p>
                  <p className="text-xs text-slate-400">{profile.trade_count} closed trades</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">PnL</p>
                  <p className={pnlTone(profile.realized_pnl)}>{formatCurrency(profile.realized_pnl)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Win Rate</p>
                  <p className="text-slate-200">{profile.win_rate ? `${formatDecimal(profile.win_rate)}%` : '-'}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Expectancy</p>
                  <p className="text-slate-200">{profile.average_expectancy ? formatCurrency(profile.average_expectancy) : '-'}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Manual vs Auto</p>
          <div className="mt-3 space-y-2">
            {review.execution_sources.map((source) => (
              <div key={source.execution_source} className="grid grid-cols-[1fr,0.9fr,0.9fr,0.9fr] gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-sm">
                <div>
                  <p className="font-medium text-slate-100">{source.execution_source}</p>
                  <p className="text-xs text-slate-400">{source.trade_count} closed trades</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">PnL</p>
                  <p className={pnlTone(source.realized_pnl)}>{formatCurrency(source.realized_pnl)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Win Rate</p>
                  <p className="text-slate-200">{source.win_rate ? `${formatDecimal(source.win_rate)}%` : '-'}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Expectancy</p>
                  <p className="text-slate-200">{source.average_expectancy ? formatCurrency(source.average_expectancy) : '-'}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
