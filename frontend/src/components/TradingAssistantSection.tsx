import { formatDateTime, formatDecimal } from '../lib/format';
import type { TradingAssistantResponse } from '../lib/types';
import { AdvancedDetailsPro } from './AdvancedDetailsPro';
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
  const heatmapTag = assistant.heatmap_alignment === 'confirmed'
    ? 'Heatmap Confirmed'
    : assistant.heatmap_alignment === 'conflict'
      ? 'Heatmap Conflict'
      : null;
  const crowdLine = assistant.crowd_side === 'long_crowded'
    ? 'Crowd: Long heavy (downside risk)'
    : assistant.crowd_side === 'short_crowded'
      ? 'Crowd: Short heavy (squeeze risk)'
      : 'Crowd: Balanced';
  const liquidationLine = assistant.liquidation_signal === 'cascade_down'
    ? 'Liquidation: Downside cascade in progress'
    : assistant.liquidation_signal === 'cascade_up'
      ? 'Liquidation: Short squeeze active'
      : assistant.liquidation_signal === 'exhaustion'
        ? 'Liquidation: Exhaustion detected'
        : assistant.liquidation_signal === 'sweep_confirmation'
          ? 'Liquidation: Sweep confirmation'
          : 'Liquidation: No significant activity';

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trading Assistant</p>
          <h3 className="mt-2 text-xl font-semibold text-white">{assistant.decision.replace('_', ' ').toUpperCase()}</h3>
          <p className="mt-2 text-sm text-slate-300">{assistant.simple_reason}</p>
          <p className="mt-2 text-sm font-medium text-slate-200">{crowdLine}</p>
          <p className="mt-1 text-sm font-medium text-slate-200">{liquidationLine}</p>
          {heatmapTag ? (
            <span className="mt-3 inline-flex rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-200">
              {heatmapTag}
            </span>
          ) : null}
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

      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Liquidity Bias</p>
        <div className="mt-3 grid gap-3 md:grid-cols-4">
          <div><span className="text-xs text-slate-500">Bias</span><p className="text-sm text-slate-200">{assistant.liquidity_bias}</p></div>
          <div><span className="text-xs text-slate-500">Pressure</span><p className="text-sm text-slate-200">{assistant.liquidity_pressure}</p></div>
          <div><span className="text-xs text-slate-500">Likely Sweep</span><p className="text-sm text-slate-200">{assistant.likely_liquidation_direction}</p></div>
          <div><span className="text-xs text-slate-500">Trap Risk</span><p className="text-sm text-slate-200">{assistant.trap_risk.replace('_', ' ')}</p></div>
          <div><span className="text-xs text-slate-500">Upside Zone</span><p className="text-sm text-slate-200">{assistant.upside_liquidity_zone.level ? formatDecimal(assistant.upside_liquidity_zone.level) : '-'}</p></div>
          <div><span className="text-xs text-slate-500">Downside Zone</span><p className="text-sm text-slate-200">{assistant.downside_liquidity_zone.level ? formatDecimal(assistant.downside_liquidity_zone.level) : '-'}</p></div>
          <div><span className="text-xs text-slate-500">Nearest Target</span><p className="text-sm text-slate-200">{assistant.nearest_liquidity_target.direction}</p></div>
          <div><span className="text-xs text-slate-500">TP/SL Alignment</span><p className="text-sm text-slate-200">{assistant.tp_sl_alignment.replace(/_/g, ' ')}</p></div>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-300">{assistant.liquidity_explanation}</p>
        <p className="mt-2 text-sm leading-6 text-slate-300">{assistant.liquidity_zone_explanation}</p>
      </div>

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

      <AdvancedDetailsPro>
        <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
          <div><span className="text-slate-500">Base Signal</span><p>{assistant.base_signal_type} ({assistant.base_confidence}%)</p></div>
          <div><span className="text-slate-500">Heatmap Signal</span><p>{assistant.heatmap_signal_type} ({assistant.heatmap_confidence}%)</p></div>
          <div><span className="text-slate-500">Heatmap Bias</span><p>{assistant.heatmap_bias.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Heatmap Intensity</span><p>{assistant.heatmap_intensity_score ?? '-'}</p></div>
          <div><span className="text-slate-500">Heatmap Above</span><p>{assistant.heatmap_liquidity_above ? formatDecimal(assistant.heatmap_liquidity_above) : '-'}</p></div>
          <div><span className="text-slate-500">Heatmap Below</span><p>{assistant.heatmap_liquidity_below ? formatDecimal(assistant.heatmap_liquidity_below) : '-'}</p></div>
          <div><span className="text-slate-500">Heatmap Provider</span><p>{assistant.heatmap_provider.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Data Quality</span><p>{assistant.heatmap_data_quality.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Real Data</span><p>{assistant.heatmap_is_real_data ? 'Yes' : 'No'}</p></div>
          <div><span className="text-slate-500">Liquidation Pressure</span><p>{assistant.liquidation_pressure}</p></div>
          <div><span className="text-slate-500">Liquidation Signal</span><p>{assistant.liquidation_signal.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Liquidation Intensity</span><p>{assistant.liquidation_intensity}</p></div>
          <div><span className="text-slate-500">Dominant Side</span><p>{assistant.dominant_side.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Long Liq Volume</span><p>{formatDecimal(assistant.liquidation_volume_long)}</p></div>
          <div><span className="text-slate-500">Short Liq Volume</span><p>{formatDecimal(assistant.liquidation_volume_short)}</p></div>
          <div><span className="text-slate-500">Liq Imbalance</span><p>{formatDecimal(assistant.liquidation_imbalance_ratio)}</p></div>
          <div><span className="text-slate-500">Event Frequency</span><p>{formatDecimal(assistant.liquidation_event_frequency)}/min</p></div>
          <div><span className="text-slate-500">Funding Rate</span><p>{assistant.funding_rate ? formatDecimal(assistant.funding_rate) : '-'}</p></div>
          <div><span className="text-slate-500">Open Interest</span><p>{assistant.open_interest ? formatDecimal(assistant.open_interest) : '-'}</p></div>
          <div><span className="text-slate-500">OI Trend</span><p>{assistant.oi_trend}</p></div>
          <div><span className="text-slate-500">Crowd Side</span><p>{assistant.crowd_side.replace(/_/g, ' ')}</p></div>
          <div><span className="text-slate-500">Squeeze Risk</span><p>{assistant.squeeze_risk.replace(/_/g, ' ')}</p></div>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-300">{assistant.heatmap_explanation}</p>
        <p className="mt-2 text-sm leading-6 text-slate-300">{assistant.positioning_explanation}</p>
        <p className="mt-2 text-sm leading-6 text-slate-300">{assistant.liquidation_explanation}</p>
        {!assistant.heatmap_is_real_data ? (
          <p className="mt-2 text-sm leading-6 text-amber-200">Heatmap data is mock/estimated. Do not treat as real market heatmap.</p>
        ) : null}
      </AdvancedDetailsPro>
    </div>
  );
}
