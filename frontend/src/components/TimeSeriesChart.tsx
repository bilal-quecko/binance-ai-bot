import { useMemo, useState } from 'react';

import { classNames, formatCurrency, formatDateTime, formatDecimal, formatPercent, formatShortDateTime } from '../lib/format';

type ChartValueFormat = 'currency' | 'decimal' | 'percent';

export interface TimeSeriesSeries {
  key: string;
  label: string;
  color: string;
  values: number[];
  format?: ChartValueFormat;
}

interface TimeSeriesChartProps {
  title: string;
  subtitle?: string;
  labels: string[];
  series: TimeSeriesSeries[];
  emptyMessage?: string;
}

function formatChartValue(value: number, format: ChartValueFormat): string {
  if (format === 'currency') {
    return formatCurrency(value);
  }
  if (format === 'percent') {
    return formatPercent(value / 100, 2);
  }
  return formatDecimal(value);
}

export function TimeSeriesChart({
  title,
  subtitle,
  labels,
  series,
  emptyMessage,
}: TimeSeriesChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const activeIndex = hoverIndex ?? labels.length - 1;
  const hasData = labels.length > 0 && series.some((item) => item.values.length > 0);

  const chartState = useMemo(() => {
    const flattenedValues = series.flatMap((item) => item.values);
    if (flattenedValues.length === 0 || labels.length === 0) {
      return null;
    }

    const width = 720;
    const height = 240;
    const paddingX = 24;
    const paddingY = 20;
    const minValue = Math.min(...flattenedValues);
    const maxValue = Math.max(...flattenedValues);
    const range = maxValue - minValue || 1;
    const stepX = labels.length > 1 ? (width - paddingX * 2) / (labels.length - 1) : 0;
    const zeroLine = maxValue >= 0 && minValue <= 0 ? height - paddingY - ((0 - minValue) / range) * (height - paddingY * 2) : null;

    return {
      width,
      height,
      paddingX,
      paddingY,
      minValue,
      maxValue,
      range,
      stepX,
      zeroLine,
    };
  }, [labels.length, series]);

  if (!hasData || chartState === null) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/30 p-6 text-sm text-slate-400">
        {emptyMessage ?? `No ${title.toLowerCase()} data available for the selected range.`}
      </div>
    );
  }

  const currentLabel = labels[activeIndex] ?? null;
  const pointerX = chartState.paddingX + chartState.stepX * activeIndex;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {series.map((item) => (
            <span
              key={item.key}
              className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-950/60 px-3 py-1 text-xs text-slate-300"
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Hover timestamp</p>
            <p className="mt-1 text-sm font-medium text-slate-100">{formatDateTime(currentLabel)}</p>
          </div>
          <div className="grid gap-3 text-right sm:grid-cols-2">
            {series.map((item) => {
              const value = item.values[activeIndex] ?? 0;
              return (
                <div key={item.key}>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
                  <p className="mt-1 text-sm font-semibold" style={{ color: item.color }}>
                    {formatChartValue(value, item.format ?? 'decimal')}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="relative mt-4">
          <svg
            viewBox={`0 0 ${chartState.width} ${chartState.height}`}
            className="h-64 w-full overflow-visible rounded-2xl bg-slate-950/40"
            onMouseLeave={() => setHoverIndex(null)}
            onMouseMove={(event) => {
              const bounds = event.currentTarget.getBoundingClientRect();
              const relativeX = ((event.clientX - bounds.left) / bounds.width) * chartState.width;
              const rawIndex = Math.round((relativeX - chartState.paddingX) / Math.max(chartState.stepX, 1));
              const nextIndex = Math.min(Math.max(rawIndex, 0), labels.length - 1);
              setHoverIndex(nextIndex);
            }}
          >
            <defs>
              {series.map((item) => (
                <linearGradient key={item.key} id={`gradient-${item.key}`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={item.color} stopOpacity="0.28" />
                  <stop offset="100%" stopColor={item.color} stopOpacity="0.04" />
                </linearGradient>
              ))}
            </defs>

            <line
              x1={chartState.paddingX}
              x2={chartState.width - chartState.paddingX}
              y1={chartState.paddingY}
              y2={chartState.paddingY}
              className="stroke-slate-800"
            />
            <line
              x1={chartState.paddingX}
              x2={chartState.width - chartState.paddingX}
              y1={chartState.height - chartState.paddingY}
              y2={chartState.height - chartState.paddingY}
              className="stroke-slate-800"
            />
            {chartState.zeroLine !== null ? (
              <line
                x1={chartState.paddingX}
                x2={chartState.width - chartState.paddingX}
                y1={chartState.zeroLine}
                y2={chartState.zeroLine}
                className="stroke-slate-700/80"
                strokeDasharray="4 4"
              />
            ) : null}

            {series.map((item) => {
              const points = item.values.map((value, index) => {
                const x = chartState.paddingX + index * chartState.stepX;
                const y =
                  chartState.height -
                  chartState.paddingY -
                  ((value - chartState.minValue) / chartState.range) * (chartState.height - chartState.paddingY * 2);
                return { x, y };
              });

              const polylinePoints = points.map((point) => `${point.x},${point.y}`).join(' ');
              const areaPath = [
                `M ${points[0]?.x ?? chartState.paddingX} ${chartState.height - chartState.paddingY}`,
                ...points.map((point) => `L ${point.x} ${point.y}`),
                `L ${points[points.length - 1]?.x ?? chartState.paddingX} ${chartState.height - chartState.paddingY}`,
                'Z',
              ].join(' ');

              return (
                <g key={item.key}>
                  <path d={areaPath} fill={`url(#gradient-${item.key})`} />
                  <polyline
                    fill="none"
                    stroke={item.color}
                    strokeWidth="3"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    points={polylinePoints}
                  />
                  {points.map((point, index) => (
                    <circle
                      key={`${item.key}-${labels[index]}`}
                      cx={point.x}
                      cy={point.y}
                      r={index === activeIndex ? 5 : 2.5}
                      fill={item.color}
                      className={classNames(index === activeIndex ? 'opacity-100' : 'opacity-75')}
                    />
                  ))}
                </g>
              );
            })}

            <line
              x1={pointerX}
              x2={pointerX}
              y1={chartState.paddingY}
              y2={chartState.height - chartState.paddingY}
              className="stroke-slate-600"
              strokeDasharray="4 4"
            />
          </svg>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <span>Start {formatShortDateTime(labels[0] ?? null)}</span>
          <span>Low {formatDecimal(chartState.minValue)}</span>
          <span>High {formatDecimal(chartState.maxValue)}</span>
          <span>End {formatShortDateTime(labels[labels.length - 1] ?? null)}</span>
        </div>
      </div>
    </div>
  );
}
