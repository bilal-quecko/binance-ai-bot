import type {
  AdaptiveRecommendationResponse,
  AIOutcomeEvaluationResponse,
  AISignalHistoryResponse,
  AISignalSummary,
  BotStatusResponse,
  BackfillStatusResponse,
  CandleHistoryResponse,
  DrawdownResponse,
  EquityHistoryPoint,
  EquityResponse,
  EventItem,
  EdgeReportResponse,
  FillItem,
  FuturesLivePriceResponse,
  FuturesLiveSubscriptionResponse,
  FuturesOpportunityScanResponse,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  MarketSentimentResponse,
  PaginatedResponse,
  PnlHistoryResponse,
  PostSignalHistoryResponse,
  PostSignalPerformanceSummaryResponse,
  PostSignalSnapshotResponse,
  PerformanceAnalyticsResponse,
  PaperTradeReviewResponse,
  ModuleAttributionResponse,
  ProfileCalibrationApplyResponse,
  ProfileCalibrationComparisonResponse,
  ProfileCalibrationResponse,
  PatternAnalysisResponse,
  FusionSignalResponse,
  OpportunityResponse,
  PositionItem,
  TechnicalAnalysisResponse,
  TradeEligibilityResponse,
  TradingAssistantResponse,
  TradingProfile,
  TradeQualityResponse,
  ManualTradeResponse,
  WorkstationResponse,
  RangeFilters,
  RegimeAnalysisResponse,
  ScannerValidationEvaluateResponse,
  ScannerValidationReportResponse,
  SpotSymbolItem,
  SignalValidationResponse,
  SimilarSetupResponse,
  SymbolSummaryItem,
  SymbolSentimentResponse,
  TradeItem,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
const ADVANCED_ANALYTICS_TIMEOUT_MS = 60_000;
const FUTURES_SCANNER_TIMEOUT_MS = 60_000;

export type ApiErrorCategory =
  | 'backend_unavailable'
  | 'scanner_timeout'
  | 'binance_unavailable'
  | 'network_proxy_error'
  | 'request_canceled'
  | 'http_error'
  | 'unknown';

export class ApiRequestError extends Error {
  category: ApiErrorCategory;
  status?: number;

  constructor(message: string, category: ApiErrorCategory, status?: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.category = category;
    this.status = status;
  }
}

interface RequestJsonOptions extends RequestInit {
  timeoutMs?: number;
}

export interface ApiRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

function buildUrl(path: string, params?: URLSearchParams): string {
  const suffix = params && params.toString().length > 0 ? `?${params.toString()}` : '';
  return `${API_BASE_URL}${path}${suffix}`;
}

async function requestJson<T>(path: string, params?: URLSearchParams, init?: RequestJsonOptions): Promise<T> {
  const timeoutMs = init?.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  init?.signal?.addEventListener('abort', () => controller.abort(), { once: true });
  const { timeoutMs: _timeoutMs, signal: _signal, ...fetchInit } = init ?? {};

  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), {
      ...fetchInit,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(fetchInit?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(fetchInit?.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (!timedOut && init?.signal?.aborted) {
        throw new ApiRequestError('Request canceled because a newer symbol was selected.', 'request_canceled');
      }
      throw new ApiRequestError('Request timed out before the backend returned a response.', 'scanner_timeout');
    }
    if (error instanceof TypeError) {
      throw new ApiRequestError('Network or proxy error while contacting the backend.', 'network_proxy_error');
    }
    throw new ApiRequestError(error instanceof Error ? error.message : 'Unknown network error.', 'unknown');
  } finally {
    window.clearTimeout(timeoutId);
  }
  void _timeoutMs;
  void _signal;

  if (!response.ok) {
    const detail = await response.text();
    if (response.status === 502 || response.status === 503) {
      throw new ApiRequestError('Backend unavailable. The API server may be offline or restarting.', 'backend_unavailable', response.status);
    }
    if (response.status === 504 || response.status === 408) {
      throw new ApiRequestError('Scanner timed out before the backend completed.', 'scanner_timeout', response.status);
    }
    if (response.status === 429 || response.status >= 500) {
      throw new ApiRequestError(`Binance API or backend dependency is temporarily unavailable (${response.status}).`, 'binance_unavailable', response.status);
    }
    throw new ApiRequestError(`Request failed (${response.status}): ${detail || response.statusText}`, 'http_error', response.status);
  }

  return (await response.json()) as T;
}

function requestOptions(options?: ApiRequestOptions): RequestJsonOptions | undefined {
  if (!options) {
    return undefined;
  }
  return {
    signal: options.signal,
    timeoutMs: options.timeoutMs,
  };
}

function advancedRequestOptions(options?: ApiRequestOptions): RequestJsonOptions {
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? ADVANCED_ANALYTICS_TIMEOUT_MS,
  };
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

export function getHealth(options?: ApiRequestOptions): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/health', undefined, requestOptions(options));
}

export function getMetrics(): Promise<MetricsResponse> {
  return requestJson<MetricsResponse>('/metrics');
}

export function getPerformanceAnalytics(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<PerformanceAnalyticsResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<PerformanceAnalyticsResponse>('/performance', params, advancedRequestOptions(options));
}

export function getPostSignalPerformanceSummary(horizon = '15m'): Promise<PostSignalPerformanceSummaryResponse> {
  const params = new URLSearchParams();
  params.set('horizon', horizon);
  return requestJson<PostSignalPerformanceSummaryResponse>('/performance/summary', params);
}

export function getPostSignalHistory(symbol?: string, limit = 10): Promise<PostSignalHistoryResponse> {
  const params = new URLSearchParams();
  if (symbol && symbol.trim().length > 0) {
    params.set('symbol', symbol.trim().toUpperCase());
  }
  params.set('limit', String(limit));
  params.set('offset', '0');
  return requestJson<PostSignalHistoryResponse>('/performance/signal-history', params);
}

export function getPostSignalDetail(signalId: string): Promise<PostSignalSnapshotResponse> {
  return requestJson<PostSignalSnapshotResponse>(`/performance/signal/${encodeURIComponent(signalId)}`);
}

export function getTradeQualityAnalytics(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<TradeQualityResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  params.set('limit', '5');
  params.set('offset', '0');
  return requestJson<TradeQualityResponse>('/performance/trade-quality', params, advancedRequestOptions(options));
}

export function getSignalValidation(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<SignalValidationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<SignalValidationResponse>('/performance/signal-validation', params, advancedRequestOptions(options));
}

export function getEdgeReport(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<EdgeReportResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<EdgeReportResponse>('/performance/edge-report', params, advancedRequestOptions(options));
}

export function getModuleAttribution(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<ModuleAttributionResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<ModuleAttributionResponse>('/performance/module-attribution', params, advancedRequestOptions(options));
}

export function getSimilarSetups(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<SimilarSetupResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<SimilarSetupResponse>('/performance/similar-setups', params, advancedRequestOptions(options));
}

export function getAdaptiveRecommendations(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<AdaptiveRecommendationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<AdaptiveRecommendationResponse>('/performance/adaptive-recommendations', params, advancedRequestOptions(options));
}

export function getScannerValidationReport(): Promise<ScannerValidationReportResponse> {
  return requestJson<ScannerValidationReportResponse>('/performance/scanner-validation-report');
}

export function evaluateScannerValidation(): Promise<ScannerValidationEvaluateResponse> {
  return requestJson<ScannerValidationEvaluateResponse>('/performance/scanner-validation/evaluate', undefined, {
    method: 'POST',
  });
}

export function getPaperTradeReview(
  symbol: string,
  filters?: RangeFilters,
  options?: ApiRequestOptions,
): Promise<PaperTradeReviewResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<PaperTradeReviewResponse>('/performance/review', params, advancedRequestOptions(options));
}

export function getProfileCalibration(
  symbol: string,
  filters?: RangeFilters & { profile?: TradingProfile },
  options?: ApiRequestOptions,
): Promise<ProfileCalibrationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  if (filters?.profile) {
    params.set('profile', filters.profile);
  }
  return requestJson<ProfileCalibrationResponse>('/performance/profile-calibration', params, advancedRequestOptions(options));
}

export function applyProfileCalibration(
  symbol: string,
  profile: TradingProfile,
  selectedThresholds?: string[],
): Promise<ProfileCalibrationApplyResponse> {
  return requestJson<ProfileCalibrationApplyResponse>('/performance/profile-calibration/apply', undefined, {
    method: 'POST',
    body: JSON.stringify({
      symbol: symbol.trim().toUpperCase(),
      profile,
      selected_thresholds: selectedThresholds,
    }),
  });
}

export function getProfileCalibrationComparison(
  symbol: string,
  profile: TradingProfile,
  filters?: RangeFilters & { sessionId?: string },
  options?: ApiRequestOptions,
): Promise<ProfileCalibrationComparisonResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  params.set('profile', profile);
  if (filters?.sessionId) {
    params.set('session_id', filters.sessionId);
  }
  return requestJson<ProfileCalibrationComparisonResponse>('/performance/profile-calibration/comparison', params, advancedRequestOptions(options));
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

export function getBotStatus(options?: ApiRequestOptions): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/status', undefined, requestOptions(options));
}

export function getWorkstation(symbol: string, options?: ApiRequestOptions): Promise<WorkstationResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<WorkstationResponse>('/bot/workstation', params, requestOptions(options));
}

export function getCandles(
  symbol: string,
  timeframe: '1m' | '5m' | '15m' | '1h',
  limit = 120,
  options?: ApiRequestOptions,
): Promise<CandleHistoryResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    timeframe,
    limit: String(limit),
  });
  return requestJson<CandleHistoryResponse>('/bot/candles', params, requestOptions(options));
}

export function getBackfillStatus(symbol: string, options?: ApiRequestOptions): Promise<BackfillStatusResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<BackfillStatusResponse>('/bot/backfill-status', params, requestOptions(options));
}

export function triggerBackfill(symbol: string, options?: ApiRequestOptions): Promise<BackfillStatusResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<BackfillStatusResponse>('/bot/backfill', params, {
    method: 'POST',
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  });
}

export function getTechnicalAnalysis(symbol: string, options?: ApiRequestOptions): Promise<TechnicalAnalysisResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<TechnicalAnalysisResponse>('/bot/technical-analysis', params, requestOptions(options));
}

export function getPatternAnalysis(
  symbol: string,
  horizon: string,
  options?: ApiRequestOptions,
): Promise<PatternAnalysisResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    horizon: horizon.trim().toLowerCase(),
  });
  return requestJson<PatternAnalysisResponse>('/bot/pattern-analysis', params, advancedRequestOptions(options));
}

export function getRegimeAnalysis(
  symbol: string,
  horizon: string,
  options?: ApiRequestOptions,
): Promise<RegimeAnalysisResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    horizon: horizon.trim().toLowerCase(),
  });
  return requestJson<RegimeAnalysisResponse>('/bot/regime-analysis', params, requestOptions(options));
}

export function getMarketSentiment(symbol: string, options?: ApiRequestOptions): Promise<MarketSentimentResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<MarketSentimentResponse>('/bot/market-sentiment', params, advancedRequestOptions(options));
}

export function getSymbolSentiment(symbol: string, options?: ApiRequestOptions): Promise<SymbolSentimentResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<SymbolSentimentResponse>('/bot/symbol-sentiment', params, advancedRequestOptions(options));
}

export function getFusionSignal(symbol: string, options?: ApiRequestOptions): Promise<FusionSignalResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<FusionSignalResponse>('/bot/fusion-signal', params, requestOptions(options));
}

export function getTradingAssistant(symbol: string, options?: ApiRequestOptions): Promise<TradingAssistantResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<TradingAssistantResponse>('/bot/trading-assistant', params, requestOptions(options));
}

export function getTradeEligibility(symbol: string, horizon?: string, options?: ApiRequestOptions): Promise<TradeEligibilityResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  if (horizon) {
    params.set('horizon', horizon.trim().toLowerCase());
  }
  return requestJson<TradeEligibilityResponse>('/bot/trade-eligibility', params, requestOptions(options));
}

export function getOpportunities(limit = 20): Promise<OpportunityResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return requestJson<OpportunityResponse[]>('/bot/opportunities', params);
}

export interface FuturesOpportunityFilters {
  maxSymbols: number;
  minOpportunityScore: number;
  includeWeakEvidence: boolean;
  horizon: string;
  includeAvoid: boolean;
}

export function getFuturesOpportunities(filters: FuturesOpportunityFilters): Promise<FuturesOpportunityScanResponse> {
  const params = new URLSearchParams({
    max_symbols: String(filters.maxSymbols),
    min_opportunity_score: String(filters.minOpportunityScore),
    include_weak_evidence: filters.includeWeakEvidence ? 'true' : 'false',
    horizon: filters.horizon,
    include_avoid: filters.includeAvoid ? 'true' : 'false',
    scan_timeout_seconds: '45',
  });
  return requestJson<FuturesOpportunityScanResponse>('/bot/futures-opportunities', params, {
    timeoutMs: FUTURES_SCANNER_TIMEOUT_MS,
  });
}

export function getFuturesLivePrices(symbols: string[]): Promise<FuturesLivePriceResponse> {
  const normalized = Array.from(new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean)));
  const params = new URLSearchParams({ symbols: normalized.join(',') });
  return requestJson<FuturesLivePriceResponse>('/bot/futures-opportunities/live-prices', params);
}

export function updateFuturesLiveSubscriptions(symbols: string[]): Promise<FuturesLiveSubscriptionResponse> {
  const normalized = Array.from(new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean))).slice(0, 100);
  return requestJson<FuturesLiveSubscriptionResponse>(
    '/bot/futures-opportunities/live-subscriptions',
    undefined,
    {
      method: 'POST',
      body: JSON.stringify({ symbols: normalized }),
    },
  );
}

export function getAISignal(symbol: string, options?: ApiRequestOptions): Promise<AISignalSummary | null> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<AISignalSummary | null>('/bot/ai-signal', params, advancedRequestOptions(options));
}

export function getAISignalHistory(
  symbol: string,
  filters?: Omit<Partial<HistoryFilters>, 'symbol'>,
  options?: ApiRequestOptions,
): Promise<AISignalHistoryResponse> {
  const params = buildHistoryParams({
    symbol,
    startDate: filters?.startDate,
    endDate: filters?.endDate,
    limit: filters?.limit ?? 20,
    offset: filters?.offset ?? 0,
  });
  return requestJson<AISignalHistoryResponse>('/bot/ai-signal/history', params, advancedRequestOptions(options));
}

export function getAISignalEvaluation(symbol: string, options?: ApiRequestOptions): Promise<AIOutcomeEvaluationResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<AIOutcomeEvaluationResponse>('/bot/ai-signal/evaluation', params, advancedRequestOptions(options));
}

export function getSymbols(query = '', limit = 20): Promise<SpotSymbolItem[]> {
  const params = new URLSearchParams();
  if (query.trim().length > 0) {
    params.set('query', query.trim());
  }
  params.set('limit', String(limit));
  return requestJson<SpotSymbolItem[]>('/symbols', params);
}

export function startBot(symbol: string, tradingProfile: TradingProfile): Promise<BotStatusResponse> {
  return requestJson<BotStatusResponse>('/bot/start', undefined, {
    method: 'POST',
    body: JSON.stringify({ symbol, trading_profile: tradingProfile }),
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

export function manualBuyMarket(symbol: string): Promise<ManualTradeResponse> {
  return requestJson<ManualTradeResponse>('/bot/manual-buy', undefined, {
    method: 'POST',
    body: JSON.stringify({ symbol }),
  });
}

export function manualClosePosition(symbol: string): Promise<ManualTradeResponse> {
  return requestJson<ManualTradeResponse>('/bot/manual-close', undefined, {
    method: 'POST',
    body: JSON.stringify({ symbol }),
  });
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
