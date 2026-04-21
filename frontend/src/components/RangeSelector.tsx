import { classNames } from '../lib/format';
import type { RangePreset } from '../lib/types';

interface RangeSelectorProps {
  value: RangePreset;
  onChange: (preset: RangePreset) => void;
}

const PRESETS: RangePreset[] = ['1D', '7D', '30D', 'ALL'];

export function RangeSelector({ value, onChange }: RangeSelectorProps) {
  return (
    <div className="inline-flex rounded-2xl border border-slate-800 bg-slate-950/60 p-1 shadow-inner shadow-slate-950/40">
      {PRESETS.map((preset) => (
        <button
          key={preset}
          type="button"
          onClick={() => onChange(preset)}
          className={classNames(
            'rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition',
            value === preset
              ? 'bg-sky-400/20 text-sky-100 ring-1 ring-sky-400/30'
              : 'text-slate-400 hover:bg-slate-900/80 hover:text-slate-100',
          )}
        >
          {preset}
        </button>
      ))}
    </div>
  );
}
