import { classNames, formatCurrency, formatDateTime } from '../lib/format';
import { StatePanel } from './StatePanel';
import type { CandleHistoryResponse, TechnicalAnalysisResponse } from '../lib/types';

interface SymbolCandlestickChartProps {
  symbol: string;
  timeframe: '1m' | '5m' | '15m' | '1h';
  chart: CandleHistoryResponse | null;
  chartLoading: boolean;
  chartError: string | null;
  technicalAnalysis: TechnicalAnalysisResponse | null;
}

function toNumber(value: string): number {
  return Number(value);
}

function nearestLevel(levels: string[], currentPrice: number, direction: 'support' | 'resistance'): string | null {
  const numericLevels = levels.map(Number).filter((value) => Number.isFinite(value));
  if (direction === 'support') {
    return numericLevels
      .filter((value) => value <= currentPrice)
      .sort((left, right) => right - left)[0]?.toString() ?? null;
  }
  return numericLevels
    .filter((value) => value >= currentPrice)
    .sort((left, right) => left - right)[0]?.toString() ?? null;
}

export function SymbolCandlestickChart({
  symbol,
  timeframe,
  chart,
  chartLoading,
  chartError,
  technicalAnalysis,
}: SymbolCandlestickChartProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to load its recent candles and technical landmarks." tone="empty" />;
  }

  if (chartLoading && !chart) {
    return <StatePanel title="Loading chart" message={`Loading recent ${timeframe} candles for ${symbol}.`} tone="loading" />;
  }

  if (chartError) {
    return <StatePanel title="Chart unavailable" message={chartError} tone="error" />;
  }

  if (!chart || chart.candles.length === 0) {
    return (
      <StatePanel
        title="Chart waiting for data"
        message={chart?.status_message ?? `Recent ${timeframe} candles are not available for ${symbol} yet.`}
        tone="empty"
      />
    );
  }

  const width = 820;
  const height = 340;
  const volumeHeight = 72;
  const chartHeight = height - volumeHeight - 18;
  const paddingLeft = 18;
  const paddingRight = 84;
  const paddingTop = 14;
  const drawableWidth = width - paddingLeft - paddingRight;
  const drawableHeight = chartHeight - paddingTop - 18;
  const candleWidth = Math.max(4, Math.floor(drawableWidth / chart.candles.length) - 2);
  const candleGap = drawableWidth / chart.candles.length;

  const highs = chart.candles.map((item) => toNumber(item.high));
  const lows = chart.candles.map((item) => toNumber(item.low));
  const maxVolume = Math.max(...chart.candles.map((item) => toNumber(item.volume)), 1);
  const upperBound = Math.max(...highs);
  const lowerBound = Math.min(...lows);
  const priceSpan = Math.max(upperBound - lowerBound, 0.0000001);
  const currentPrice = chart.current_price ? Number(chart.current_price) : Number(chart.candles[chart.candles.length - 1].close);
  const nearestSupport = nearestLevel(technicalAnalysis?.support_levels ?? [], currentPrice, 'support');
  const nearestResistance = nearestLevel(technicalAnalysis?.resistance_levels ?? [], currentPrice, 'resistance');

  const priceY = (price: number): number => paddingTop + ((upperBound - price) / priceSpan) * drawableHeight;
  const volumeY = (volume: number): number => chartHeight + volumeHeight - (volume / maxVolume) * (volumeHeight - 8);

  const trendTone =
    technicalAnalysis?.trend_direction === 'bullish'
      ? 'text-emerald-300'
      : technicalAnalysis?.trend_direction === 'bearish'
        ? 'text-rose-300'
        : 'text-amber-300';

  const priceLines = [
    {
      label: 'Current',
      value: currentPrice,
      tone: 'stroke-sky-400',
      dash: '6 4',
    },
    nearestSupport
      ? {
          label: 'Support',
          value: Number(nearestSupport),
          tone: 'stroke-emerald-500/70',
          dash: '4 4',
        }
      : null,
    nearestResistance
      ? {
          label: 'Resistance',
          value: Number(nearestResistance),
          tone: 'stroke-rose-500/70',
          dash: '4 4',
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: number; tone: string; dash: string }>;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Selected symbol chart</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-white">{symbol}</h3>
            <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">
              {timeframe}
            </span>
            {chart.derived_from_lower_timeframe ? (
              <span className="rounded-full border border-slate-800 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-400">
                Derived from {chart.source_timeframe} candles
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-sm text-slate-400">
            {chart.status_message ?? `Recent closed candles for ${symbol}.`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Current price</p>
          <p className="mt-1 text-xl font-semibold text-white">{formatCurrency(currentPrice)}</p>
          <p className={classNames('mt-1 text-xs font-medium capitalize', trendTone)}>
            {technicalAnalysis?.trend_direction ?? 'waiting'} trend
            {technicalAnalysis?.trend_strength ? ` · ${technicalAnalysis.trend_strength}` : ''}
          </p>
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/80">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[360px] w-full">
          <rect x="0" y="0" width={width} height={height} className="fill-slate-950" />
          {[0.25, 0.5, 0.75].map((marker) => (
            <line
              key={marker}
              x1={paddingLeft}
              x2={width - paddingRight}
              y1={paddingTop + drawableHeight * marker}
              y2={paddingTop + drawableHeight * marker}
              className="stroke-slate-800"
              strokeWidth="1"
            />
          ))}

          {priceLines.map((line) => (
            <g key={`${line.label}-${line.value}`}>
              <line
                x1={paddingLeft}
                x2={width - paddingRight}
                y1={priceY(line.value)}
                y2={priceY(line.value)}
                className={line.tone}
                strokeWidth="1.2"
                strokeDasharray={line.dash}
              />
              <text
                x={width - paddingRight + 8}
                y={priceY(line.value) + 4}
                className="fill-slate-300 text-[11px]"
              >
                {line.label} {formatCurrency(line.value)}
              </text>
            </g>
          ))}

          {chart.candles.map((item, index) => {
            const open = toNumber(item.open);
            const high = toNumber(item.high);
            const low = toNumber(item.low);
            const close = toNumber(item.close);
            const volume = toNumber(item.volume);
            const rising = close >= open;
            const xCenter = paddingLeft + index * candleGap + candleGap / 2;
            const bodyTop = priceY(Math.max(open, close));
            const bodyBottom = priceY(Math.min(open, close));
            const bodyHeight = Math.max(2, bodyBottom - bodyTop);
            const bodyY = Math.min(bodyTop, bodyBottom);

            return (
              <g key={`${item.open_time}-${index}`}>
                <line
                  x1={xCenter}
                  x2={xCenter}
                  y1={priceY(high)}
                  y2={priceY(low)}
                  className={rising ? 'stroke-emerald-400' : 'stroke-rose-400'}
                  strokeWidth="1.2"
                />
                <rect
                  x={xCenter - candleWidth / 2}
                  y={bodyY}
                  width={candleWidth}
                  height={bodyHeight}
                  className={rising ? 'fill-emerald-400/80' : 'fill-rose-400/80'}
                  rx="1"
                />
                <rect
                  x={xCenter - candleWidth / 2}
                  y={volumeY(volume)}
                  width={candleWidth}
                  height={chartHeight + volumeHeight - volumeY(volume)}
                  className={rising ? 'fill-emerald-500/25' : 'fill-rose-500/25'}
                  rx="1"
                />
              </g>
            );
          })}

          <line
            x1={paddingLeft}
            x2={width - paddingRight}
            y1={chartHeight}
            y2={chartHeight}
            className="stroke-slate-800"
            strokeWidth="1"
          />

          <text x={paddingLeft} y={height - 8} className="fill-slate-500 text-[11px]">
            {formatDateTime(chart.candles[0].open_time)}
          </text>
          <text x={width - paddingRight - 96} y={height - 8} className="fill-slate-500 text-[11px]">
            {formatDateTime(chart.candles[chart.candles.length - 1].close_time)}
          </text>
        </svg>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <PointCard label="Nearest support" value={nearestSupport ? formatCurrency(nearestSupport) : 'Waiting'} helper="Closest support beneath current price" tone="text-emerald-300" />
        <PointCard label="Nearest resistance" value={nearestResistance ? formatCurrency(nearestResistance) : 'Waiting'} helper="Closest resistance above current price" tone="text-rose-300" />
        <PointCard
          label="Breakout area"
          value={
            technicalAnalysis?.breakout_bias === 'upside' && nearestResistance
              ? `Above ${formatCurrency(nearestResistance)}`
              : technicalAnalysis?.breakout_bias === 'downside' && nearestSupport
                ? `Below ${formatCurrency(nearestSupport)}`
                : technicalAnalysis?.breakout_readiness ?? 'Waiting'
          }
          helper={technicalAnalysis?.breakout_readiness ? `${technicalAnalysis.breakout_readiness} readiness` : 'Needs technical structure'}
          tone="text-sky-300"
        />
        <PointCard
          label="Reversal risk area"
          value={technicalAnalysis?.reversal_risk ?? 'Waiting'}
          helper="Current technical reversal pressure"
          tone="text-amber-300"
        />
        <PointCard
          label="Current price"
          value={formatCurrency(currentPrice)}
          helper="Latest closed-candle close"
          tone="text-white"
        />
      </div>
    </div>
  );
}

interface PointCardProps {
  label: string;
  value: string;
  helper: string;
  tone: string;
}

function PointCard({ label, value, helper, tone }: PointCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={classNames('mt-2 text-sm font-semibold', tone)}>{value}</p>
      <p className="mt-1 text-xs text-slate-400">{helper}</p>
    </div>
  );
}
