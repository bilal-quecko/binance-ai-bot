import { PaginationControls } from './PaginationControls';
import { StatePanel } from './StatePanel';
import { badgeTone, classNames, formatDateTime } from '../lib/format';
import type { AISignalSummary, WorkstationDataState } from '../lib/types';

interface AIHistorySectionProps {
  symbol: string;
  history: AISignalSummary[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  dataState: WorkstationDataState;
  statusMessage: string | null;
  total: number;
  limit: number;
  offset: number;
  onPrevious: () => void;
  onNext: () => void;
}

function biasTone(bias: AISignalSummary['bias']): string {
  if (bias === 'bullish') {
    return 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30';
  }
  if (bias === 'bearish') {
    return 'bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30';
  }
  return 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30';
}

export function AIHistorySection({
  symbol,
  history,
  loading,
  refreshing,
  error,
  dataState,
  statusMessage,
  total,
  limit,
  offset,
  onPrevious,
  onNext,
}: AIHistorySectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load advisory history for that workstation."
        tone="empty"
      />
    );
  }

  if (error) {
    return <StatePanel title="AI history unavailable" message={error} tone="error" />;
  }

  if (loading && history.length === 0) {
    return <StatePanel title="Loading AI history" message="Reading persisted advisory snapshots for the selected symbol." tone="loading" />;
  }

  if (history.length === 0) {
    return (
      <StatePanel
        title="No AI history yet"
        message={
          statusMessage
          ?? (
            dataState === 'waiting_for_runtime'
              ? 'Start the live runtime for the selected symbol to generate advisory history.'
              : 'The selected symbol does not have persisted advisory snapshots yet. Wait for closed candles to accumulate history.'
          )
        }
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">AI History</p>
          <p className="mt-1 text-sm text-slate-400">Latest 3 advisory snapshots for {symbol}. Older pages stay symbol-scoped.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/50">
        <div className="border-b border-slate-800 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recent Advisory Rows</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-sm">
            <thead className="bg-slate-950/70 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Time</th>
                <th className="px-4 py-3 font-semibold">Bias</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200">
              {history.slice(0, 3).map((item) => (
                <tr key={`${item.symbol}-${item.timestamp}`}>
                  <td className="px-4 py-3 text-slate-400">{formatDateTime(item.timestamp)}</td>
                  <td className="px-4 py-3">
                    <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', biasTone(item.bias))}>
                      {item.bias}
                    </span>
                  </td>
                  <td className="px-4 py-3">{item.confidence}%</td>
                  <td className="px-4 py-3">
                    <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.suggested_action))}>
                      {item.suggested_action}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {total > limit ? (
          <div className="px-4 pb-4">
            <PaginationControls total={total} limit={limit} offset={offset} onPrevious={onPrevious} onNext={onNext} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
