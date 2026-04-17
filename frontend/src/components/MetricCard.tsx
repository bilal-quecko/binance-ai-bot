import { classNames } from '../lib/format';

interface MetricCardProps {
  label: string;
  value: string;
  helper?: string;
  tone?: 'default' | 'positive' | 'negative';
}

export function MetricCard({ label, value, helper, tone = 'default' }: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p
        className={classNames(
          'mt-3 text-2xl font-semibold',
          tone === 'positive' && 'text-emerald-400',
          tone === 'negative' && 'text-rose-400',
          tone === 'default' && 'text-white',
        )}
      >
        {value}
      </p>
      {helper ? <p className="mt-2 text-sm text-slate-400">{helper}</p> : null}
    </div>
  );
}

