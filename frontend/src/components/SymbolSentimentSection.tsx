import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
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
        message={`Reading external symbol-specific sentiment for ${symbol}.`}
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

  const incomplete = sentiment.sentiment_state === 'insufficient_data';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Symbol Sentiment</p>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={sentiment.data_state} message={sentiment.status_message} />

      {incomplete ? (
        <StatePanel
          title="Symbol sentiment is insufficient"
          message={sentiment.explanation ?? `No usable external symbol sentiment is available yet for ${symbol}.`}
          tone="empty"
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Sentiment State" value={humanize(sentiment.sentiment_state)} helper="External symbol-specific tone" />
            <MetricCard
              label="Sentiment Score"
              value={sentiment.sentiment_score !== null ? `${sentiment.sentiment_score}/100` : '-'}
              helper="Source-backed score only"
            />
            <MetricCard
              label="Confidence"
              value={sentiment.confidence !== null ? `${sentiment.confidence}/100` : '-'}
              helper="Reduced when source evidence conflicts"
            />
            <MetricCard
              label="Freshness"
              value={humanize(sentiment.freshness)}
              helper={
                sentiment.freshness_minutes !== null
                  ? `${sentiment.freshness_minutes} min since latest evidence`
                  : 'No usable evidence timestamp'
              }
            />
            <MetricCard label="Source Count" value={String(sentiment.source_count)} helper="Usable evidence items only" />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Symbol Sentiment Explanation</p>
              <p className="mt-3 text-sm leading-6 text-slate-300">{sentiment.explanation ?? 'No symbol-specific sentiment explanation yet.'}</p>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Evidence Summary</p>
              {sentiment.evidence_summary.length > 0 ? (
                <ul className="mt-3 space-y-2 text-sm text-slate-300">
                  {sentiment.evidence_summary.map((item) => (
                    <li key={item} className="rounded-xl border border-slate-800/80 bg-slate-900/70 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-slate-400">No source-backed evidence summary is available.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
