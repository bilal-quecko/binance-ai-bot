import { TimeSeriesChart } from './TimeSeriesChart';
import { StatePanel } from './StatePanel';
import { badgeTone, classNames, formatDateTime } from '../lib/format';
import { buildAiHistoryViewModel } from '../lib/ai-history.js';
import type { AISignalSummary, WorkstationDataState } from '../lib/types';

interface AIHistorySectionProps {
  symbol: string;
  history: AISignalSummary[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  dataState: WorkstationDataState;
  statusMessage: string | null;
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

export function AIHistorySection({ symbol, history, loading, refreshing, error, dataState, statusMessage }: AIHistorySectionProps) {
  const viewModel = buildAiHistoryViewModel(symbol, history);

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

  if (loading && viewModel.items.length === 0) {
    return <StatePanel title="Loading AI history" message="Reading persisted advisory snapshots for the selected symbol." tone="loading" />;
  }

  if (viewModel.items.length === 0) {
    return (
      <StatePanel
        title="No AI history yet"
        message={
          statusMessage
          ?? (
            dataState === 'waiting_for_runtime'
              ? 'Start the live paper runtime for the selected symbol to generate advisory history.'
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
          <p className="mt-1 text-sm text-slate-400">Persisted advisory bias, confidence, and action changes for {symbol}.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <TimeSeriesChart
        title="Confidence Trend"
        subtitle="Confidence is persisted when the advisory output materially changes on a closed candle."
        labels={viewModel.labels}
        series={[
          {
            key: 'confidence',
            label: 'Confidence',
            color: '#38bdf8',
            values: viewModel.confidenceValues,
            format: 'decimal',
          },
        ]}
        emptyMessage="No confidence history is available for the selected symbol."
      />

      <div className="grid gap-4 lg:grid-cols-[1.1fr,0.9fr]">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Bias Changes Over Time</p>
          <div className="mt-4 space-y-3">
            {viewModel.recentItems.slice(0, 6).map((item) => (
              <div key={`${item.symbol}-${item.timestamp}`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', biasTone(item.bias))}>
                    {item.bias}
                  </span>
                  <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.suggested_action))}>
                    {item.suggested_action}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(item.timestamp)}</span>
                </div>
                <p className="mt-2 text-sm text-slate-300">{item.explanation}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recent Suggested Action Changes</p>
          <div className="mt-4 space-y-3">
            {viewModel.recentActionChanges.slice(0, 5).map((item) => (
              <div key={`${item.symbol}-${item.timestamp}-action`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-sm text-slate-300">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={classNames('rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(item.suggested_action))}>
                    {item.suggested_action}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(item.timestamp)}</span>
                </div>
                <p className="mt-2 text-slate-400">{item.bias} bias � confidence {item.confidence}%</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/50">
        <div className="border-b border-slate-800 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recent Advisory Snapshots</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-sm">
            <thead className="bg-slate-950/70 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Time</th>
                <th className="px-4 py-3 font-semibold">Bias</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Action</th>
                <th className="px-4 py-3 font-semibold">Entry</th>
                <th className="px-4 py-3 font-semibold">Exit</th>
                <th className="px-4 py-3 font-semibold">Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200">
              {viewModel.recentItems.slice(0, 10).map((item) => (
                <tr key={`${item.symbol}-${item.timestamp}-row`}>
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
                  <td className="px-4 py-3">{item.entry_signal ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-3">{item.exit_signal ? 'Yes' : 'No'}</td>
                  <td className="max-w-md px-4 py-3 text-slate-400">{item.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
