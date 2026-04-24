function toNumber(value: string | number): number {
  return typeof value === 'string' ? Number(value) : value;
}

function precisionByMagnitude(value: number): Intl.NumberFormatOptions {
  const absValue = Math.abs(value);
  if (absValue >= 10000) {
    return { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  }
  if (absValue >= 100) {
    return { minimumFractionDigits: 2, maximumFractionDigits: 3 };
  }
  if (absValue >= 1) {
    return { minimumFractionDigits: 2, maximumFractionDigits: 5 };
  }
  if (absValue >= 0.01) {
    return { minimumFractionDigits: 4, maximumFractionDigits: 6 };
  }
  if (absValue >= 0.001) {
    return { minimumFractionDigits: 5, maximumFractionDigits: 6 };
  }
  return { minimumFractionDigits: 6, maximumFractionDigits: 8 };
}

export function formatDecimal(value: string | number, options?: Intl.NumberFormatOptions): string {
  const numericValue = toNumber(value);
  return new Intl.NumberFormat('en-US', {
    ...precisionByMagnitude(numericValue),
    ...options,
  }).format(numericValue);
}

export function formatCurrency(value: string | number): string {
  return formatDecimal(value);
}

export function formatPercent(value: string | number, digits = 2): string {
  const numericValue = toNumber(value);
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
  const numericValue = toNumber(value);
  if (numericValue > 0) {
    return 'text-emerald-400';
  }
  if (numericValue < 0) {
    return 'text-rose-400';
  }
  return 'text-slate-200';
}

export function badgeTone(value: string): string {
  if (value === 'BUY' || value === 'approve' || value === 'executed' || value === 'ok' || value === 'enter') {
    return 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30';
  }
  if (value === 'SELL' || value === 'reject' || value === 'rejected' || value === 'exit') {
    return 'bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30';
  }
  if (value === 'wait' || value === 'hold' || value === 'abstain') {
    return 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30';
  }
  return 'bg-slate-700/60 text-slate-200 ring-1 ring-slate-600';
}

export function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function humanizeReasonCode(reasonCode: string): string {
  switch (reasonCode) {
    case 'MISSING_ATR_CONTEXT':
      return 'Need more candles before signals activate.';
    case 'NO_POSITION':
    case 'NO_POSITION_TO_EXIT':
      return 'No open position, so no exit setup exists.';
    case 'REGIME_NOT_TREND':
      return 'Trend confirmation is not strong enough yet.';
    case 'MICROSTRUCTURE_UNHEALTHY':
      return 'Spread or order-book conditions are still unhealthy.';
    case 'VOL_TOO_LOW':
      return 'Volatility is too weak to trust this setup yet.';
    case 'EDGE_BELOW_COSTS':
    case 'EXPECTED_EDGE_TOO_SMALL':
      return 'Expected edge is too small after fees and slippage.';
    case 'APPROVED':
      return 'Risk checks currently allow the trade.';
    case 'EXIT_APPROVED':
      return 'Risk checks currently allow the exit.';
    case 'RESIZED_FOR_RISK':
      return 'Position size was reduced to stay within risk limits.';
    case 'RESIZED_TO_POSITION':
      return 'Exit size was reduced to match the open position.';
    case 'OPEN_POSITION_LIMIT':
      return 'The bot already holds the maximum allowed open positions.';
    case 'DAILY_LOSS_LIMIT':
      return 'Daily loss protection is active, so new entries are blocked.';
    case 'STOP_DISTANCE_TOO_TIGHT':
    case 'PROTECTIVE_STOP_TOO_TIGHT':
      return 'The protective stop is too tight relative to current price movement.';
    case 'EMA_BULLISH':
      return 'Fast EMA remains above slow EMA.';
    case 'EMA_BEARISH_EXIT':
      return 'Fast EMA has crossed below slow EMA.';
    case 'TAKE_PROFIT_HIT':
      return 'The take-profit condition is active.';
    case 'POSITION_OPEN':
      return 'An open position exists, so the bot is watching exit conditions.';
    case 'RISK_FILTERS_PASS':
      return 'Volatility and microstructure filters are currently acceptable.';
    default:
      return reasonCode
        .split('_')
        .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
        .join(' ');
  }
}

export function formatReasonCodes(reasonCodes: string[] | readonly string[]): string {
  if (reasonCodes.length === 0) {
    return 'No explanation yet.';
  }
  return reasonCodes.map(humanizeReasonCode).join(' ');
}
