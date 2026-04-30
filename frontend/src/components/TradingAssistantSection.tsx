import { formatDateTime, formatDecimal } from '../lib/format';
import type { TradingAssistantResponse } from '../lib/types';
import { StatePanel } from './StatePanel';

interface TradingAssistantSectionProps {
  symbol: string;
  assistant: TradingAssistantResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

export function TradingAssistantSection({ symbol, assistant, loading, refreshing, error }: TradingAssistantSectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to get a beginner trading summary." tone="empty" />;
  }
  if (loading && !assistant) {
    return <StatePanel title="Loading trading assistant" message={`Preparing a simpler decision view for ${symbol}.`} tone="loading" />;
  }
  if (error) {
    return <StatePanel title="Trading assistant unavailable" message={error} tone="error" />;
  }
  if (!assistant) {
    return <StatePanel title="No trading assistant data" message={`No beginner trading summary is available for ${symbol} yet.`} tone="empty" />;
  }
  const similarSetup = assistant.similar_setup;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trading Assistant</p>
          <h3 className="mt-2 text-xl font-semibold text-white">{assistant.decision.replace('_', ' ').toUpperCase()}</h3>
          <p className="mt-2 text-sm text-slate-300">{assistant.simple_reason}</p>
        </div>
        <div className="text-right text-xs text-slate-400">
          <p>{refreshing ? 'Refreshing...' : 'Current summary'}</p>
          <p className="mt-1">History {assistant.backfill_status.status}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Confidence</p>
          <p className="mt-2 text-lg font-semibold text-white">{assistant.confidence_label} ({assistant.confidence_score}%)</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Risk</p>
          <p className="mt-2 text-lg font-semibold text-white">{assistant.risk_label}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Best Timeframe</p>
          <p className="mt-2 text-lg font-semibold text-white">{assistant.best_timeframe}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Backfill</p>
          <p className="mt-2 text-lg font-semibold text-white">{assistant.backfill_status.coverage_pct}%</p>
          <p className="mt-1 text-xs text-slate-400">{assistant.backfill_status.requested_interval} over {assistant.backfill_status.requested_lookback_days}d</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Suggested Entry Zone</p>
          <p className="mt-2 text-sm text-slate-200">{assistant.suggested_entry_zone ?? 'Not enough clean context yet'}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Stop Loss</p>
          <p className="mt-2 text-sm text-slate-200">{assistant.suggested_stop_loss ? formatDecimal(assistant.suggested_stop_loss) : 'Not set'}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Take Profit</p>
          <p className="mt-2 text-sm text-slate-200">{assistant.suggested_take_profit ? formatDecimal(assistant.suggested_take_profit) : 'Not set'}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">History Window</p>
          <p className="mt-2 text-sm text-slate-200">{assistant.backfill_status.available_from ? formatDateTime(assistant.backfill_status.available_from) : 'Not started'}</p>
          <p className="mt-1 text-xs text-slate-400">to {assistant.backfill_status.available_to ? formatDateTime(assistant.backfill_status.available_to) : '-'}</p>
        </div>
      </div>

      {assistant.why_not_trade ? (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <p className="font-semibold uppercase tracking-[0.14em] text-amber-300">Why not trade now</p>
          <p className="mt-2 leading-6">{assistant.why_not_trade}</p>
        </div>
      ) : null}

      {similarSetup ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Similar Setups</p>
              <p className="mt-2 text-sm text-slate-300">{similarSetup.explanation}</p>
            </div>
            <div className="text-right text-xs text-slate-400">
              <p>{similarSetup.matching_sample_size} evaluated matches</p>
              <p className="mt-1">Best horizon {similarSetup.best_horizon ?? '-'}</p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-200">
              {similarSetup.reliability_label.replace('_', ' ')}
            </span>
            {similarSetup.matched_attributes.slice(0, 4).map((attribute) => (
              <span key={attribute} className="rounded-full border border-slate-800 px-3 py-1 text-slate-400">
                {attribute}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
