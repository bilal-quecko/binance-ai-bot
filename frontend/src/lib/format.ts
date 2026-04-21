export function formatDecimal(value: string | number, options?: Intl.NumberFormatOptions): string {
  const numericValue = typeof value === 'string' ? Number(value) : value;
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 4,
    ...options,
  }).format(numericValue);
}

export function formatCurrency(value: string | number): string {
  const numericValue = typeof value === 'string' ? Number(value) : value;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(numericValue);
}

export function formatPercent(value: string | number, digits = 2): string {
  const numericValue = typeof value === 'string' ? Number(value) : value;
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    maximumFractionDigits: digits,
  }).format(numericValue);
}

export function formatDateTime(value: string | null): string {
  if (!value) {
    return '-';
  }
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function formatShortDateTime(value: string | null): string {
  if (!value) {
    return '-';
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

export function pnlTone(value: string | number): string {
  const numericValue = typeof value === 'string' ? Number(value) : value;
  if (numericValue > 0) {
    return 'text-emerald-400';
  }
  if (numericValue < 0) {
    return 'text-rose-400';
  }
  return 'text-slate-200';
}

export function badgeTone(value: string): string {
  if (value === 'BUY' || value === 'approve' || value === 'executed' || value === 'ok') {
    return 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30';
  }
  if (value === 'SELL' || value === 'reject' || value === 'rejected') {
    return 'bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30';
  }
  return 'bg-slate-700/60 text-slate-200 ring-1 ring-slate-600';
}

export function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
