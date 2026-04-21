import type { RangePreset } from '../lib/types';
import { classNames } from '../lib/format';

interface RangeTabsProps {
  value: RangePreset;
  onChange: (value: RangePreset) => void;
}

const PRESETS: RangePreset[] = ['1D', '7D', '30D', 'ALL'];

export function RangeTabs({ value, onChange }: RangeTabsProps) {
  return (
    <div className="inline-flex rounded-xl border border-slate-800 bg-slate-950/60 p-1">
      {PRESETS.map((preset) => (
        <button
          key={preset}
          type="button"
          onClick={() => onChange(preset)}
          className={classNames(
            'rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] transition',
            preset === value ? 'bg-sky-400/20 text-sky-200' : 'text-slate-400 hover:text-slate-200',
          )}
        >
          {preset}
        </button>
      ))}
    </div>
  );
}
