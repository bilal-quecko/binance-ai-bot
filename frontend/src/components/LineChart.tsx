import { formatDecimal } from '../lib/format';

interface LineChartProps {
  values: number[];
  labels: string[];
  stroke: string;
  fill: string;
  title: string;
}

export function LineChart({ values, labels, stroke, fill, title }: LineChartProps) {
  if (values.length === 0) {
    return <div className="rounded-xl border border-dashed border-slate-700 p-6 text-sm text-slate-400">No data available for {title}.</div>;
  }

  const width = 520;
  const height = 180;
  const padding = 16;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;

  const points = values.map((value, index) => {
    const x = padding + index * stepX;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  });

  const areaPath = [
    `M ${padding} ${height - padding}`,
    ...points.map((point, index) => `${index === 0 ? 'L' : 'L'} ${point.replace(',', ' ')}`),
    `L ${padding + stepX * (values.length - 1)} ${height - padding}`,
    'Z',
  ].join(' ');

  return (
    <div className="space-y-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full overflow-visible rounded-xl border border-slate-800 bg-slate-950/60 p-2">
        <path d={areaPath} fill={fill} opacity="0.35" />
        <polyline fill="none" stroke={stroke} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" points={points.join(' ')} />
        {values.map((value, index) => {
          const [x, y] = points[index].split(',').map(Number);
          return <circle key={`${labels[index]}-${value}`} cx={x} cy={y} r="3" fill={stroke} />;
        })}
      </svg>
      <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 sm:grid-cols-4 lg:grid-cols-7">
        {labels.map((label, index) => (
          <div key={label} className="rounded-lg border border-slate-800 bg-slate-950/40 px-2 py-1.5">
            <p>{label.slice(5)}</p>
            <p className="mt-1 text-sm font-semibold text-slate-100">{formatDecimal(values[index])}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

