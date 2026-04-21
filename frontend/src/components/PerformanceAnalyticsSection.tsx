import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { formatCurrency, formatDecimal } from '../lib/format';
import type { PerformanceAnalyticsResponse } from '../lib/types';

interface PerformanceAnalyticsSectionProps {
  symbol: string;
  analytics: PerformanceAnalyticsResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function formatHoldTime(seconds: number | null): string {
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

export function PerformanceAnalyticsSection({
  symbol,
  analytics,
  loading,
  refreshing,
  error,
}: PerformanceAnalyticsSectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to evaluate trading performance." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Performance analytics unavailable" message={error} tone="error" />;
  }
  if (loading && analytics === null) {
    return <StatePanel title="Loading performance analytics" message="Reading realized PnL, drawdown, and closed-trade quality metrics." tone="loading" />;
  }
  if (!analytics || analytics.total_closed_trades === 0) {
    return <StatePanel title="No closed trades yet" message="Performance analytics appear after the selected symbol completes at least one closed paper trade." tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Performance Analytics</p>
          <p className="mt-1 text-sm text-slate-400">Closed-trade quality and session PnL context for {symbol}.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Expectancy"
          value={analytics.expectancy_per_closed_trade ? formatCurrency(analytics.expectancy_per_closed_trade) : '-'}
          helper="Average realized PnL per closed trade"
        />
        <MetricCard
          label="Profit Factor"
          value={analytics.profit_factor ? formatDecimal(analytics.profit_factor, { maximumFractionDigits: 2 }) : '-'}
          helper="Gross wins divided by gross losses"
        />
        <MetricCard
          label="Average Hold Time"
          value={formatHoldTime(analytics.average_hold_seconds)}
          helper="Quantity-weighted close duration"
        />
        <MetricCard
          label="Closed Trades"
          value={String(analytics.total_closed_trades)}
          helper="Completed SELL exits in scope"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Average Win"
          value={analytics.average_win ? formatCurrency(analytics.average_win) : '-'}
          helper="Mean realized PnL on winning closes"
        />
        <MetricCard
          label="Average Loss"
          value={analytics.average_loss ? formatCurrency(analytics.average_loss) : '-'}
          helper="Mean realized PnL on losing closes"
        />
        <MetricCard
          label="Symbol Realized PnL"
          value={formatCurrency(analytics.symbol_realized_pnl)}
          helper="Closed-trade realized PnL for selected symbol"
        />
        <MetricCard
          label="Session Unrealized PnL"
          value={formatCurrency(analytics.session_unrealized_pnl)}
          helper="Latest total PnL minus realized PnL"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Session Realized PnL"
          value={formatCurrency(analytics.session_realized_pnl)}
          helper="Latest persisted realized PnL snapshot"
        />
        <MetricCard
          label="Current Drawdown"
          value={formatCurrency(analytics.current_drawdown)}
          helper="Current peak-to-trough drop"
        />
        <MetricCard
          label="Max Drawdown"
          value={formatCurrency(analytics.max_drawdown)}
          helper="Worst peak-to-trough drop in scope"
        />
        <MetricCard
          label="Sample Size"
          value={String(analytics.total_closed_trades)}
          helper="Closed trades used in expectancy and averages"
        />
      </div>
    </div>
  );
}
