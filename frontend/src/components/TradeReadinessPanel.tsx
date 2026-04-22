import { badgeTone, classNames, formatDecimal } from '../lib/format';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import type { TradeReadinessResponse } from '../lib/types';

interface TradeReadinessPanelProps {
  symbol: string;
  readiness: TradeReadinessResponse | null;
  compact?: boolean;
}

function boolLabel(value: boolean): string {
  return value ? 'Yes' : 'No';
}

export function TradeReadinessPanel({ symbol, readiness, compact = false }: TradeReadinessPanelProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to see deterministic trade readiness." tone="empty" />;
  }
  if (!readiness) {
    return <StatePanel title="Readiness unavailable" message="Deterministic readiness appears after the workstation loads for the selected symbol." tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Execution Readiness</p>
          <p className="mt-1 text-sm text-slate-400">This is the actual deterministic execution path. AI advisory is shown separately and never places trades directly.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(readiness.mode === 'auto_paper' ? 'approve' : readiness.mode === 'paused' ? 'hold' : readiness.mode === 'error' ? 'reject' : 'skipped'))}>
            {readiness.mode}
          </span>
          <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(readiness.risk_blocked ? 'reject' : readiness.risk_ready ? 'approve' : 'hold'))}>
            {readiness.risk_blocked ? 'risk blocked' : readiness.risk_ready ? 'risk ready' : 'waiting'}
          </span>
        </div>
      </div>

      <div className={classNames('grid gap-4', compact ? 'md:grid-cols-2 xl:grid-cols-3' : 'md:grid-cols-2 xl:grid-cols-4')}>
        <MetricCard label="Next Action" value={readiness.next_action} helper={readiness.reason_if_not_trading ?? 'Deterministic path is clear.'} />
        <MetricCard label="Entry Signal" value={boolLabel(readiness.deterministic_entry_signal)} helper="Deterministic entry conditions only" />
        <MetricCard label="Exit Signal" value={boolLabel(readiness.deterministic_exit_signal)} helper="Deterministic exit conditions only" />
        <MetricCard label="Candle History Ready" value={boolLabel(readiness.enough_candle_history)} helper="Enough closed candles for features and strategy" />
        <MetricCard label="Broker Ready" value={boolLabel(readiness.broker_ready)} helper="Paper broker and execution handoff can act" />
        <MetricCard label="Runtime Active" value={boolLabel(readiness.runtime_active)} helper={`Selected symbol ${readiness.selected_symbol}`} />
        <MetricCard
          label="Expected Edge"
          value={readiness.expected_edge_pct ? `${formatDecimal(readiness.expected_edge_pct, { maximumFractionDigits: 3 })}%` : '-'}
          helper="Estimated upside from the deterministic setup"
        />
        <MetricCard
          label="Round-Trip Cost"
          value={readiness.estimated_round_trip_cost_pct ? `${formatDecimal(readiness.estimated_round_trip_cost_pct, { maximumFractionDigits: 3 })}%` : '-'}
          helper="Estimated entry plus exit fees and slippage"
        />
      </div>

      {readiness.risk_reason_codes.length > 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Risk Status</p>
          <p className="mt-3 text-sm text-slate-300">{readiness.risk_reason_codes.join(', ')}</p>
        </div>
      ) : null}
    </div>
  );
}
