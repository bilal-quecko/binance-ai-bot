import type { RangeFilters, RangePreset } from './types';

function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export function resolveRangeFilters(preset: RangePreset, now: Date = new Date()): RangeFilters | undefined {
  if (preset === 'ALL') {
    return undefined;
  }

  const end = new Date(now);
  const start = new Date(now);

  if (preset === '1D') {
    return {
      startDate: toIsoDate(start),
      endDate: toIsoDate(end),
    };
  }

  const days = preset === '7D' ? 6 : 29;
  start.setUTCDate(start.getUTCDate() - days);
  return {
    startDate: toIsoDate(start),
    endDate: toIsoDate(end),
  };
}
