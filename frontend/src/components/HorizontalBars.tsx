import { classNames, formatCurrency } from '../lib/format';

interface HorizontalBarsProps {
  items: Array<{ label: string; value: number }>;
}

export function HorizontalBars({ items }: HorizontalBarsProps) {
  if (items.length === 0) {
    return <div className="rounded-xl border border-dashed border-slate-700 p-6 text-sm text-slate-400">No symbol data available.</div>;
  }

  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const width = `${(Math.abs(item.value) / max) * 100}%`;
        return (
          <div key={item.label} className="space-y-1">
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="font-medium text-slate-200">{item.label}</span>
              <span className={classNames(item.value > 0 && 'text-emerald-400', item.value < 0 && 'text-rose-400', item.value === 0 && 'text-slate-200')}>
                {formatCurrency(item.value)}
              </span>
            </div>
            <div className="h-2 rounded-full bg-slate-800">
              <div
                className={classNames(
                  'h-2 rounded-full',
                  item.value > 0 && 'bg-emerald-400',
                  item.value < 0 && 'bg-rose-400',
                  item.value === 0 && 'bg-slate-500',
                )}
                style={{ width }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

