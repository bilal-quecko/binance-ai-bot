import type {
  AISignalHistoryResponse,
  AISignalSummary,
  BotStatusResponse,
  DrawdownResponse,
  EquityHistoryPoint,
  EquityResponse,
  EventItem,
  FillItem,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  PaginatedResponse,
  PnlHistoryResponse,
  PositionItem,
  WorkstationResponse,
  RangeFilters,
  SpotSymbolItem,
  SymbolSummaryItem,
  TradeItem,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

function buildUrl(path: string, params?: URLSearchParams): string {
  const suffix = params && params.toString().length > 0 ? `?${params.toString()}` : '';
  return `${API_BASE_URL}${path}${suffix}`;
}

async function requestJson<T>(path: string, params?: URLSearchParams, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
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

function buildRangeParams(filters?: RangeFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters?.startDate) {
    params.set('start_date', filters.startDate);
  }
  if (filters?.endDate) {
    params.set('end_date', filters.endDate);
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

export function getEquityHistory(filters?: RangeFilters): Promise<EquityHistoryPoint[]> {
  return requestJson<EquityHistoryPoint[]>('/equity/history', buildRangeParams(filters));
}

export function getPnlHistory(filters?: RangeFilters): Promise<PnlHistoryResponse> {
  return requestJson<PnlHistoryResponse>('/pnl/history', buildRangeParams(filters));
}

export function getDrawdown(filters?: RangeFilters): Promise<DrawdownResponse> {
  return requestJson<DrawdownResponse>('/drawdown', buildRangeParams(filters));
}

export function getPositions(): Promise<PositionItem[]> {
  return requestJson<PositionItem[]>('/positions');
}

export function getBotStatus(): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/status');
}

export function getWorkstation(symbol: string): Promise<WorkstationResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<WorkstationResponse>('/bot/workstation', params);
}

export function getAISignal(symbol: string): Promise<AISignalSummary | null> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<AISignalSummary | null>('/bot/ai-signal', params);
}

export function getAISignalHistory(
  symbol: string,
  filters?: Omit<Partial<HistoryFilters>, 'symbol'>,
): Promise<AISignalHistoryResponse> {
  const params = buildHistoryParams({
    symbol,
    startDate: filters?.startDate,
    endDate: filters?.endDate,
    limit: filters?.limit ?? 20,
    offset: filters?.offset ?? 0,
  });
  return requestJson<AISignalHistoryResponse>('/bot/ai-signal/history', params);
}

export function getSymbols(query = '', limit = 20): Promise<SpotSymbolItem[]> {
  const params = new URLSearchParams();
  if (query.trim().length > 0) {
    params.set('query', query.trim());
  }
  params.set('limit', String(limit));
  return requestJson<SpotSymbolItem[]>('/symbols', params);
}

export function startBot(symbol: string): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/start', undefined, {
    method: 'POST',
    body: JSON.stringify({ symbol }),
  });
}

export function stopBot(): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/stop', undefined, { method: 'POST' });
}

export function pauseBot(): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/pause', undefined, { method: 'POST' });
}

export function resumeBot(): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/resume', undefined, { method: 'POST' });
}

export function resetBotSession(): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/reset', undefined, { method: 'POST' });
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

export async function getAllTrades(limit = 500): Promise<TradeItem[]> {
  const firstPage = await getTrades({ limit, offset: 0 });
  const items = [...firstPage.items];
  let nextOffset = firstPage.items.length;

  while (items.length < firstPage.total) {
    const page = await getTrades({ limit, offset: nextOffset });
    items.push(...page.items);
    if (page.items.length === 0) {
      break;
    }
    nextOffset += page.items.length;
  }

  return items;
}

export async function getRecentEvents(limit = 12): Promise<EventItem[]> {
  const firstPage = await getEvents({ limit: 1, offset: 0 });
  const recentOffset = Math.max(firstPage.total - limit, 0);
  const recentPage = await getEvents({ limit, offset: recentOffset });
  return recentPage.items;
}

export function getSymbolSummaries(symbols?: string[]): Promise<SymbolSummaryItem[]> {
  const params = new URLSearchParams();
  symbols
    ?.map((symbol) => symbol.trim().toUpperCase())
    .filter((symbol) => symbol.length > 0)
    .forEach((symbol) => params.append('symbols', symbol));
  return requestJson<SymbolSummaryItem[]>('/summary/symbols', params);
}
