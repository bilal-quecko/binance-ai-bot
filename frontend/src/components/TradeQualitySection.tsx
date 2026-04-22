import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { formatCurrency, formatDateTime, formatDecimal, pnlTone } from '../lib/format';
import type { TradeQualityResponse } from '../lib/types';

interface TradeQualitySectionProps {
  symbol: string;
  analytics: TradeQualityResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function formatSeconds(seconds: number | null): string {
  if (seconds === null) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainderSeconds = seconds % 60;
  if (minutes < 60) {
    return remainderSeconds === 0 ? `${minutes}m` : `${minutes}m ${remainderSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  return remainderMinutes === 0 ? `${hours}h` : `${hours}h ${remainderMinutes}m`;
}

function formatPct(value: string | null): string {
  return value === null ? '-' : `${formatDecimal(value, { maximumFractionDigits: 2 })}%`;
}

export function TradeQualitySection({
  symbol,
  analytics,
  loading,
  refreshing,
  error,
}: TradeQualitySectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to inspect entry and exit quality." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Trade quality unavailable" message={error} tone="error" />;
  }
  if (loading && analytics === null) {
    return <StatePanel title="Loading trade quality" message="Reading closed candles and closed trades for attribution analysis." tone="loading" />;
  }
  if (!analytics || analytics.summary.total_closed_trades === 0) {
    return <StatePanel title="No closed trades yet" message="Trade quality appears after the selected symbol completes at least one paper round trip." tone="empty" />;
  }

  const hold = analytics.summary.hold_time_distribution;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trade Quality</p>
          <p className="mt-1 text-sm text-slate-400">Explains whether results are coming from entries, exits, or trade management on {symbol}.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Entry Quality"
          value={formatPct(analytics.summary.average_entry_quality_score)}
          helper="Higher means entries were closer to the better observed prices before exit."
        />
        <MetricCard
          label="Exit Quality"
          value={formatPct(analytics.summary.average_exit_quality_score)}
          helper="Higher means exits captured more of the observed trade range."
        />
        <MetricCard
          label="Average MFE"
          value={formatPct(analytics.summary.average_mfe_pct)}
          helper="Best favorable move seen after entry before the trade closed."
        />
        <MetricCard
          label="Average MAE"
          value={formatPct(analytics.summary.average_mae_pct)}
          helper="Worst adverse move seen after entry before the trade closed."
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Captured Move"
          value={formatPct(analytics.summary.average_captured_move_pct)}
          helper="Share of the best favorable move that the exit actually kept."
        />
        <MetricCard
          label="Giveback"
          value={formatPct(analytics.summary.average_giveback_pct)}
          helper="Share of the best favorable move that was surrendered before exit."
        />
        <MetricCard
          label="Longest No-Trade"
          value={formatSeconds(analytics.summary.longest_no_trade_seconds)}
          helper="Longest idle gap between executed paper trades in scope."
        />
        <MetricCard
          label="Sample Size"
          value={String(analytics.summary.total_closed_trades)}
          helper="Closed trades used for attribution."
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Average Hold" value={formatSeconds(hold.average_seconds)} helper="Mean hold time per closed trade." />
        <MetricCard label="Median Hold" value={formatSeconds(hold.median_seconds)} helper="Middle hold time after sorting closed trades." />
        <MetricCard label="P75 Hold" value={formatSeconds(hold.p75_seconds)} helper="Longer-hold threshold for the top quarter of trades." />
        <MetricCard label="Max Hold" value={formatSeconds(hold.max_seconds)} helper="Longest single closed-trade hold time." />
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recent Closed Trade Attribution</p>
            <p className="mt-1 text-sm text-slate-400">Use these recent closes to judge whether the bot is buying well, managing risk well, and exiting efficiently.</p>
          </div>
          <p className="text-xs text-slate-500">Latest {analytics.details.length} closes</p>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-sm text-slate-200">
            <thead>
              <tr className="text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                <th className="px-3 py-2">Exit</th>
                <th className="px-3 py-2">PnL</th>
                <th className="px-3 py-2">Hold</th>
                <th className="px-3 py-2">MFE / MAE</th>
                <th className="px-3 py-2">Captured / Giveback</th>
                <th className="px-3 py-2">Entry / Exit Quality</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-900/70">
              {analytics.details.map((detail) => (
                <tr key={detail.order_id}>
                  <td className="px-3 py-3 align-top">
                    <div className="font-medium text-white">{formatDateTime(detail.exit_time)}</div>
                    <div className="text-xs text-slate-500">
                      Entry {formatCurrency(detail.entry_price)} {'->'} Exit {formatCurrency(detail.exit_price)}
                    </div>
                  </td>
                  <td className={`px-3 py-3 align-top font-medium ${pnlTone(detail.realized_pnl)}`}>
                    {formatCurrency(detail.realized_pnl)}
                  </td>
                  <td className="px-3 py-3 align-top">{formatSeconds(detail.hold_seconds)}</td>
                  <td className="px-3 py-3 align-top">
                    <div>MFE {formatPct(detail.mfe_pct)}</div>
                    <div className="text-xs text-slate-500">MAE {formatPct(detail.mae_pct)}</div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div>Captured {formatPct(detail.captured_move_pct)}</div>
                    <div className="text-xs text-slate-500">Giveback {formatPct(detail.giveback_pct)}</div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div>Entry {formatPct(detail.entry_quality_score)}</div>
                    <div className="text-xs text-slate-500">Exit {formatPct(detail.exit_quality_score)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
