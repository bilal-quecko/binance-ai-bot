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
  FuturesOpportunityScanResponse,
  HealthResponse,
  HistoryFilters,
  MetricsResponse,
  MarketSentimentResponse,
  PaginatedResponse,
  PnlHistoryResponse,
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
  SpotSymbolItem,
  SignalValidationResponse,
  SimilarSetupResponse,
  SymbolSummaryItem,
  SymbolSentimentResponse,
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

export function getPerformanceAnalytics(
  symbol: string,
  filters?: RangeFilters,
): Promise<PerformanceAnalyticsResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<PerformanceAnalyticsResponse>('/performance', params);
}

export function getTradeQualityAnalytics(
  symbol: string,
  filters?: RangeFilters,
): Promise<TradeQualityResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  params.set('limit', '5');
  params.set('offset', '0');
  return requestJson<TradeQualityResponse>('/performance/trade-quality', params);
}

export function getSignalValidation(
  symbol: string,
  filters?: RangeFilters,
): Promise<SignalValidationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<SignalValidationResponse>('/performance/signal-validation', params);
}

export function getEdgeReport(
  symbol: string,
  filters?: RangeFilters,
): Promise<EdgeReportResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<EdgeReportResponse>('/performance/edge-report', params);
}

export function getModuleAttribution(
  symbol: string,
  filters?: RangeFilters,
): Promise<ModuleAttributionResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<ModuleAttributionResponse>('/performance/module-attribution', params);
}

export function getSimilarSetups(
  symbol: string,
  filters?: RangeFilters,
): Promise<SimilarSetupResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<SimilarSetupResponse>('/performance/similar-setups', params);
}

export function getAdaptiveRecommendations(
  symbol: string,
  filters?: RangeFilters,
): Promise<AdaptiveRecommendationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<AdaptiveRecommendationResponse>('/performance/adaptive-recommendations', params);
}

export function getPaperTradeReview(
  symbol: string,
  filters?: RangeFilters,
): Promise<PaperTradeReviewResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  return requestJson<PaperTradeReviewResponse>('/performance/review', params);
}

export function getProfileCalibration(
  symbol: string,
  filters?: RangeFilters & { profile?: TradingProfile },
): Promise<ProfileCalibrationResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  if (filters?.profile) {
    params.set('profile', filters.profile);
  }
  return requestJson<ProfileCalibrationResponse>('/performance/profile-calibration', params);
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
): Promise<ProfileCalibrationComparisonResponse> {
  const params = buildRangeParams(filters);
  params.set('symbol', symbol.trim().toUpperCase());
  params.set('profile', profile);
  if (filters?.sessionId) {
    params.set('session_id', filters.sessionId);
  }
  return requestJson<ProfileCalibrationComparisonResponse>('/performance/profile-calibration/comparison', params);
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

export function getCandles(
  symbol: string,
  timeframe: '1m' | '5m' | '15m' | '1h',
  limit = 120,
): Promise<CandleHistoryResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    timeframe,
    limit: String(limit),
  });
  return requestJson<CandleHistoryResponse>('/bot/candles', params);
}

export function getBackfillStatus(symbol: string): Promise<BackfillStatusResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<BackfillStatusResponse>('/bot/backfill-status', params);
}

export function triggerBackfill(symbol: string): Promise<BackfillStatusResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<BackfillStatusResponse>('/bot/backfill', params, { method: 'POST' });
}

export function getTechnicalAnalysis(symbol: string): Promise<TechnicalAnalysisResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<TechnicalAnalysisResponse>('/bot/technical-analysis', params);
}

export function getPatternAnalysis(
  symbol: string,
  horizon: string,
): Promise<PatternAnalysisResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    horizon: horizon.trim().toLowerCase(),
  });
  return requestJson<PatternAnalysisResponse>('/bot/pattern-analysis', params);
}

export function getRegimeAnalysis(
  symbol: string,
  horizon: string,
): Promise<RegimeAnalysisResponse> {
  const params = new URLSearchParams({
    symbol: symbol.trim().toUpperCase(),
    horizon: horizon.trim().toLowerCase(),
  });
  return requestJson<RegimeAnalysisResponse>('/bot/regime-analysis', params);
}

export function getMarketSentiment(symbol: string): Promise<MarketSentimentResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<MarketSentimentResponse>('/bot/market-sentiment', params);
}

export function getSymbolSentiment(symbol: string): Promise<SymbolSentimentResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<SymbolSentimentResponse>('/bot/symbol-sentiment', params);
}

export function getFusionSignal(symbol: string): Promise<FusionSignalResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<FusionSignalResponse>('/bot/fusion-signal', params);
}

export function getTradingAssistant(symbol: string): Promise<TradingAssistantResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<TradingAssistantResponse>('/bot/trading-assistant', params);
}

export function getTradeEligibility(symbol: string, horizon?: string): Promise<TradeEligibilityResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  if (horizon) {
    params.set('horizon', horizon.trim().toLowerCase());
  }
  return requestJson<TradeEligibilityResponse>('/bot/trade-eligibility', params);
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
    limit: String(filters.maxSymbols),
    min_opportunity_score: String(filters.minOpportunityScore),
    include_weak_evidence: filters.includeWeakEvidence ? 'true' : 'false',
    horizon: filters.horizon,
    include_avoid: filters.includeAvoid ? 'true' : 'false',
  });
  return requestJson<FuturesOpportunityScanResponse>('/bot/futures-opportunities', params);
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

export function getAISignalEvaluation(symbol: string): Promise<AIOutcomeEvaluationResponse> {
  const params = new URLSearchParams({ symbol: symbol.trim().toUpperCase() });
  return requestJson<AIOutcomeEvaluationResponse>('/bot/ai-signal/evaluation', params);
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
