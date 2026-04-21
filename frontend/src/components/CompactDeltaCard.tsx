import { classNames } from '../lib/format';

interface CompactDeltaCardProps {
  label: string;
  value: string;
  helper?: string;
  delta?: string;
  tone?: 'default' | 'positive' | 'negative';
}

export function CompactDeltaCard({ label, value, helper, delta, tone = 'default' }: CompactDeltaCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
        {delta ? (
          <span
            className={classNames(
              'rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-[0.14em]',
              tone === 'positive' && 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30',
              tone === 'negative' && 'bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30',
              tone === 'default' && 'bg-slate-800 text-slate-200 ring-1 ring-slate-700',
            )}
          >
            {delta}
          </span>
        ) : null}
      </div>
      <p
        className={classNames(
          'mt-3 text-lg font-semibold',
          tone === 'positive' && 'text-emerald-400',
          tone === 'negative' && 'text-rose-400',
          tone === 'default' && 'text-white',
        )}
      >
        {value}
      </p>
      {helper ? <p className="mt-1 text-xs text-slate-400">{helper}</p> : null}
    </div>
  );
}
