import { badgeTone, classNames, formatDecimal, formatReasonCodes } from '../lib/format';
import { explainPrimaryBlocker } from '../lib/blocker-explanations.js';
import { describeReadiness, humanizeMode, humanizeReadinessAction, shouldShowCostMetrics } from '../lib/workstation-ux.js';
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

  const readinessSummary = describeReadiness(readiness);
  const showCostMetrics = shouldShowCostMetrics(readiness);
  const primaryBlocker = explainPrimaryBlocker(readiness);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Execution Readiness</p>
          <p className="mt-1 text-sm text-slate-400">This is the actual deterministic execution path. AI advisory is shown separately and never places trades directly.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(readiness.mode === 'auto_paper' ? 'approve' : readiness.mode === 'paused' ? 'hold' : readiness.mode === 'error' ? 'reject' : 'skipped'))}>
            {humanizeMode(readiness.mode)}
          </span>
          <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(readiness.risk_blocked ? 'reject' : readiness.risk_ready ? 'approve' : 'hold'))}>
            {readiness.risk_blocked ? 'risk blocked' : readiness.risk_ready ? 'risk ready' : 'waiting'}
          </span>
        </div>
      </div>

      <div className={classNames('grid gap-4', compact ? 'md:grid-cols-2 xl:grid-cols-3' : 'md:grid-cols-2 xl:grid-cols-4')}>
        <MetricCard label="Next Action" value={humanizeReadinessAction(readiness.next_action)} helper={readinessSummary} />
        <MetricCard label="Trading Profile" value={readiness.trading_profile} helper="Current paper activation tuning" />
        <MetricCard label="Entry Signal" value={boolLabel(readiness.deterministic_entry_signal)} helper="Deterministic entry conditions only" />
        <MetricCard label="Exit Signal" value={boolLabel(readiness.deterministic_exit_signal)} helper="Deterministic exit conditions only" />
        <MetricCard label="Candle History Ready" value={boolLabel(readiness.enough_candle_history)} helper="Enough closed candles for features and strategy" />
        <MetricCard label="Broker Ready" value={boolLabel(readiness.broker_ready)} helper="Paper broker and execution handoff can act" />
        <MetricCard label="Runtime Active" value={boolLabel(readiness.runtime_active)} helper={`Selected symbol ${readiness.selected_symbol}`} />
        {showCostMetrics ? (
          <>
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
          </>
        ) : null}
      </div>

      {!showCostMetrics ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Cost-Aware Gating</p>
          <p className="mt-3 text-sm text-slate-300">
            Expected edge and round-trip cost appear after live candles, deterministic signals, and risk inputs are ready for this symbol.
          </p>
        </div>
      ) : null}

      {primaryBlocker ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trade blocker explained</p>
            <span className={classNames('rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em]', badgeTone(primaryBlocker.category === 'risk_protection' ? 'hold' : primaryBlocker.category === 'system_state' ? 'reject' : 'skipped'))}>
              {primaryBlocker.category === 'risk_protection'
                ? 'risk protection'
                : primaryBlocker.category === 'system_state'
                  ? 'system state'
                  : primaryBlocker.category === 'data_requirement'
                    ? 'needs more data'
                    : 'setup context'}
            </span>
          </div>
          <h4 className="mt-3 text-sm font-semibold text-white">{primaryBlocker.title}</h4>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 px-3 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">What happened</p>
              <p className="mt-2 text-sm text-slate-300">{primaryBlocker.happened}</p>
            </div>
            <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 px-3 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Why the bot blocked it</p>
              <p className="mt-2 text-sm text-slate-300">{primaryBlocker.why}</p>
            </div>
            <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 px-3 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">What you can do</p>
              <p className="mt-2 text-sm text-slate-300">{primaryBlocker.action}</p>
            </div>
          </div>
        </div>
      ) : null}

      {readiness.blocking_reasons.length > 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Additional context</p>
          <ul className="mt-3 space-y-2 text-sm text-slate-300">
            {readiness.blocking_reasons.map((reason) => (
              <li key={reason} className="rounded-xl border border-slate-800/80 bg-slate-950/70 px-3 py-2">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {readiness.risk_reason_codes.length > 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Risk Status</p>
          <p className="mt-3 text-sm text-slate-300">{formatReasonCodes(readiness.risk_reason_codes)}</p>
        </div>
      ) : null}
    </div>
  );
}
