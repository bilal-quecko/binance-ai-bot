import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { classNames } from '../lib/format';
import type { SymbolSentimentResponse } from '../lib/types';

interface SymbolSentimentSectionProps {
  symbol: string;
  sentiment: SymbolSentimentResponse | null;
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

function meterTone(label: SymbolSentimentResponse['label']): string {
  if (label === 'bullish') {
    return 'bg-emerald-400';
  }
  if (label === 'bearish') {
    return 'bg-rose-400';
  }
  if (label === 'mixed') {
    return 'bg-amber-400';
  }
  return 'bg-slate-400';
}

function badgeTone(riskFlag: SymbolSentimentResponse['risk_flag']): string {
  if (riskFlag === 'hype') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  }
  if (riskFlag === 'panic') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-200';
}

function scoreWidth(score: number | null): string {
  if (score === null) {
    return '0%';
  }
  if (score === 0) {
    return '0%';
  }
  return `${Math.max(4, Math.min(100, Math.abs(score)))}%`;
}

export function SymbolSentimentSection({
  symbol,
  sentiment,
  loading,
  refreshing,
  error,
}: SymbolSentimentSectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load symbol-specific sentiment."
        tone="empty"
      />
    );
  }

  if (loading && sentiment === null) {
    return (
      <StatePanel
        title="Loading symbol sentiment"
        message={`Building symbol-specific sentiment proxies for ${symbol}.`}
        tone="loading"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        title="Symbol sentiment unavailable"
        message={error}
        tone="error"
      />
    );
  }

  if (sentiment === null) {
    return (
      <StatePanel
        title="Symbol sentiment unavailable"
        message={`No symbol-specific sentiment view is available yet for ${symbol}.`}
        tone="empty"
      />
    );
  }

  const incomplete = sentiment.data_state !== 'ready' || sentiment.label === 'insufficient_data';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Symbol Sentiment</p>
          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">Advisory proxy inputs only - not direct external news sentiment.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={sentiment.data_state} message={sentiment.status_message} />

      {incomplete ? (
        <StatePanel
          title="Symbol sentiment is still building"
          message={sentiment.explanation ?? `Symbol-specific sentiment proxies are not ready yet for ${symbol}.`}
          tone="empty"
        />
      ) : (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Score Meter</p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {sentiment.score !== null ? `${sentiment.score > 0 ? '+' : ''}${sentiment.score}` : '-'}
                </p>
                <p className="mt-1 text-sm text-slate-400">{humanize(sentiment.label)}</p>
              </div>
              <div className="w-full max-w-md">
                <div className="h-3 rounded-full bg-slate-900">
                  <div
                    className={classNames('h-3 rounded-full transition-all', meterTone(sentiment.label))}
                    style={{ width: scoreWidth(sentiment.score) }}
                  />
                </div>
                <div className="mt-2 flex justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
                  <span>Bearish</span>
                  <span>Neutral</span>
                  <span>Bullish</span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard label="Sentiment Label" value={humanize(sentiment.label)} helper="Profit-oriented proxy read" />
            <MetricCard
              label="Confidence"
              value={sentiment.confidence !== null ? `${sentiment.confidence}/100` : '-'}
              helper="Reduced when proxy drivers disagree"
            />
            <MetricCard label="Momentum State" value={humanize(sentiment.momentum_state)} helper="Short-horizon sentiment drift" />
            <MetricCard
              label="Risk Flag"
              value={humanize(sentiment.risk_flag)}
              helper="Hype/panic warning from proxy stress"
            />
            <MetricCard label="Source Mode" value={humanize(sentiment.source_mode)} helper={`${sentiment.components.length} active sentiment drivers`} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Explanation</p>
                <span className={classNames('rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', badgeTone(sentiment.risk_flag))}>
                  {humanize(sentiment.risk_flag)}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                {sentiment.explanation ?? 'No symbol-specific sentiment explanation is available yet.'}
              </p>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Sentiment Drivers</p>
              {sentiment.components.length > 0 ? (
                <ul className="mt-3 space-y-2 text-sm text-slate-300">
                  {sentiment.components.map((item) => (
                    <li key={item} className="rounded-xl border border-slate-800/80 bg-slate-900/70 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-slate-400">No usable sentiment drivers are active yet.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
