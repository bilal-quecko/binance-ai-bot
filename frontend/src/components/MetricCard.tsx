import { classNames } from '../lib/format';

interface MetricCardProps {
  label: string;
  value: string;
  helper?: string;
  tone?: 'default' | 'positive' | 'negative';
}

export function MetricCard({ label, value, helper, tone = 'default' }: MetricCardProps) {
  return (
    <div className="min-w-0 rounded-lg border border-borderSoft bg-cardBg/80 p-4">
      <p className="text-xs font-medium text-textMuted">{label}</p>
      <p
        className={classNames(
          'mt-3 truncate text-2xl font-semibold',
          tone === 'positive' && 'text-longGreen',
          tone === 'negative' && 'text-shortRed',
          tone === 'default' && 'text-textPrimary',
        )}
      >
        {value}
      </p>
      {helper ? <p className="mt-2 text-sm leading-5 text-textSecondary">{helper}</p> : null}
    </div>
  );
}

