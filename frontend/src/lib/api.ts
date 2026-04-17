import type {
  DailyPnlPoint,
  EquityResponse,
  EventItem,
  FillItem,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  PaginatedResponse,
  PositionItem,
  SymbolSummaryItem,
  TradeItem,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

function buildUrl(path: string, params?: URLSearchParams): string {
  const suffix = params && params.toString().length > 0 ? `?${params.toString()}` : '';
  return `${API_BASE_URL}${path}${suffix}`;
}

async function requestJson<T>(path: string, params?: URLSearchParams): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail || response.statusText}`);
  }

  return (await response.json()) as T;
}

function buildHistoryParams(filters: Partial<HistoryFilters>): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.symbol && filters.symbol.trim().length > 0) {
    params.set('symbol', filters.symbol.trim().toUpperCase());
  }
  if (filters.startDate) {
    params.set('start_date', filters.startDate);
  }
  if (filters.endDate) {
    params.set('end_date', filters.endDate);
  }
  if (filters.limit) {
    params.set('limit', String(filters.limit));
  }
  if (typeof filters.offset === 'number') {
    params.set('offset', String(filters.offset));
  }
  return params;
}

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/health');
}

export function getMetrics(): Promise<MetricsResponse> {
  return requestJson<MetricsResponse>('/metrics');
}

export function getEquity(): Promise<EquityResponse> {
  return requestJson<EquityResponse>('/equity');
}

export function getPositions(): Promise<PositionItem[]> {
  return requestJson<PositionItem[]>('/positions');
}

export function getDailyPnl(day?: string): Promise<string> {
  const params = new URLSearchParams();
  if (day) {
    params.set('day', day);
  }
  return requestJson<string>('/daily-pnl', params);
}

export function getTrades(filters: Partial<HistoryFilters>): Promise<PaginatedResponse<TradeItem>> {
  return requestJson<PaginatedResponse<TradeItem>>('/trades', buildHistoryParams(filters));
}

export function getFills(filters: Partial<HistoryFilters>): Promise<PaginatedResponse<FillItem>> {
  return requestJson<PaginatedResponse<FillItem>>('/fills', buildHistoryParams(filters));
}

export function getEvents(filters: Partial<HistoryFilters>): Promise<PaginatedResponse<EventItem>> {
  return requestJson<PaginatedResponse<EventItem>>('/events', buildHistoryParams(filters));
}

export function getSymbolSummaries(symbols?: string[]): Promise<SymbolSummaryItem[]> {
  const params = new URLSearchParams();
  symbols
    ?.map((symbol) => symbol.trim().toUpperCase())
    .filter((symbol) => symbol.length > 0)
    .forEach((symbol) => params.append('symbols', symbol));
  return requestJson<SymbolSummaryItem[]>('/summary/symbols', params);
}

export async function getRecentDailyPnl(days: number): Promise<DailyPnlPoint[]> {
  const now = new Date();
  const requests: Promise<string>[] = [];
  const labels: string[] = [];

  for (let index = days - 1; index >= 0; index -= 1) {
    const current = new Date(now);
    current.setUTCDate(now.getUTCDate() - index);
    const day = current.toISOString().slice(0, 10);
    labels.push(day);
    requests.push(getDailyPnl(day));
  }

  const values = await Promise.all(requests);
  return values.map((value, index) => ({
    day: labels[index],
    value: Number(value),
  }));
}

