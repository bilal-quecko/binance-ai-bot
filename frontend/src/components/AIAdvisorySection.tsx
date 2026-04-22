import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { classNames, formatDateTime } from '../lib/format';
import type { AISignalSummary } from '../lib/types';

interface AIAdvisorySectionProps {
  symbol: string;
  signal: AISignalSummary | null;
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

function actionTone(action: AISignalSummary['suggested_action']): string {
  if (action === 'enter') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  }
  if (action === 'exit') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
  }
  if (action === 'abstain') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-200';
}

export function AIAdvisorySection({
  symbol,
  signal,
  loading,
  refreshing,
  error,
}: AIAdvisorySectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load AI advisory context."
        tone="empty"
      />
    );
  }

  if (error) {
    return <StatePanel title="AI signal unavailable" message={error} tone="error" />;
  }

  if (loading && signal === null) {
    return (
      <StatePanel
        title="Loading AI signal"
        message="Reading the latest persisted advisory snapshot for the selected symbol."
        tone="loading"
      />
    );
  }

  if (signal === null) {
    return (
      <StatePanel
        title="AI signal unavailable"
        message="No persisted AI advisory snapshot exists yet for the selected symbol."
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">AI Advisory</p>
          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">Advisory only - execution still follows deterministic strategy plus risk gating.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Bias" value={signal.bias} helper="Probable direction" />
        <MetricCard label="Confidence" value={`${signal.confidence}%`} helper={formatDateTime(signal.timestamp)} />
        <MetricCard label="Regime" value={humanize(signal.regime)} helper={`Noise ${humanize(signal.noise_level)}`} />
        <MetricCard label="Preferred Horizon" value={signal.preferred_horizon ?? '-'} helper="Most credible current horizon" />
        <MetricCard label="Entry Setup" value={signal.entry_signal ? 'Yes' : 'No'} helper="Advisory entry only" />
        <MetricCard label="Exit Setup" value={signal.exit_signal ? 'Yes' : 'No'} helper="Advisory exit only" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.9fr,1.1fr]">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recommendation</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className={classNames('rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', actionTone(signal.suggested_action))}>
              {signal.suggested_action}
            </span>
            {signal.abstain ? <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-amber-200">abstain</span> : null}
            {signal.confirmation_needed ? <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-sky-200">confirmation needed</span> : null}
            {signal.low_confidence ? <span className="rounded-full border border-slate-600 bg-slate-900 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">low confidence</span> : null}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">{signal.explanation}</p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Horizon Reads</p>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {signal.horizons.length === 0 ? (
              <p className="text-sm text-slate-400">Horizon-specific reads are not available yet.</p>
            ) : (
              signal.horizons.map((item) => (
                <div key={item.horizon} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{item.horizon}</p>
                  <p className="mt-2 text-sm font-medium text-white">{item.bias}</p>
                  <p className="mt-1 text-xs text-slate-400">{item.confidence}% - {humanize(item.suggested_action)}</p>
                  <p className="mt-2 text-xs leading-5 text-slate-400">{item.explanation}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {signal.weakening_factors.length > 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Confidence Headwinds</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            {signal.weakening_factors.map((item) => item.split('_').join(' ')).join(', ')}
          </p>
        </div>
      ) : null}
    </div>
  );
}
