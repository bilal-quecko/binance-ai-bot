import { classNames } from '../lib/format';
import type { AutoRefreshIntervalSeconds } from '../lib/types';

interface AutoRefreshSelectorProps {
  value: AutoRefreshIntervalSeconds;
  onChange: (value: AutoRefreshIntervalSeconds) => void;
}

const OPTIONS: Array<{ label: string; value: AutoRefreshIntervalSeconds }> = [
  { label: 'Off', value: 0 },
  { label: '5s', value: 5 },
  { label: '10s', value: 10 },
  { label: '30s', value: 30 },
];

export function AutoRefreshSelector({ value, onChange }: AutoRefreshSelectorProps) {
  return (
    <div className="inline-flex rounded-2xl border border-slate-800 bg-slate-950/60 p-1 shadow-inner shadow-slate-950/40">
      {OPTIONS.map((option) => (
        <button
          key={option.label}
          type="button"
          onClick={() => onChange(option.value)}
          className={classNames(
            'rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition',
            value === option.value
              ? 'bg-emerald-400/20 text-emerald-100 ring-1 ring-emerald-400/30'
              : 'text-slate-400 hover:bg-slate-900/80 hover:text-slate-100',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
