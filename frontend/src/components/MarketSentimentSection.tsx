import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { formatDecimal } from '../lib/format';
import type { MarketSentimentResponse } from '../lib/types';

interface MarketSentimentSectionProps {
  symbol: string;
  sentiment: MarketSentimentResponse | null;
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

export function MarketSentimentSection({
  symbol,
  sentiment,
  loading,
  refreshing,
  error,
}: MarketSentimentSectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load broader market sentiment."
        tone="empty"
      />
    );
  }

  if (loading && sentiment === null) {
    return (
      <StatePanel
        title="Loading market sentiment"
        message={`Reading broader crypto context for ${symbol}.`}
        tone="loading"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        title="Market sentiment unavailable"
        message={error}
        tone="error"
      />
    );
  }

  if (sentiment === null) {
    return (
      <StatePanel
        title="Market sentiment unavailable"
        message={`No broader market sentiment view is available yet for ${symbol}.`}
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Market Sentiment</p>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={sentiment.data_state} message={sentiment.status_message} />

      {sentiment.data_state !== 'ready' ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Broader Market Context</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            {sentiment.explanation ?? `Broader market context for ${symbol} is still building from BTC, ETH, breadth, and volatility history.`}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Market State" value={humanize(sentiment.market_state)} helper="Broader crypto risk tone" />
            <MetricCard
              label="Sentiment Score"
              value={sentiment.sentiment_score !== null ? `${sentiment.sentiment_score}/100` : '-'}
              helper="Explainable heuristic score"
            />
            <MetricCard label="BTC Bias" value={humanize(sentiment.btc_bias)} helper="BTC trend and momentum proxy" />
            <MetricCard label="ETH Bias" value={humanize(sentiment.eth_bias)} helper="ETH confirmation if available" />
            <MetricCard
              label="Relative Strength"
              value={humanize(sentiment.selected_symbol_relative_strength)}
              helper={
                sentiment.relative_strength_pct !== null
                  ? `${formatDecimal(sentiment.relative_strength_pct)}% vs BTC`
                  : 'Relative strength still limited'
              }
            />
            <MetricCard
              label="Market Breadth"
              value={humanize(sentiment.market_breadth_state)}
              helper={`${sentiment.breadth_advancing_symbols} advancing / ${sentiment.breadth_declining_symbols} declining`}
            />
            <MetricCard label="Volatility Environment" value={humanize(sentiment.volatility_environment)} helper="BTC volatility proxy" />
            <MetricCard label="Breadth Sample" value={String(sentiment.breadth_sample_size)} helper="Tracked symbols with enough data" />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Market Sentiment Explanation</p>
            <p className="mt-3 text-sm leading-6 text-slate-300">{sentiment.explanation ?? 'No broader market explanation yet.'}</p>
          </div>
        </div>
      )}
    </div>
  );
}
