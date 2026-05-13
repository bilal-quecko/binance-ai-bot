import { classNames, formatCurrency, formatDateTime, formatDecimal } from '../lib/format';
import type { LeverageOption } from '../lib/futuresLeverage';
import {
  buildScannerUnavailableMessage,
  hasScannerCandidates,
  isLastSuccessfulScannerCache,
  scannerCandidateCount,
} from '../lib/futures-scanner-ux.js';
import type { FuturesLivePriceItemResponse, FuturesLivePriceResponse, FuturesOpportunityScanResponse, FuturesPaperSignalResponse } from '../lib/types';
import { AdvancedDetailsPro } from './AdvancedDetailsPro';
import { StatePanel } from './StatePanel';

interface FuturesScannerFilters {
  maxSymbols: number;
  minOpportunityScore: number;
  includeWeakEvidence: boolean;
  horizon: string;
  includeAvoid: boolean;
}

interface FuturesPaperScannerSectionProps {
  scan: FuturesOpportunityScanResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  livePrices: FuturesLivePriceResponse | null;
  livePricesLoading: boolean;
  livePricesError: string | null;
  heartbeatNow: Date;
  filters: FuturesScannerFilters;
  onFiltersChange: (filters: FuturesScannerFilters) => void;
  autoRescanMinutes: 0 | 5 | 15;
  onAutoRescanChange: (minutes: 0 | 5 | 15) => void;
  selectedLeverage?: LeverageOption;
  onSelectedLeverageChange?: (leverage: LeverageOption) => void;
  onViewSignal?: (symbol: string) => void;
  onSimulate?: (symbol: string) => void;
  onRefresh: () => void;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.replace(/_/g, ' ');
}

function cardTone(direction: FuturesPaperSignalResponse['direction']): string {
  if (direction === 'long') {
    return 'border-longGreen/30 bg-longGreen/10 shadow-greenGlow';
  }
  if (direction === 'short') {
    return 'border-shortRed/30 bg-shortRed/10';
  }
  if (direction === 'wait') {
    return 'border-waitAmber/25 bg-waitAmber/8';
  }
  return 'border-borderSoft bg-cardBg/75';
}

function badgeTone(direction: FuturesPaperSignalResponse['direction']): string {
  if (direction === 'long') {
    return 'border-longGreen/40 bg-longGreen/10 text-emerald-100';
  }
  if (direction === 'short') {
    return 'border-shortRed/40 bg-shortRed/10 text-rose-100';
  }
  if (direction === 'wait') {
    return 'border-waitAmber/40 bg-waitAmber/10 text-amber-100';
  }
  return 'border-neutralBlue/35 bg-neutralBlue/10 text-blue-100';
}

function liquidityLine(signal: FuturesPaperSignalResponse): string {
  if (signal.sweep_risk === 'downside_sweep') {
    return 'Liquidity: Downside sweep risk';
  }
  if (signal.sweep_risk === 'upside_sweep') {
    return 'Liquidity: Upside liquidity target nearby';
  }
  if (signal.sweep_risk === 'both_sides' || signal.trade_timing_adjustment === 'avoid_chop') {
    return 'Liquidity: Choppy both-side liquidity';
  }
  if (signal.nearest_liquidity_target.direction === 'up' && signal.nearest_liquidity_target.strength !== 'low') {
    return 'Liquidity: Upside liquidity target nearby';
  }
  if (signal.nearest_liquidity_target.direction === 'down' && signal.nearest_liquidity_target.strength !== 'low') {
    return 'Liquidity: Downside liquidity target nearby';
  }
  return 'Liquidity: Clean path';
}

function crowdLine(signal: FuturesPaperSignalResponse): string {
  if (signal.crowd_side === 'long_crowded') {
    return 'Crowd: Long heavy (downside risk)';
  }
  if (signal.crowd_side === 'short_crowded') {
    return 'Crowd: Short heavy (squeeze risk)';
  }
  return 'Crowd: Balanced';
}

function liquidationLine(signal: FuturesPaperSignalResponse): string {
  if (signal.liquidation_signal === 'cascade_down') {
    return 'Liquidation: Downside cascade in progress';
  }
  if (signal.liquidation_signal === 'cascade_up') {
    return 'Liquidation: Short squeeze active';
  }
  if (signal.liquidation_signal === 'exhaustion') {
    return 'Liquidation: Exhaustion detected';
  }
  if (signal.liquidation_signal === 'sweep_confirmation') {
    return 'Liquidation: Sweep confirmation';
  }
  return 'Liquidation: No significant activity';
}

type HeartbeatStatus = 'active' | 'near_take_profit' | 'take_profit_touched' | 'near_stop' | 'invalidated' | 'stale';

interface SignalHeartbeat {
  livePrice: number | null;
  livePriceUpdatedAt: string | null;
  liveChangeSinceScan: number | null;
  distanceToStop: number | null;
  distanceToTakeProfit: number | null;
  signalAgeSeconds: number;
  livePriceAgeSeconds: number | null;
  status: HeartbeatStatus;
  warning: string | null;
  source: FuturesLivePriceItemResponse['source'] | null;
  priceType: FuturesLivePriceItemResponse['price_type'] | FuturesPaperSignalResponse['price_type'] | null;
}

function parseNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function secondsBetween(start: string | null | undefined, now: Date): number | null {
  if (!start) {
    return null;
  }
  const parsed = new Date(start).getTime();
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.max(0, Math.floor((now.getTime() - parsed) / 1000));
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function formatSignedPct(value: number | null): string {
  if (value === null) {
    return '-';
  }
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatDistance(value: number | null): string {
  if (value === null) {
    return '-';
  }
  return `${value.toFixed(2)}%`;
}

function heartbeatStatusTone(status: HeartbeatStatus): string {
  if (status === 'take_profit_touched' || status === 'near_take_profit') {
    return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100';
  }
  if (status === 'invalidated' || status === 'near_stop') {
    return 'border-rose-400/40 bg-rose-400/10 text-rose-100';
  }
  if (status === 'stale') {
    return 'border-amber-400/40 bg-amber-400/10 text-amber-100';
  }
  return 'border-sky-400/40 bg-sky-400/10 text-sky-100';
}

function heartbeatStatusLabel(status: HeartbeatStatus): string {
  return {
    active: 'Active',
    near_take_profit: 'Near TP',
    take_profit_touched: 'TP Touched',
    near_stop: 'Near Stop',
    invalidated: 'Invalidated',
    stale: 'Stale',
  }[status];
}

function heartbeatSourceLabel(source: FuturesLivePriceItemResponse['source'] | null): string {
  if (source === 'websocket') {
    return 'WS';
  }
  if (source === 'rest') {
    return 'REST';
  }
  if (source === 'cache') {
    return 'Cache';
  }
  if (source === 'unavailable') {
    return 'Unavailable';
  }
  return 'None';
}

function heartbeatSourceTone(source: FuturesLivePriceItemResponse['source'] | null): string {
  if (source === 'websocket') {
    return 'border-emerald-400/35 bg-emerald-400/10 text-emerald-100';
  }
  if (source === 'rest') {
    return 'border-sky-400/35 bg-sky-400/10 text-sky-100';
  }
  if (source === 'cache') {
    return 'border-amber-400/35 bg-amber-400/10 text-amber-100';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-300';
}

function priceTypeLabel(priceType: FuturesLivePriceItemResponse['price_type'] | FuturesPaperSignalResponse['price_type'] | null): string {
  return priceType === 'mark_price' ? 'Futures Mark Price' : 'Futures Price';
}

function dataSourceLabel(dataSource: string | null | undefined): string {
  return dataSource === 'binance_usdm_futures' ? 'binance_usdm_futures' : (dataSource ?? '-');
}

function heatmapTag(signal: FuturesPaperSignalResponse): string | null {
  if (signal.heatmap_alignment === 'confirmed') {
    return 'Heatmap Confirmed';
  }
  if (signal.heatmap_alignment === 'conflict') {
    return 'Heatmap Conflict';
  }
  return null;
}

function heatmapTagTone(signal: FuturesPaperSignalResponse): string {
  if (signal.heatmap_alignment === 'confirmed') {
    return 'border-emerald-400/35 bg-emerald-400/10 text-emerald-100';
  }
  if (signal.heatmap_alignment === 'conflict') {
    return 'border-amber-400/35 bg-amber-400/10 text-amber-100';
  }
  return 'border-slate-700 bg-slate-900/70 text-slate-300';
}

function buildHeartbeat(
  signal: FuturesPaperSignalResponse,
  livePrice: FuturesLivePriceItemResponse | undefined,
  now: Date,
): SignalHeartbeat {
  const live = parseNumber(livePrice?.live_price);
  const scan = parseNumber(signal.current_price);
  const stop = parseNumber(signal.suggested_stop_loss);
  const takeProfit = parseNumber(signal.suggested_take_profit);
  const signalAgeSeconds = secondsBetween(signal.timestamp, now) ?? 0;
  const livePriceAgeSeconds = secondsBetween(livePrice?.updated_at, now);
  const stale = livePrice?.stale === true || live === null || livePriceAgeSeconds === null || livePriceAgeSeconds > 30;
  if (stale) {
    return {
      livePrice: live,
      livePriceUpdatedAt: livePrice?.updated_at ?? null,
      liveChangeSinceScan: null,
      distanceToStop: null,
      distanceToTakeProfit: null,
      signalAgeSeconds,
      livePriceAgeSeconds,
      status: 'stale',
      warning: livePrice?.warning ?? 'No live price heartbeat received in the last 30 seconds.',
      source: livePrice?.source ?? null,
      priceType: livePrice?.price_type ?? signal.price_type,
    };
  }

  let liveChangeSinceScan: number | null = null;
  if (scan !== null && scan > 0) {
    liveChangeSinceScan = signal.direction === 'short'
      ? ((scan - live) / scan) * 100
      : ((live - scan) / scan) * 100;
  }

  let distanceToStop: number | null = null;
  let distanceToTakeProfit: number | null = null;
  if (signal.direction === 'long') {
    distanceToStop = stop !== null ? ((live - stop) / live) * 100 : null;
    distanceToTakeProfit = takeProfit !== null ? ((takeProfit - live) / live) * 100 : null;
  } else if (signal.direction === 'short') {
    distanceToStop = stop !== null ? ((stop - live) / live) * 100 : null;
    distanceToTakeProfit = takeProfit !== null ? ((live - takeProfit) / live) * 100 : null;
  }

  let status: HeartbeatStatus = 'active';
  if (signal.direction === 'long') {
    if (stop !== null && live <= stop) {
      status = 'invalidated';
    } else if (takeProfit !== null && live >= takeProfit) {
      status = 'take_profit_touched';
    } else if (distanceToStop !== null && distanceToStop >= 0 && distanceToStop <= 0.35) {
      status = 'near_stop';
    } else if (distanceToTakeProfit !== null && distanceToTakeProfit >= 0 && distanceToTakeProfit <= 0.35) {
      status = 'near_take_profit';
    }
  } else if (signal.direction === 'short') {
    if (stop !== null && live >= stop) {
      status = 'invalidated';
    } else if (takeProfit !== null && live <= takeProfit) {
      status = 'take_profit_touched';
    } else if (distanceToStop !== null && distanceToStop >= 0 && distanceToStop <= 0.35) {
      status = 'near_stop';
    } else if (distanceToTakeProfit !== null && distanceToTakeProfit >= 0 && distanceToTakeProfit <= 0.35) {
      status = 'near_take_profit';
    }
  }

  return {
    livePrice: live,
    livePriceUpdatedAt: livePrice?.updated_at ?? null,
    liveChangeSinceScan,
    distanceToStop,
    distanceToTakeProfit,
    signalAgeSeconds,
    livePriceAgeSeconds,
    status,
    warning: livePrice?.warning ?? null,
    source: livePrice?.source ?? null,
    priceType: livePrice?.price_type ?? signal.price_type,
  };
}

function SignalCard({
  signal,
  livePrice,
  heartbeatNow,
  onViewSignal,
  onSimulate,
}: {
  signal: FuturesPaperSignalResponse;
  livePrice: FuturesLivePriceItemResponse | undefined;
  heartbeatNow: Date;
  onViewSignal: (symbol: string) => void;
  onSimulate: (symbol: string) => void;
}) {
  const heartbeat = buildHeartbeat(signal, livePrice, heartbeatNow);
  const showSource = heartbeat.status === 'stale' || heartbeat.source === 'cache' || heartbeat.source === 'unavailable';
  const criticalWarnings = signal.warnings.filter((warning) => /error|fail|unavailable|stale|risk|liquid/i.test(warning));
  const heatmapLabel = heatmapTag(signal);
  const livePriceLabel = priceTypeLabel(heartbeat.priceType);
  return (
    <article className={classNames('min-w-0 rounded-lg border p-4 shadow-sm', cardTone(signal.direction))}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-textPrimary">{signal.symbol}</h3>
            <span className={classNames('rounded-md border px-3 py-1 text-xs font-semibold', badgeTone(signal.direction))}>
              {signal.direction.toUpperCase()}
            </span>
            <span className={classNames('rounded-md border px-3 py-1 text-xs font-semibold', heartbeatStatusTone(heartbeat.status))}>
              {heartbeatStatusLabel(heartbeat.status)}
            </span>
            {showSource ? (
              <span className={classNames('rounded-md border px-3 py-1 text-xs font-semibold', heartbeatSourceTone(heartbeat.source))}>
                {heartbeatSourceLabel(heartbeat.source)}
              </span>
            ) : null}
            <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1 text-xs font-semibold text-textSecondary">
              Validation {signal.validation_score !== null ? `${signal.validation_score}%` : 'pending'}
            </span>
            {heatmapLabel ? (
              <span className={classNames('rounded-md border px-3 py-1 text-xs font-semibold text-slate-300', heatmapTagTone(signal))}>
                {heatmapLabel}
              </span>
            ) : null}
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-textSecondary">{signal.reason}</p>
        </div>
        <div className="grid min-w-40 grid-cols-2 gap-3 text-right">
          <div className="rounded-md border border-borderSoft bg-panelBg/70 p-3">
            <p className="text-2xl font-semibold text-textPrimary">{signal.opportunity_score}</p>
            <p className="text-xs text-textMuted">Score</p>
          </div>
          <div className="rounded-md border border-borderSoft bg-panelBg/70 p-3">
            <p className="text-2xl font-semibold text-textPrimary">{signal.confidence}%</p>
            <p className="text-xs text-textMuted">Confidence</p>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 text-sm text-textSecondary sm:grid-cols-2 lg:grid-cols-5">
        <div><span className="text-textMuted">Entry</span><p className="font-semibold text-textPrimary">{signal.suggested_entry_zone ?? (signal.current_price ? formatCurrency(signal.current_price) : '-')}</p></div>
        <div><span className="text-textMuted">Stop</span><p>{signal.suggested_stop_loss ? formatDecimal(signal.suggested_stop_loss) : '-'}</p></div>
        <div><span className="text-textMuted">Take Profit</span><p>{signal.suggested_take_profit ? formatDecimal(signal.suggested_take_profit) : '-'}</p></div>
        <div><span className="text-textMuted">{livePriceLabel}</span><p>{heartbeat.livePrice !== null ? formatCurrency(heartbeat.livePrice) : '-'}</p></div>
        <div><span className="text-textMuted">Live Move</span><p className={heartbeat.liveChangeSinceScan !== null && heartbeat.liveChangeSinceScan < 0 ? 'text-rose-200' : 'text-emerald-200'}>{formatSignedPct(heartbeat.liveChangeSinceScan)}</p></div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onViewSignal(signal.symbol)}
          className="rounded-md border border-accentPurple/35 bg-accentPurple/15 px-3 py-2 text-sm font-medium text-violet-100 transition hover:border-accentPurple hover:bg-accentPurple/25"
        >
          View Signal
        </button>
        <button
          type="button"
          onClick={() => onSimulate(signal.symbol)}
          className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-2 text-sm font-medium text-textSecondary transition hover:border-borderMedium hover:text-textPrimary"
        >
          Simulate
        </button>
        <span className="text-xs text-textMuted">{liquidityLine(signal)} | {crowdLine(signal)} | {liquidationLine(signal)}</span>
      </div>

      <div className="mt-4">
        <AdvancedDetailsPro>
          <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
            <div><span className="text-slate-500">Trend</span><p>{humanize(signal.trend)}</p></div>
            <div><span className="text-slate-500">Momentum</span><p>{humanize(signal.momentum)}</p></div>
            <div><span className="text-slate-500">Best Horizon</span><p>{signal.best_horizon}</p></div>
            <div><span className="text-slate-500">Evidence Level</span><p>{humanize(signal.evidence_strength)}</p></div>
            <div><span className="text-slate-500">Risk</span><p>{signal.risk_grade}</p></div>
            <div><span className="text-slate-500">Signal Age</span><p>{formatDuration(heartbeat.signalAgeSeconds)}</p></div>
            <div><span className="text-slate-500">Stop</span><p>{signal.suggested_stop_loss ? formatDecimal(signal.suggested_stop_loss) : '-'}</p></div>
            <div><span className="text-slate-500">Take Profit</span><p>{signal.suggested_take_profit ? formatDecimal(signal.suggested_take_profit) : '-'}</p></div>
            <div><span className="text-slate-500">Distance to Stop</span><p>{formatDistance(heartbeat.distanceToStop)}</p></div>
            <div><span className="text-slate-500">Distance to TP</span><p>{formatDistance(heartbeat.distanceToTakeProfit)}</p></div>
            <div><span className="text-slate-500">Heartbeat Source</span><p>{heartbeatSourceLabel(heartbeat.source)}</p></div>
            <div><span className="text-slate-500">Data Source</span><p>{dataSourceLabel(signal.data_source)}</p></div>
            <div><span className="text-slate-500">Price Type</span><p>{humanize(heartbeat.priceType ?? signal.price_type)}</p></div>
            <div><span className="text-slate-500">Scan Time</span><p>{formatDateTime(signal.timestamp)}</p></div>
            <div><span className="text-slate-500">Liquidity Bias</span><p>{humanize(signal.liquidity_bias)}</p></div>
            <div><span className="text-slate-500">Liquidity Pressure</span><p>{humanize(signal.liquidity_pressure)}</p></div>
            <div><span className="text-slate-500">Likely Sweep</span><p>{humanize(signal.likely_liquidation_direction)}</p></div>
            <div><span className="text-slate-500">Trap Risk</span><p>{humanize(signal.trap_risk)}</p></div>
            <div><span className="text-slate-500">Upside Liquidity Zone</span><p>{signal.upside_liquidity_zone.level ? formatDecimal(signal.upside_liquidity_zone.level) : '-'}</p></div>
            <div><span className="text-slate-500">Downside Liquidity Zone</span><p>{signal.downside_liquidity_zone.level ? formatDecimal(signal.downside_liquidity_zone.level) : '-'}</p></div>
            <div><span className="text-slate-500">Nearest Liquidity Target</span><p>{humanize(signal.nearest_liquidity_target.direction)} {signal.nearest_liquidity_target.distance_pct ? `${formatDecimal(signal.nearest_liquidity_target.distance_pct)}%` : ''}</p></div>
            <div><span className="text-slate-500">Sweep Risk</span><p>{humanize(signal.sweep_risk)}</p></div>
            <div><span className="text-slate-500">Trade Timing</span><p>{humanize(signal.trade_timing_adjustment)}</p></div>
            <div><span className="text-slate-500">TP/SL Alignment</span><p>{humanize(signal.tp_sl_alignment)}</p></div>
            <div><span className="text-slate-500">Base Signal</span><p>{signal.base_signal_type} ({signal.base_confidence}%)</p></div>
            <div><span className="text-slate-500">Heatmap Signal</span><p>{signal.heatmap_signal_type} ({signal.heatmap_confidence}%)</p></div>
            <div><span className="text-slate-500">Heatmap Bias</span><p>{humanize(signal.heatmap_bias)}</p></div>
            <div><span className="text-slate-500">Heatmap Intensity</span><p>{signal.heatmap_intensity_score ?? '-'}</p></div>
            <div><span className="text-slate-500">Heatmap Above</span><p>{signal.heatmap_liquidity_above ? formatDecimal(signal.heatmap_liquidity_above) : '-'}</p></div>
            <div><span className="text-slate-500">Heatmap Below</span><p>{signal.heatmap_liquidity_below ? formatDecimal(signal.heatmap_liquidity_below) : '-'}</p></div>
            <div><span className="text-slate-500">Heatmap Provider</span><p>{humanize(signal.heatmap_provider)}</p></div>
            <div><span className="text-slate-500">Data Quality</span><p>{humanize(signal.heatmap_data_quality)}</p></div>
            <div><span className="text-slate-500">Real Data</span><p>{signal.heatmap_is_real_data ? 'Yes' : 'No'}</p></div>
            <div><span className="text-slate-500">Liquidation Pressure</span><p>{humanize(signal.liquidation_pressure)}</p></div>
            <div><span className="text-slate-500">Liquidation Signal</span><p>{humanize(signal.liquidation_signal)}</p></div>
            <div><span className="text-slate-500">Liquidation Intensity</span><p>{humanize(signal.liquidation_intensity)}</p></div>
            <div><span className="text-slate-500">Dominant Side</span><p>{humanize(signal.dominant_side)}</p></div>
            <div><span className="text-slate-500">Long Liq Volume</span><p>{formatDecimal(signal.liquidation_volume_long)}</p></div>
            <div><span className="text-slate-500">Short Liq Volume</span><p>{formatDecimal(signal.liquidation_volume_short)}</p></div>
            <div><span className="text-slate-500">Liq Imbalance</span><p>{formatDecimal(signal.liquidation_imbalance_ratio)}</p></div>
            <div><span className="text-slate-500">Event Frequency</span><p>{formatDecimal(signal.liquidation_event_frequency)}/min</p></div>
            <div><span className="text-slate-500">Funding Rate</span><p>{signal.funding_rate ? formatDecimal(signal.funding_rate) : '-'}</p></div>
            <div><span className="text-slate-500">Open Interest</span><p>{signal.open_interest ? formatDecimal(signal.open_interest) : '-'}</p></div>
            <div><span className="text-slate-500">OI Trend</span><p>{humanize(signal.oi_trend)}</p></div>
            <div><span className="text-slate-500">Crowd Side</span><p>{humanize(signal.crowd_side)}</p></div>
            <div><span className="text-slate-500">Squeeze Risk</span><p>{humanize(signal.squeeze_risk)}</p></div>
          </div>
          <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-3 xl:grid-cols-6">
            <p>Trend {signal.trend_score}</p>
            <p>Momentum {signal.momentum_score}</p>
            <p>Direction {signal.direction_score}</p>
            <p>Volatility {signal.volatility_quality_score}</p>
            <p>Liquidity {signal.liquidity_score}</p>
            <p>Validation {signal.validation_score ?? '-'}</p>
          </div>
          <div className="mt-4 grid gap-3 text-xs text-slate-400 lg:grid-cols-2">
            <p>{signal.invalidation_hint ?? 'No invalidation level is available yet.'}</p>
            <p>{signal.liquidation_safety_note}</p>
          </div>
          <p className="mt-3 text-xs text-slate-400">{signal.liquidity_explanation}</p>
          <p className="mt-2 text-xs text-slate-400">{signal.liquidity_zone_explanation}</p>
          <p className="mt-2 text-xs text-slate-400">{signal.heatmap_explanation}</p>
          <p className="mt-2 text-xs text-slate-400">{signal.liquidation_explanation}</p>
          {!signal.heatmap_is_real_data ? (
            <p className="mt-2 text-xs text-amber-200">Heatmap data is mock/estimated. Do not treat as real market heatmap.</p>
          ) : null}
          {signal.liquidity_adjusted_note ? (
            <p className="mt-2 text-xs text-amber-200">{signal.liquidity_adjusted_note}</p>
          ) : null}
        </AdvancedDetailsPro>
      </div>
      {heartbeat.status === 'stale' || heartbeat.warning ? (
        <p className="mt-3 text-xs text-amber-200">
          {heartbeat.warning ?? 'Heartbeat is stale. Refreshing live prices will recover this card when Binance ticker data is available.'}
        </p>
      ) : null}
      {criticalWarnings.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {criticalWarnings.slice(0, 3).map((warning) => (
            <span key={warning} className="rounded-full border border-amber-400/25 px-3 py-1 text-xs text-amber-100">
              {warning}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function CandidateGroup({
  title,
  items,
  empty,
  livePriceBySymbol,
  heartbeatNow,
  onViewSignal,
  onSimulate,
}: {
  title: string;
  items: FuturesPaperSignalResponse[];
  empty: string;
  livePriceBySymbol: Map<string, FuturesLivePriceItemResponse>;
  heartbeatNow: Date;
  onViewSignal: (symbol: string) => void;
  onSimulate: (symbol: string) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      {items.length === 0 ? (
        <StatePanel title={empty} message="No high-quality candidates matched the current filters." tone="empty" />
      ) : (
        <div className="grid gap-3">
          {items.map((signal) => (
            <SignalCard
              key={`${signal.symbol}-${signal.direction}`}
              signal={signal}
              livePrice={livePriceBySymbol.get(signal.symbol)}
              heartbeatNow={heartbeatNow}
              onViewSignal={onViewSignal}
              onSimulate={onSimulate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ScannerProgress({
  active,
  scan,
  maxSymbols,
}: {
  active: boolean;
  scan: FuturesOpportunityScanResponse | null;
  maxSymbols: number;
}) {
  if (!active) {
    return null;
  }
  if (scan) {
    return (
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-sky-200 border-t-transparent" />
        Updating futures scanner
      </div>
    );
  }
  return (
    <div className="mb-5 rounded-lg border border-sky-400/25 bg-sky-400/10 p-4 text-sm text-sky-100">
      <div className="flex flex-wrap items-center gap-3">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-transparent" />
        <div>
          <p className="font-semibold">Preparing USD-M Futures symbol universe</p>
          <p className="mt-1 text-xs text-sky-200">Scanning up to {maxSymbols} symbols. Partial results will appear as soon as the scan completes.</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-sky-200 sm:grid-cols-2 lg:grid-cols-4">
        <span>Fetching USD-M Futures candles</span>
        <span>Analyzing trend and momentum</span>
        <span>Ranking LONG candidates</span>
        <span>Ranking SHORT candidates</span>
      </div>
    </div>
  );
}

export function FuturesPaperScannerSection({
  scan,
  loading,
  refreshing,
  error,
  livePrices,
  livePricesLoading,
  livePricesError,
  heartbeatNow,
  filters,
  onFiltersChange,
  autoRescanMinutes,
  onAutoRescanChange,
  onViewSignal = () => undefined,
  onSimulate = () => undefined,
  onRefresh,
}: FuturesPaperScannerSectionProps) {
  if (error && !scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <StatePanel
          title="No scanner results yet"
          message={buildScannerUnavailableMessage(error, false)}
          tone="empty"
        />
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing || loading}
          className="mt-4 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20 focus:outline-none focus:ring-2 focus:ring-sky-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Retry Scanner
        </button>
      </section>
    );
  }
  if (loading && !scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <ScannerProgress active scan={scan} maxSymbols={filters.maxSymbols} />
        <StatePanel title="Loading futures paper scanner" message="Scanning symbols for advisory long/short paper opportunities." tone="loading" />
      </section>
    );
  }
  if (!scan) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
        <StatePanel
          title="No scanner results yet"
          message="No scanner results yet. Run scanner when Binance API is available."
          tone="empty"
        />
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing || loading}
          className="mt-4 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20 focus:outline-none focus:ring-2 focus:ring-sky-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Retry Scanner
        </button>
      </section>
    );
  }
  const livePriceBySymbol = new Map((livePrices?.items ?? []).map((item) => [item.symbol, item]));
  const candidateCount = scannerCandidateCount(scan);
  const hasCandidates = hasScannerCandidates(scan);
  const showingLastSuccessfulCache = isLastSuccessfulScannerCache(scan);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-5 shadow-glow">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Futures Paper Scanner</p>
          <h2 className="mt-2 text-xl font-semibold text-white">Long/Short Opportunity Intelligence</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            Paper Futures Mode - Advisory Only - No Real Orders - Long/Short Simulation
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
            {scan.scan_state}
          </span>
          {error ? (
            <span className="rounded-full border border-amber-400/35 bg-amber-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-amber-100">
              last refresh failed
            </span>
          ) : null}
          {showingLastSuccessfulCache ? (
            <span className="rounded-full border border-amber-400/35 bg-amber-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-amber-100">
              cached degraded
            </span>
          ) : null}
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
            heartbeat {livePricesLoading ? 'updating' : 'live'}
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing || loading}
            className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing || loading ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Min Opportunity</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.minOpportunityScore}
            onChange={(event) => onFiltersChange({ ...filters, minOpportunityScore: Number(event.target.value) })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          />
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Max Symbols</span>
          <select
            value={filters.maxSymbols}
            onChange={(event) => onFiltersChange({ ...filters, maxSymbols: Number(event.target.value) })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            <option value={20}>20 symbols</option>
            <option value={50}>50 symbols</option>
            <option value={100}>100 symbols</option>
          </select>
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Horizon</span>
          <select
            value={filters.horizon}
            onChange={(event) => onFiltersChange({ ...filters, horizon: event.target.value })}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="7d">7d</option>
          </select>
        </label>
        <label className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Auto Re-Scan</span>
          <select
            value={autoRescanMinutes}
            onChange={(event) => onAutoRescanChange(Number(event.target.value) as 0 | 5 | 15)}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            <option value={0}>Off</option>
            <option value={5}>Every 5 minutes</option>
            <option value={15}>Every 15 minutes</option>
          </select>
        </label>
        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={filters.includeAvoid}
              onChange={(event) => onFiltersChange({ ...filters, includeAvoid: event.target.checked })}
            />
            Include WAIT/AVOID
          </label>
        </div>
      </div>

      <ScannerProgress active={loading || refreshing} scan={scan} maxSymbols={filters.maxSymbols} />

      {error ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          <p>{buildScannerUnavailableMessage(error, hasCandidates)}</p>
          {hasCandidates ? (
            <p className="mt-1 text-xs text-amber-200">Showing the last successful futures scanner result.</p>
          ) : null}
        </div>
      ) : null}

      {showingLastSuccessfulCache ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          Binance API unavailable; showing last successful scanner result.
        </div>
      ) : null}

      {filters.maxSymbols === 100 ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100">
          Large scan may take longer and use more Binance requests.
        </div>
      ) : null}

      {(livePricesError || livePrices?.warnings.length) ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          {livePricesError ? <p>{livePricesError}</p> : null}
          {livePrices?.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}

      <div className="mb-5 grid gap-3 text-sm text-slate-300 md:grid-cols-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Scanned</span><p className="mt-1 text-lg font-semibold text-white">{scan.scanned_count}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">LONG</span><p className="mt-1 text-lg font-semibold text-emerald-300">{scan.long_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">SHORT</span><p className="mt-1 text-lg font-semibold text-rose-300">{scan.short_candidates.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"><span className="text-slate-500">Candidates</span><p className="mt-1 text-lg font-semibold text-white">{candidateCount}</p></div>
      </div>

      <AdvancedDetailsPro>
        <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
          <div><span className="text-slate-500">Universe Source</span><p>{humanize(scan.futures_symbol_universe_source)}</p></div>
          <div><span className="text-slate-500">Data Source</span><p>{humanize(scan.data_source)}</p></div>
          <div><span className="text-slate-500">Symbol Count</span><p>{scan.symbol_count}</p></div>
          <div><span className="text-slate-500">Persisted Candidates</span><p>{scan.persisted_candidate_count}</p></div>
          <div><span className="text-slate-500">Fallback Symbols</span><p>{scan.fallback_symbol_count}</p></div>
          <div><span className="text-slate-500">Last Fetch</span><p>{scan.last_successful_fetch_at ? formatDateTime(scan.last_successful_fetch_at) : '-'}</p></div>
          <div><span className="text-slate-500">Last Successful Scan</span><p>{scan.latest_successful_scanner_at ? formatDateTime(scan.latest_successful_scanner_at) : '-'}</p></div>
          <div><span className="text-slate-500">Latest Error</span><p>{scan.latest_error ?? '-'}</p></div>
          <div><span className="text-slate-500">Scanner Error</span><p>{scan.latest_scanner_error ?? '-'}</p></div>
        </div>
      </AdvancedDetailsPro>

      {scan.warnings.length > 0 ? (
        <div className="mb-5 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          {scan.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-2">
        <CandidateGroup
          title="Top LONG Candidates"
          items={scan.long_candidates}
          empty="No LONG candidates"
          livePriceBySymbol={livePriceBySymbol}
          heartbeatNow={heartbeatNow}
          onViewSignal={onViewSignal}
          onSimulate={onSimulate}
        />
        <CandidateGroup
          title="Top SHORT Candidates"
          items={scan.short_candidates}
          empty="No SHORT candidates"
          livePriceBySymbol={livePriceBySymbol}
          heartbeatNow={heartbeatNow}
          onViewSignal={onViewSignal}
          onSimulate={onSimulate}
        />
      </div>

      {filters.includeAvoid ? (
      <div className="mt-5">
        <CandidateGroup
          title="WAIT / AVOID"
          items={scan.neutral_candidates.slice(0, 6)}
          empty="No neutral candidates"
          livePriceBySymbol={livePriceBySymbol}
          heartbeatNow={heartbeatNow}
          onViewSignal={onViewSignal}
          onSimulate={onSimulate}
        />
      </div>
      ) : null}
    </section>
  );
}
