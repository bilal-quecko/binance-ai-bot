import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { AIEvaluationCard } from './components/AIEvaluationCard';
import { AIHistorySection } from './components/AIHistorySection';
import { AIAdvisorySection } from './components/AIAdvisorySection';
import { AdvancedDetailsPro } from './components/AdvancedDetailsPro';
import { AdaptiveRecommendationsSection } from './components/AdaptiveRecommendationsSection';
import { AutoRefreshSelector } from './components/AutoRefreshSelector';
import { BotControlPanel } from './components/BotControlPanel';
import { DataStateIndicator } from './components/DataStateIndicator';
import { DiagnosticsPanel } from './components/DiagnosticsPanel';
import { ErrorBoundary } from './components/ErrorBoundary';
import { FusionSignalSection } from './components/FusionSignalSection';
import { FuturesPaperScannerSection } from './components/FuturesPaperScannerSection';
import { FuturesPaperTradingSection } from './components/FuturesPaperTradingSection';
import { MarketSentimentSection } from './components/MarketSentimentSection';
import { MetricCard } from './components/MetricCard';
import { OpportunityScannerSection } from './components/OpportunityScannerSection';
import { PaperTradeReviewSection } from './components/PaperTradeReviewSection';
import { PerformanceAnalyticsSection } from './components/PerformanceAnalyticsSection';
import { PatternAnalysisSection } from './components/PatternAnalysisSection';
import { PersistenceHealthCard } from './components/PersistenceHealthCard';
import { ProfileCalibrationSection } from './components/ProfileCalibrationSection';
import { RegimeAnalysisSection } from './components/RegimeAnalysisSection';
import { SectionCard } from './components/SectionCard';
import { ScannerValidationReportSection } from './components/ScannerValidationReportSection';
import { SignalValidationSection } from './components/SignalValidationSection';
import { SpotPaperScannerSection } from './components/SpotPaperScannerSection';
import { StatePanel } from './components/StatePanel';
import { SymbolCandlestickChart } from './components/SymbolCandlestickChart';
import { SymbolSentimentSection } from './components/SymbolSentimentSection';
import { TechnicalAnalysisSection } from './components/TechnicalAnalysisSection';
import { TradeEligibilitySection } from './components/TradeEligibilitySection';
import { TradingAssistantSection } from './components/TradingAssistantSection';
import { TradeReadinessPanel } from './components/TradeReadinessPanel';
import { WhyNoTradePanel } from './components/WhyNoTradePanel';
import { TradeQualitySection } from './components/TradeQualitySection';
import { V1SignalDashboard } from './components/V1SignalDashboard';
import {
  getAISignalEvaluation,
  getAISignal,
  getAISignalHistory,
  getAdaptiveRecommendations,
  getBackfillStatus,
  getBotStatus,
  getCandles,
  getFusionSignal,
  getFuturesLivePrices,
  getFuturesOpportunityScanJob,
  getSpotOpportunityScanJob,
  updateFuturesLiveSubscriptions,
  getHealth,
  getEdgeReport,
  getMarketSentiment,
  getModuleAttribution,
  getOpportunities,
  getPatternAnalysis,
  getPaperTradeReview,
  getPerformanceAnalytics,
  getPostSignalDetail,
  getPostSignalHistory,
  getPostSignalPerformanceSummary,
  getRegimeAnalysis,
  getScannerValidationReport,
  getSignalValidation,
  getProfileCalibrationComparison,
  getProfileCalibration,
  getSimilarSetups,
  getSymbolSentiment,
  getTechnicalAnalysis,
  getTradeEligibility,
  getTradeQualityAnalytics,
  getSymbols,
  getTradingAssistant,
  getWorkstation,
  cancelFuturesOpportunityScanJob,
  cancelSpotOpportunityScanJob,
  evaluateScannerValidation,
  manualBuyMarket,
  manualClosePosition,
  applyProfileCalibration,
  pauseBot,
  resetBotSession,
  resumeBot,
  startBot,
  startFuturesOpportunityScan,
  startSpotOpportunityScan,
  stopBot,
  triggerBackfill,
  ApiRequestError,
  type SelectedMarket,
} from './lib/api';
import { badgeTone, classNames, formatCurrency, formatDateTime, formatDecimal, formatReasonCodes, pnlTone } from './lib/format';
import {
  LEVERAGE_OPTIONS,
  simulateFuturesLeverageFromPrices,
  type LeverageOption,
  type LeverageRiskLabel,
} from './lib/futuresLeverage';
import type {
  AIOutcomeEvaluationResponse,
  AISignalHistoryResponse,
  AISignalSummary,
  AdaptiveRecommendationResponse,
  AutoRefreshIntervalSeconds,
  BackfillStatusResponse,
  BotStatusResponse,
  CandleHistoryResponse,
  ChartTimeframe,
  EdgeReportResponse,
  HealthResponse,
  FusionSignalResponse,
  FuturesLivePriceItemResponse,
  FuturesLivePriceResponse,
  FuturesOpportunityScanJobResponse,
  FuturesOpportunityScanResponse,
  FuturesPaperSignalResponse,
  ModuleAttributionResponse,
  MarketSentimentResponse,
  ManualTradeResponse,
  OpportunityResponse,
  PatternAnalysisResponse,
  PatternHorizon,
  PaperTradeReviewResponse,
  ProfileCalibrationApplyResponse,
  ProfileCalibrationComparisonResponse,
  PerformanceAnalyticsResponse,
  PostSignalHistoryResponse,
  PostSignalPerformanceSummaryResponse,
  PostSignalSnapshotResponse,
  PersistenceHealthSummary,
  ProfileCalibrationResponse,
  RegimeAnalysisResponse,
  ScannerValidationReportResponse,
  SignalValidationResponse,
  SimilarSetupResponse,
  SpotOpportunityScanJobResponse,
  SpotOpportunityScanResponse,
  SpotOpportunitySignalResponse,
  SpotSymbolItem,
  SymbolSentimentResponse,
  TechnicalAnalysisResponse,
  TradeEligibilityResponse,
  TradingAssistantResponse,
  TradingProfile,
  TradeQualityResponse,
  WorkstationDataState,
  WorkstationResponse,
} from './lib/types';

interface RemoteState<T> {
  data: T;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

interface WorkspaceRefreshOptions {
  includeSignal?: boolean;
  includeAutoTrade?: boolean;
}

const SYMBOL_SWITCH_DEBOUNCE_MS = 350;
const ADVANCED_LOAD_DELAY_MS = 250;
const ADVANCED_DATA_WARNING = 'Some advanced data is still loading or timed out.';
const ADVANCED_SOFT_MESSAGE = 'Advanced data is still loading. Try refresh if it does not appear.';

const INITIAL_BOT_STATUS: BotStatusResponse = {
  state: 'stopped',
  mode: 'stopped',
  symbol: null,
  timeframe: '1m',
  paper_only: true,
  session_id: null,
  started_at: null,
  last_event_time: null,
  last_error: null,
  recovered_from_prior_session: false,
  broker_state_restored: false,
  recovery_message: null,
  trading_profile: 'balanced',
  tuning_version_id: null,
  baseline_tuning_version_id: null,
  persistence: {
    persistence_state: 'unavailable',
    persistence_message: 'Persistence state has not been read yet.',
    persistence_last_ok_at: null,
    recovery_source: null,
  },
};

const INITIAL_WORKSTATION: WorkstationResponse | null = null;
const INITIAL_AI_SIGNAL: AISignalSummary | null = null;
const INITIAL_AI_HISTORY: AISignalHistoryResponse = {
  items: [],
  total: 0,
  limit: 3,
  offset: 0,
  data_state: 'waiting_for_runtime',
  status_message: 'Start the live runtime for the selected symbol to generate advisory history.',
};
const INITIAL_AI_EVALUATION: AIOutcomeEvaluationResponse | null = null;
const INITIAL_CANDLES: CandleHistoryResponse | null = null;
const INITIAL_BACKFILL_STATUS: BackfillStatusResponse | null = null;
const INITIAL_TECHNICAL_ANALYSIS: TechnicalAnalysisResponse | null = null;
const INITIAL_MARKET_SENTIMENT: MarketSentimentResponse | null = null;
const INITIAL_SYMBOL_SENTIMENT: SymbolSentimentResponse | null = null;
const INITIAL_PATTERN_ANALYSIS: PatternAnalysisResponse | null = null;
const INITIAL_REGIME_ANALYSIS: RegimeAnalysisResponse | null = null;
const INITIAL_FUSION_SIGNAL: FusionSignalResponse | null = null;
const INITIAL_TRADING_ASSISTANT: TradingAssistantResponse | null = null;
const INITIAL_OPPORTUNITIES: OpportunityResponse[] = [];
const INITIAL_SPOT_OPPORTUNITIES: SpotOpportunityScanResponse | null = null;
const INITIAL_FUTURES_OPPORTUNITIES: FuturesOpportunityScanResponse | null = null;
const INITIAL_FUTURES_LIVE_PRICES: FuturesLivePriceResponse | null = null;
const INITIAL_PERFORMANCE: PerformanceAnalyticsResponse | null = null;
const INITIAL_TRADE_QUALITY: TradeQualityResponse | null = null;
const INITIAL_PAPER_REVIEW: PaperTradeReviewResponse | null = null;
const INITIAL_PROFILE_CALIBRATION: ProfileCalibrationResponse | null = null;
const INITIAL_PROFILE_CALIBRATION_COMPARISON: ProfileCalibrationComparisonResponse | null = null;
const INITIAL_SIGNAL_VALIDATION: SignalValidationResponse | null = null;
const INITIAL_EDGE_REPORT: EdgeReportResponse | null = null;
const INITIAL_MODULE_ATTRIBUTION: ModuleAttributionResponse | null = null;
const INITIAL_SIMILAR_SETUPS: SimilarSetupResponse | null = null;
const INITIAL_TRADE_ELIGIBILITY: TradeEligibilityResponse | null = null;
const INITIAL_ADAPTIVE_RECOMMENDATIONS: AdaptiveRecommendationResponse | null = null;
const INITIAL_SCANNER_VALIDATION: ScannerValidationReportResponse | null = null;
const INITIAL_POST_SIGNAL_PERFORMANCE: PostSignalPerformanceSummaryResponse | null = null;
const INITIAL_POST_SIGNAL_HISTORY: PostSignalHistoryResponse = { items: [], total: 0, limit: 10, offset: 0 };
const INITIAL_POST_SIGNAL_DETAIL: PostSignalSnapshotResponse | null = null;
const AI_HISTORY_PAGE_SIZE = 3;

function createRemoteState<T>(data: T): RemoteState<T> {
  return {
    data,
    loading: true,
    refreshing: false,
    error: null,
  };
}

function setPending<T>(current: RemoteState<T>): RemoteState<T> {
  if (current.loading) {
    return current;
  }
  if (current.data === null) {
    return { ...current, loading: true, error: null };
  }
  return { ...current, refreshing: true, error: null };
}

function stopSoftLoading<T>(current: RemoteState<T>): RemoteState<T> {
  return { ...current, loading: false, refreshing: false, error: null };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isCanceledRequest(error: unknown): boolean {
  return error instanceof ApiRequestError && error.category === 'request_canceled';
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeoutId);
        resolve();
      },
      { once: true },
    );
  });
}

function futuresScannerErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.category === 'backend_unavailable') {
      return 'Backend unavailable. The API server may be offline or restarting.';
    }
    if (error.category === 'scanner_timeout') {
      return 'Scanner timed out. Retry when Binance futures data is reachable.';
    }
    if (error.category === 'binance_unavailable') {
      return 'Binance API temporarily unavailable. Retry when Binance is reachable.';
    }
    if (error.category === 'network_proxy_error') {
      return 'Network/proxy error. Check the frontend proxy or API connection.';
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Unable to refresh futures paper scanner.';
}

function isTerminalFuturesScanJob(job: FuturesOpportunityScanJobResponse | null): boolean {
  return job ? ['completed', 'failed', 'cancelled'].includes(job.status) : true;
}

function isTerminalSpotScanJob(job: SpotOpportunityScanJobResponse | null): boolean {
  return job ? ['completed', 'failed', 'cancelled'].includes(job.status) : true;
}

function describeSignal(side: string | null | undefined): string {
  if (side === 'BUY') {
    return 'Entry setup is active';
  }
  if (side === 'SELL') {
    return 'Exit condition is active';
  }
  return 'No active action';
}

function formatOptionalCurrency(value: string | number | null | undefined, fallback: string): string {
  if (value === null || value === undefined) {
    return fallback;
  }
  return formatCurrency(value);
}

function formatOptionalDecimal(value: string | number | null | undefined, fallback: string): string {
  if (value === null || value === undefined) {
    return fallback;
  }
  return formatDecimal(value);
}

function computeMidPrice(workstation: WorkstationResponse | null): number | null {
  const top = workstation?.top_of_book;
  if (!top) {
    return null;
  }
  return (Number(top.bid_price) + Number(top.ask_price)) / 2;
}

function computeSpread(workstation: WorkstationResponse | null): number | null {
  const top = workstation?.top_of_book;
  if (!top) {
    return null;
  }
  return Number(top.ask_price) - Number(top.bid_price);
}

function computeBookImbalance(workstation: WorkstationResponse | null): number | null {
  const top = workstation?.top_of_book;
  if (!top) {
    return null;
  }
  const bid = Number(top.bid_quantity);
  const ask = Number(top.ask_quantity);
  const total = bid + ask;
  if (total === 0) {
    return null;
  }
  return (bid - ask) / total;
}

function describeLiveFieldGap(workstation: WorkstationResponse | null): string {
  if (!workstation?.is_runtime_symbol) {
    return 'Symbol unsupported until the live runtime is started for this symbol';
  }
  if (!workstation.top_of_book) {
    if (workstation.current_candle) {
      return 'Exchange depth unavailable';
    }
    return 'Awaiting websocket';
  }
  return 'Not yet populated';
}

type WorkstationTab = 'discover' | 'signal' | 'simulate' | 'futures' | 'validate' | 'advanced';
type SignalAnalysisTab = 'ai' | 'technicals' | 'liquidity' | 'sentiment' | 'validation' | 'similar' | 'notes';
type MainSignal = 'BUY' | 'WAIT' | 'AVOID' | 'EXIT';

interface FuturesSimulationDraft {
  symbol: string;
  direction: 'long' | 'short';
  entryPrice: string | null;
  livePrice: string | null;
  stopLoss: string | null;
  takeProfit: string | null;
  leverageSuggestion: string | null;
  confidence: number;
  opportunityScore: number;
  reason: string;
  riskGrade: string;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.replace(/_/g, ' ');
}

function mainSignal(assistant: TradingAssistantResponse | null, fusion: FusionSignalResponse | null): MainSignal {
  if (assistant?.decision === 'buy') {
    return 'BUY';
  }
  if (assistant?.decision === 'sell_exit') {
    return 'EXIT';
  }
  if (assistant?.decision === 'avoid') {
    return 'AVOID';
  }
  if (assistant?.decision === 'wait') {
    return 'WAIT';
  }
  if (fusion?.final_signal === 'long') {
    return 'BUY';
  }
  if (fusion?.final_signal === 'exit_long' || fusion?.final_signal === 'exit_short' || fusion?.final_signal === 'reduce_risk') {
    return 'EXIT';
  }
  if (fusion?.final_signal === 'short') {
    return 'AVOID';
  }
  return 'WAIT';
}

function signalTone(signal: MainSignal): string {
  if (signal === 'BUY') {
    return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100';
  }
  if (signal === 'EXIT' || signal === 'AVOID') {
    return 'border-rose-400/40 bg-rose-400/10 text-rose-100';
  }
  return 'border-amber-400/40 bg-amber-400/10 text-amber-100';
}

function eligibilityLabel(status: TradeEligibilityResponse['status'] | undefined): string {
  if (status === 'eligible') {
    return 'Eligible';
  }
  if (status === 'watch_only') {
    return 'Watch Only';
  }
  if (status === 'not_eligible') {
    return 'Not Eligible';
  }
  return 'Insufficient Data';
}

function selectedPrice(workstation: WorkstationResponse | null): string | null {
  return workstation?.last_price ?? workstation?.current_candle?.close ?? null;
}

function pctDisplay(value: number | null): string {
  if (value === null) {
    return '-';
  }
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function futuresSimulationDraftFromSignal(
  signal: FuturesPaperSignalResponse,
  livePrice?: FuturesLivePriceItemResponse,
): FuturesSimulationDraft {
  return {
    symbol: signal.symbol,
    direction: signal.direction === 'short' ? 'short' : 'long',
    entryPrice: signal.current_price,
    livePrice: livePrice?.live_price ?? signal.current_price,
    stopLoss: signal.suggested_stop_loss,
    takeProfit: signal.suggested_take_profit,
    leverageSuggestion: signal.leverage_suggestion,
    confidence: signal.confidence,
    opportunityScore: signal.opportunity_score,
    reason: signal.reason,
    riskGrade: signal.risk_grade,
  };
}

function leverageRiskTone(label: LeverageRiskLabel): string {
  if (label === 'low') {
    return 'text-emerald-200';
  }
  if (label === 'medium') {
    return 'text-amber-200';
  }
  if (label === 'high') {
    return 'text-orange-200';
  }
  return 'text-rose-200';
}

function liquiditySummary(assistant: TradingAssistantResponse | null): string {
  if (!assistant) {
    return 'Liquidity: collecting context';
  }
  if (assistant.sweep_risk === 'downside_sweep') {
    return 'Liquidity: Downside sweep risk';
  }
  if (assistant.sweep_risk === 'upside_sweep') {
    return 'Liquidity: Upside liquidity target nearby';
  }
  if (assistant.sweep_risk === 'both_sides' || assistant.trade_timing_adjustment === 'avoid_chop') {
    return 'Liquidity: Choppy both-side liquidity';
  }
  if (assistant.nearest_liquidity_target?.direction === 'up' && assistant.nearest_liquidity_target.strength !== 'low') {
    return 'Liquidity: Upside liquidity target nearby';
  }
  if (assistant.nearest_liquidity_target?.direction === 'down' && assistant.nearest_liquidity_target.strength !== 'low') {
    return 'Liquidity: Downside liquidity target nearby';
  }
  return 'Liquidity: Clean path';
}

function crowdSummary(assistant: TradingAssistantResponse | null): string {
  if (!assistant) {
    return 'Crowd: collecting context';
  }
  if (assistant.crowd_side === 'long_crowded') {
    return 'Crowd: Long heavy (downside risk)';
  }
  if (assistant.crowd_side === 'short_crowded') {
    return 'Crowd: Short heavy (squeeze risk)';
  }
  return 'Crowd: Balanced';
}

function liquidationSummary(assistant: TradingAssistantResponse | null): string {
  if (!assistant) {
    return 'Liquidation: No significant activity';
  }
  if (assistant.liquidation_signal === 'cascade_down') {
    return 'Liquidation: Downside cascade in progress';
  }
  if (assistant.liquidation_signal === 'cascade_up') {
    return 'Liquidation: Short squeeze active';
  }
  if (assistant.liquidation_signal === 'exhaustion') {
    return 'Liquidation: Exhaustion detected';
  }
  if (assistant.liquidation_signal === 'sweep_confirmation') {
    return 'Liquidation: Sweep confirmation';
  }
  return 'Liquidation: No significant activity';
}

function SymbolCommandBar({
  searchQuery,
  selectedSymbol,
  symbolResults,
  loading,
  error,
  status,
  selectedTradingProfile,
  actionLoading,
  actionError,
  actionMessage,
  onSearchChange,
  onSelectSymbol,
  onClearSelection,
  onTradingProfileChange,
  onStart,
  onPauseResume,
  onStop,
}: {
  searchQuery: string;
  selectedSymbol: string;
  symbolResults: SpotSymbolItem[];
  loading: boolean;
  error: string | null;
  status: BotStatusResponse;
  selectedTradingProfile: TradingProfile;
  actionLoading: boolean;
  actionError: string | null;
  actionMessage: string | null;
  onSearchChange: (value: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onClearSelection: () => void;
  onTradingProfileChange: (profile: TradingProfile) => void;
  onStart: () => void;
  onPauseResume: () => void;
  onStop: () => void;
}) {
  const showResults = searchQuery.trim().length > 0 && (selectedSymbol === '' || searchQuery.toUpperCase() !== selectedSymbol);
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/70 p-4 shadow-glow">
      <div className="grid gap-4 lg:grid-cols-[1.2fr,0.8fr] lg:items-end">
        <div>
          <label className="text-sm font-medium text-slate-300" htmlFor="symbol-search">Analyze Symbol</label>
          <div className="mt-2 flex gap-2">
            <input
              id="symbol-search"
              value={searchQuery}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search Binance symbol, e.g. BTCUSDT"
              className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400"
            />
            {selectedSymbol ? (
              <button
                type="button"
                onClick={onClearSelection}
                className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-slate-500 hover:text-white"
              >
                Clear
              </button>
            ) : null}
          </div>
          {showResults ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {loading ? <span className="text-sm text-slate-400">Searching...</span> : null}
              {symbolResults.slice(0, 8).map((item) => (
                <button
                  key={item.symbol}
                  type="button"
                  onClick={() => onSelectSymbol(item.symbol)}
                  className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-medium text-slate-200 hover:border-sky-400/50 hover:text-sky-100"
                >
                  {item.symbol}
                </button>
              ))}
              {error ? <span className="text-sm text-rose-300">{error}</span> : null}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
          <label className="grid gap-2 text-sm text-slate-300">
            Market Sensitivity
            <select
              value={selectedTradingProfile}
              onChange={(event) => onTradingProfileChange(event.target.value as TradingProfile)}
              className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
            >
              <option value="conservative">Conservative</option>
              <option value="balanced">Balanced</option>
              <option value="aggressive">Active</option>
            </select>
          </label>
          <span className="basis-full text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 lg:basis-auto">Paper Trading Controls</span>
          <button type="button" disabled={!selectedSymbol || actionLoading} onClick={onStart} className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-medium text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">
            Start
          </button>
          <button type="button" disabled={status.state === 'stopped' || actionLoading} onClick={onPauseResume} className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-sm font-medium text-amber-100 disabled:cursor-not-allowed disabled:opacity-50">
            {status.state === 'paused' ? 'Resume' : 'Pause'}
          </button>
          <button type="button" disabled={status.state === 'stopped' || actionLoading} onClick={onStop} className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-sm font-medium text-rose-100 disabled:cursor-not-allowed disabled:opacity-50">
            Stop
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1">Selected {selectedSymbol || '-'}</span>
        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1">Runtime {status.state}{status.symbol ? ` ${status.symbol}` : ''}</span>
        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1">Paper mode</span>
        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1">Advisory only</span>
        {actionMessage ? <span className="text-emerald-300">{actionMessage}</span> : null}
        {actionError ? <span className="text-rose-300">{actionError}</span> : null}
      </div>
    </section>
  );
}

function SignalDecisionCard({
  selectedSymbol,
  workstation,
  fusionSignal,
  tradingAssistant,
  tradeEligibility,
  loading,
  error,
}: {
  selectedSymbol: string;
  workstation: WorkstationResponse | null;
  fusionSignal: FusionSignalResponse | null;
  tradingAssistant: TradingAssistantResponse | null;
  tradeEligibility: TradeEligibilityResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (!selectedSymbol) {
    return <StatePanel title="Select a symbol" message="Choose a Binance symbol to load the decision view." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Signal unavailable" message={error} tone="error" />;
  }
  if (loading && !workstation && !fusionSignal && !tradingAssistant) {
    return <StatePanel title="Loading core signal" message={`Preparing ${selectedSymbol} price, candles, signal, and eligibility.`} tone="loading" />;
  }

  const signal = mainSignal(tradingAssistant, fusionSignal);
  const confidence = tradingAssistant ? `${tradingAssistant.confidence_score}%` : fusionSignal ? `${fusionSignal.confidence}%` : '-';
  const risk = humanize(tradingAssistant?.risk_label ?? fusionSignal?.risk_grade);
  const horizon = tradingAssistant?.best_timeframe ?? fusionSignal?.preferred_horizon ?? tradeEligibility?.preferred_horizon ?? '-';
  const reason = tradingAssistant?.simple_reason ?? fusionSignal?.top_reasons[0] ?? workstation?.explanation ?? 'Not enough signal context is available yet.';
  const action = tradingAssistant?.why_not_trade ?? tradeEligibility?.reason ?? (signal === 'BUY' ? 'Watch for paper-only confirmation before acting.' : 'Watch only until the setup improves.');
  const invalidation = fusionSignal?.invalidation_hint ?? (tradingAssistant?.suggested_stop_loss ? formatDecimal(tradingAssistant.suggested_stop_loss) : 'Not defined yet');
  const price = selectedPrice(workstation);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/70 p-6 shadow-glow">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-3xl font-semibold text-white">{selectedSymbol}</h2>
            <span className={classNames('rounded-full border px-4 py-1.5 text-sm font-semibold', signalTone(signal))}>{signal}</span>
            <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-300">Paper mode</span>
            <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-300">Advisory only</span>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">{reason}</p>
        </div>
        <div className="text-left lg:text-right">
          <p className="text-sm text-slate-500">Current Price</p>
          <p className="mt-1 text-3xl font-semibold text-white">{price ? formatCurrency(price) : '-'}</p>
          <p className="mt-1 text-xs text-slate-500">{formatDateTime(workstation?.last_market_event ?? null)}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Confidence" value={confidence} helper="Current signal certainty" />
        <MetricCard label="Risk" value={risk} helper="Risk grade" />
        <MetricCard label="Best Horizon" value={horizon} helper="Preferred watch window" />
        <MetricCard label="Eligibility" value={eligibilityLabel(tradeEligibility?.status)} helper={tradeEligibility?.evidence_strength ? `Evidence ${tradeEligibility.evidence_strength}` : 'Evidence pending'} />
      </div>

      <div className="mt-5 rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <p className="text-sm font-semibold text-slate-200">{liquiditySummary(tradingAssistant)}</p>
        <p className="mt-2 text-sm font-semibold text-slate-200">{crowdSummary(tradingAssistant)}</p>
        <p className="mt-2 text-sm font-semibold text-slate-200">{liquidationSummary(tradingAssistant)}</p>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-sm font-semibold text-slate-200">Recommended action</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">{action}</p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-sm font-semibold text-slate-200">Invalidation Point</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">{invalidation}</p>
        </div>
      </div>
    </section>
  );
}

function SimulatePanel({
  selectedSymbol,
  selectedMarket,
  futuresDraft,
  futuresStopLoss,
  futuresTakeProfit,
  workstation,
  tradingAssistant,
  fusionSignal,
  leverage,
  onLeverageChange,
  onFuturesStopLossChange,
  onFuturesTakeProfitChange,
  onFuturesReset,
  actionLoading,
  actionError,
  actionMessage,
  onManualBuy,
  onManualClose,
}: {
  selectedSymbol: string;
  selectedMarket: SelectedMarket;
  futuresDraft: FuturesSimulationDraft | null;
  futuresStopLoss: string;
  futuresTakeProfit: string;
  workstation: WorkstationResponse | null;
  tradingAssistant: TradingAssistantResponse | null;
  fusionSignal: FusionSignalResponse | null;
  leverage: LeverageOption;
  onLeverageChange: (leverage: LeverageOption) => void;
  onFuturesStopLossChange: (value: string) => void;
  onFuturesTakeProfitChange: (value: string) => void;
  onFuturesReset: () => void;
  actionLoading: boolean;
  actionError: string | null;
  actionMessage: string | null;
  onManualBuy: () => void;
  onManualClose: () => void;
}) {
  if (!selectedSymbol) {
    return <StatePanel title="Select a symbol" message="Choose a symbol before opening the paper simulation panel." tone="empty" />;
  }

  if (selectedMarket === 'futures') {
    if (!futuresDraft || futuresDraft.symbol !== selectedSymbol) {
      return (
        <section className="rounded-lg border border-borderSoft bg-panelBg/82 p-6 shadow-glow">
          <StatePanel
            title="Futures Paper Simulation"
            message="Choose Simulate on a LONG or SHORT futures scanner card to prefill this paper-only simulation."
            tone="empty"
          />
        </section>
      );
    }
    const simulation = simulateFuturesLeverageFromPrices({
      direction: futuresDraft.direction,
      entryPrice: futuresDraft.entryPrice,
      takeProfit: futuresTakeProfit || futuresDraft.takeProfit,
      stopLoss: futuresStopLoss || futuresDraft.stopLoss,
      livePrice: futuresDraft.livePrice,
      leverage,
    });
    const missingFuturesFields = [
      futuresDraft.entryPrice ? null : 'Missing entry',
      (futuresStopLoss || futuresDraft.stopLoss) ? null : 'Missing stop loss',
      (futuresTakeProfit || futuresDraft.takeProfit) ? null : 'Missing take profit',
    ].filter(Boolean);
    return (
      <section className="rounded-lg border border-borderSoft bg-panelBg/82 p-6 shadow-glow">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-semibold text-textPrimary">Futures Paper Simulation - {selectedSymbol}</h2>
              <span className={classNames('rounded-full border px-4 py-1.5 text-sm font-semibold', futuresDraft.direction === 'long' ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100' : 'border-rose-400/40 bg-rose-400/10 text-rose-100')}>
                {futuresDraft.direction.toUpperCase()}
              </span>
              <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-100">Paper Mode Only</span>
              <span className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-300">No Real Orders</span>
            </div>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-textSecondary">{futuresDraft.reason}</p>
          </div>
          <button
            type="button"
            onClick={onFuturesReset}
            className="rounded-lg border border-borderSoft bg-panelBgSoft px-3 py-2 text-sm font-medium text-textSecondary transition hover:border-borderMedium hover:text-textPrimary"
          >
            Cancel / Reset
          </button>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Entry Price" value={futuresDraft.entryPrice ? formatCurrency(futuresDraft.entryPrice) : '-'} helper="Scanner reference" />
          <MetricCard label="Current Futures Price" value={futuresDraft.livePrice ? formatCurrency(futuresDraft.livePrice) : '-'} helper="USD-M Futures mark/last price" />
          <MetricCard label="Confidence" value={`${futuresDraft.confidence}%`} helper={`Score ${futuresDraft.opportunityScore}`} />
          <MetricCard label="Risk Grade" value={futuresDraft.riskGrade} helper={futuresDraft.leverageSuggestion ?? `${leverage}x paper`} />
          <MetricCard label="Estimated TP %" value={pctDisplay(simulation.estimated_tp_return_percent)} helper="Editable target" />
          <MetricCard label="Estimated SL %" value={pctDisplay(simulation.estimated_sl_return_percent)} helper="Editable invalidation" />
          <MetricCard label="Live PnL %" value={pctDisplay(simulation.estimated_current_unrealized_return_percent)} helper="Display-only paper estimate" />
          <MetricCard label="Risk Label" value={simulation.liquidation_risk_label} helper={`${leverage}x paper leverage`} tone={simulation.liquidation_risk_label === 'low' ? 'positive' : simulation.liquidation_risk_label === 'extreme' ? 'negative' : 'default'} />
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <label className="grid gap-2 text-sm text-textSecondary">
            Leverage
            <select
              value={leverage}
              onChange={(event) => onLeverageChange(Number(event.target.value) as LeverageOption)}
              className="rounded-lg border border-borderSoft bg-panelBg px-3 py-2 text-sm text-textPrimary"
            >
              {LEVERAGE_OPTIONS.map((option) => <option key={option} value={option}>{option}x</option>)}
            </select>
          </label>
          <label className="grid gap-2 text-sm text-textSecondary">
            Stop Loss
            <input
              type="number"
              value={futuresStopLoss}
              onChange={(event) => onFuturesStopLossChange(event.target.value)}
              className="rounded-lg border border-borderSoft bg-panelBg px-3 py-2 text-sm text-textPrimary"
            />
          </label>
          <label className="grid gap-2 text-sm text-textSecondary">
            Take Profit
            <input
              type="number"
              value={futuresTakeProfit}
              onChange={(event) => onFuturesTakeProfitChange(event.target.value)}
              className="rounded-lg border border-borderSoft bg-panelBg px-3 py-2 text-sm text-textPrimary"
            />
          </label>
        </div>

        {simulation.leverage_warning ? (
          <div className={classNames('mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-4 text-sm leading-6', leverageRiskTone(simulation.liquidation_risk_label))}>
            {simulation.leverage_warning} This simulation is paper-only and does not place Binance futures orders.
          </div>
        ) : null}
        {missingFuturesFields.length > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-100">
            {missingFuturesFields.join('. ')}.
          </div>
        ) : null}
        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            disabled
            className="rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm font-medium text-slate-400 disabled:cursor-not-allowed"
          >
            Place Futures Paper Simulation
          </button>
          <span className="self-center text-xs text-textMuted">Frontend-only simulation state in this slice; no real futures execution is connected.</span>
        </div>
      </section>
    );
  }

  const signal = mainSignal(tradingAssistant, fusionSignal);
  const price = selectedPrice(workstation);
  const entry = tradingAssistant?.suggested_entry_zone ?? (price ? formatCurrency(price) : '-');
  const direction = fusionSignal?.final_signal === 'short' || signal === 'EXIT' ? 'short' : 'long';
  const simulation = simulateFuturesLeverageFromPrices({
    direction,
    entryPrice: price,
    takeProfit: tradingAssistant?.suggested_take_profit,
    stopLoss: tradingAssistant?.suggested_stop_loss,
    livePrice: price,
    leverage,
  });
  const spotBlockers = [
    tradingAssistant?.data_state === 'waiting_for_history' ? 'Waiting for candles' : null,
    tradingAssistant?.data_state === 'degraded_storage' ? 'Symbol not available on selected market.' : null,
    signal !== 'BUY' ? 'Signal not eligible' : null,
    tradingAssistant?.suggested_entry_zone || price ? null : 'Missing entry',
    tradingAssistant?.suggested_stop_loss ? null : 'Missing stop loss',
    tradingAssistant?.suggested_take_profit ? null : 'Missing take profit',
  ].filter(Boolean);
  const canPlaceSpotPaperTrade = spotBlockers.length === 0 && !actionLoading;

  return (
    <section className="rounded-lg border border-borderSoft bg-panelBg/82 p-6 shadow-glow">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-semibold text-textPrimary">Spot Paper Simulation - {selectedSymbol}</h2>
            <span className={classNames('rounded-full border px-4 py-1.5 text-sm font-semibold', signalTone(signal))}>{signal}</span>
            <span className="rounded-md border border-longGreen/25 bg-longGreen/10 px-3 py-1 text-xs font-semibold text-emerald-100">Paper Mode Only</span>
            <span className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-300">No Real Orders</span>
          </div>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-textSecondary">Review the selected Spot paper setup before using the existing manual paper trade path.</p>
        </div>
        <label className="grid gap-2 text-sm text-textSecondary">
          Leverage
          <select
            value={leverage}
            onChange={(event) => onLeverageChange(Number(event.target.value) as LeverageOption)}
            className="rounded-lg border border-borderSoft bg-panelBg px-3 py-2 text-sm text-textPrimary"
          >
            {LEVERAGE_OPTIONS.map((option) => <option key={option} value={option}>{option}x</option>)}
          </select>
        </label>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Entry" value={entry} helper="Selected-symbol reference" />
        <MetricCard label="Current Price" value={price ? formatCurrency(price) : '-'} helper={formatDateTime(workstation?.last_market_event ?? null)} />
        <MetricCard label="Stop" value={tradingAssistant?.suggested_stop_loss ? formatCurrency(tradingAssistant.suggested_stop_loss) : '-'} helper="Paper risk level" />
        <MetricCard label="Take Profit" value={tradingAssistant?.suggested_take_profit ? formatCurrency(tradingAssistant.suggested_take_profit) : '-'} helper="Paper target level" />
        <MetricCard label="Estimated TP %" value={pctDisplay(simulation.estimated_tp_return_percent)} helper={simulation.fee_slippage_estimated ? 'Estimated fees/slippage' : 'Fee-adjusted inputs available'} />
        <MetricCard label="Estimated SL %" value={pctDisplay(simulation.estimated_sl_return_percent)} helper="Leveraged paper loss estimate" />
        <MetricCard label="Live PnL %" value={pctDisplay(simulation.estimated_current_unrealized_return_percent)} helper="Display-only paper estimate" />
        <MetricCard label="Risk Level" value={tradingAssistant?.risk_label ?? simulation.liquidation_risk_label} helper="Spot paper readiness" tone={(tradingAssistant?.risk_label ?? simulation.liquidation_risk_label) === 'low' ? 'positive' : (tradingAssistant?.risk_label ?? simulation.liquidation_risk_label) === 'high' || simulation.liquidation_risk_label === 'extreme' ? 'negative' : 'default'} />
      </div>

      {simulation.leverage_warning ? (
        <div className={classNames('mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-4 text-sm leading-6', leverageRiskTone(simulation.liquidation_risk_label))}>
          {simulation.leverage_warning} This is paper-only and liquidation-risk-aware; it does not change scanner scoring or execution behavior.
        </div>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-borderSoft bg-panelBgSoft/65 p-4">
          <p className="text-sm font-semibold text-textPrimary">Paper Position State</p>
          {workstation?.current_position ? (
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-textSecondary">
              <div><span className="text-textMuted">Quantity</span><p>{formatDecimal(workstation.current_position.quantity)}</p></div>
              <div><span className="text-textMuted">Avg Entry</span><p>{formatCurrency(workstation.current_position.avg_entry_price)}</p></div>
              <div><span className="text-textMuted">Realized PnL</span><p className={pnlTone(workstation.current_position.realized_pnl)}>{formatCurrency(workstation.current_position.realized_pnl)}</p></div>
              <div><span className="text-textMuted">Quote</span><p>{workstation.current_position.quote_asset}</p></div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-textSecondary">No open paper position for the selected symbol.</p>
          )}
        </div>
        <div className="rounded-lg border border-borderSoft bg-panelBgSoft/65 p-4">
          <p className="text-sm font-semibold text-textPrimary">Manual Paper Controls</p>
          {spotBlockers.length > 0 ? (
            <div className="mt-3 rounded-lg border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-amber-100">
              {spotBlockers.join('. ')}.
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" disabled={!canPlaceSpotPaperTrade} onClick={onManualBuy} className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-medium text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">
              Place Spot Paper Trade
            </button>
            <button type="button" disabled={actionLoading || !workstation?.current_position} onClick={onManualClose} className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-sm font-medium text-rose-100 disabled:cursor-not-allowed disabled:opacity-50">
              Close Spot Paper Trade
            </button>
          </div>
          {actionMessage ? <p className="mt-3 text-sm text-emerald-300">{actionMessage}</p> : null}
          {actionError ? <p className="mt-3 text-sm text-rose-300">{actionError}</p> : null}
        </div>
      </div>
    </section>
  );
}

function ValidationSummary({ report, signalValidation, similarSetups }: {
  report: ScannerValidationReportResponse | null;
  signalValidation: SignalValidationResponse | null;
  similarSetups: SimilarSetupResponse | null;
}) {
  const bestHorizon = report?.horizon_performance
    .filter((item) => item.average_net_return !== null)
    .sort((left, right) => Number(right.average_net_return ?? 0) - Number(left.average_net_return ?? 0))[0]?.name
    ?? similarSetups?.best_horizon
    ?? '-';
  const evaluated = report?.evaluated_snapshots ?? signalValidation?.actionable_signals ?? 0;
  const valueOrGuide = (value: string | null | undefined) => value ?? (evaluated > 0 ? 'Pending' : 'Collect signals');
  const conclusion = humanize(report?.conclusion ?? signalValidation?.status ?? 'insufficient_data');
  return (
    <section className="rounded-lg border border-borderSoft bg-panelBg/82 p-6 shadow-glow">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-textPrimary">Paper Validation</h2>
          <p className="mt-2 text-sm leading-6 text-textSecondary">
            Trust view for scanner and selected-symbol signal evidence. Validation appears after enough paper signals are evaluated.
          </p>
        </div>
        <span className="rounded-md border border-accentPurple/35 bg-accentPurple/15 px-3 py-1 text-xs font-semibold text-violet-100">
          {conclusion}
        </span>
      </div>
      <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Total Evaluated Signals" value={String(evaluated)} helper="Paper validation samples" />
        <MetricCard label="Win Rate" value={valueOrGuide(report?.win_rate ? `${formatDecimal(report.win_rate)}%` : null)} helper="Scanner outcomes" />
        <MetricCard label="Expectancy" value={valueOrGuide(report?.expectancy ? `${formatDecimal(report.expectancy)}%` : null)} helper="Estimated net return" />
        <MetricCard label="Scanner vs Random" value={valueOrGuide(report?.scanner_vs_random_baseline.edge_vs_random ? `${formatDecimal(report.scanner_vs_random_baseline.edge_vs_random)}%` : null)} helper="Baseline comparison" />
        <MetricCard label="Best Horizon" value={bestHorizon} helper="Measured paper evidence" />
      </div>
      {evaluated === 0 ? (
        <div className="mt-4 rounded-lg border border-waitAmber/25 bg-waitAmber/10 p-4 text-sm leading-6 text-amber-100">
          Run the paper scanner and keep paper runtime active. This panel will summarize win rate, expectancy, and baseline comparison once evaluated outcomes exist.
        </div>
      ) : null}
    </section>
  );
}

function PostSignalPerformancePanel({
  summary,
  history,
  detail,
  loading,
  error,
  onSelectSignal,
}: {
  summary: PostSignalPerformanceSummaryResponse | null;
  history: PostSignalHistoryResponse;
  detail: PostSignalSnapshotResponse | null;
  loading: boolean;
  error: string | null;
  onSelectSignal: (signalId: string) => void;
}) {
  if (loading && !summary) {
    return <StatePanel title="Loading post-signal performance" message="Reading paper outcome snapshots." tone="loading" />;
  }
  if (error) {
    return <StatePanel title="Post-signal performance unavailable" message={error} tone="error" />;
  }
  const latestOutcome = detail?.outcomes[0] ?? null;
  const tpRate = summary?.tp_hit_rate ? `${formatDecimal(summary.tp_hit_rate)}%` : 'Collect signals';
  const slRate = summary?.sl_hit_rate ? `${formatDecimal(summary.sl_hit_rate)}%` : 'Collect signals';
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/70 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-white">Performance</h3>
          <p className="mt-1 text-sm text-slate-400">Paper outcome tracking for generated scanner, assistant, and eligibility signals.</p>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300">analysis only</span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <MetricCard label="Win Rate" value={summary?.win_rate ? `${formatDecimal(summary.win_rate)}%` : 'Collect signals'} helper={`${summary?.evaluated_signals ?? 0} evaluated`} />
        <MetricCard label="Avg Return" value={summary?.avg_return ? `${formatDecimal(summary.avg_return)}%` : 'Collect signals'} helper="15m paper outcome" />
        <MetricCard label="TP vs SL" value={`${tpRate} / ${slRate}`} helper="Lightweight TP/SL model" />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <MetricCard label="Base Win Rate" value={summary?.base_win_rate ? `${formatDecimal(summary.base_win_rate)}%` : 'Collect signals'} helper="Existing logic only" />
        <MetricCard label="Heatmap Win Rate" value={summary?.heatmap_win_rate ? `${formatDecimal(summary.heatmap_win_rate)}%` : 'Collect signals'} helper="Parallel heatmap read" />
        <MetricCard label="Heatmap Delta" value={summary?.delta_win_rate ? `${formatDecimal(summary.delta_win_rate)}%` : 'Collect signals'} helper="Heatmap minus base" />
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div>
          <p className="text-sm font-semibold text-slate-200">Signal History</p>
          <div className="mt-2 space-y-2">
            {history.items.slice(0, 5).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectSignal(item.id)}
                className="w-full rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-left text-sm text-slate-300 transition hover:border-slate-600"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-white">{item.symbol} {item.signal_type}</span>
                  <span className="text-xs text-slate-500">{item.source}</span>
                </div>
                <p className="mt-1 line-clamp-1 text-xs text-slate-400">{item.notes}</p>
                {item.heatmap_alignment === 'confirmed' || item.heatmap_alignment === 'conflict' ? (
                  <span className="mt-2 inline-flex rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                    {item.heatmap_alignment === 'confirmed' ? 'Heatmap Confirmed' : 'Heatmap Conflict'}
                  </span>
                ) : null}
              </button>
            ))}
            {history.items.length === 0 ? <p className="text-sm text-slate-500">No tracked signals yet.</p> : null}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-sm font-semibold text-slate-200">Signal Detail</p>
          {detail ? (
            <div className="mt-3 grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
              <div><span className="text-slate-500">Entry Price</span><p>{detail.entry_price ? formatCurrency(detail.entry_price) : '-'}</p></div>
              <div><span className="text-slate-500">Current Outcome</span><p>{humanize(latestOutcome?.outcome_state ?? 'pending')}</p></div>
              <div><span className="text-slate-500">Max Upside</span><p>{latestOutcome?.max_upside_percent ? `${formatDecimal(latestOutcome.max_upside_percent)}%` : '-'}</p></div>
              <div><span className="text-slate-500">Max Downside</span><p>{latestOutcome?.max_downside_percent ? `${formatDecimal(latestOutcome.max_downside_percent)}%` : '-'}</p></div>
              <div><span className="text-slate-500">TP/SL</span><p>{latestOutcome ? `${latestOutcome.did_price_hit_tp ? 'TP hit' : 'TP not hit'} / ${latestOutcome.did_price_hit_sl ? 'SL hit' : 'SL not hit'}` : '-'}</p></div>
              <div><span className="text-slate-500">Liquidity Prediction</span><p>{latestOutcome?.sweep_prediction_correct === null || latestOutcome?.sweep_prediction_correct === undefined ? 'Collect signals' : latestOutcome.sweep_prediction_correct ? 'correct' : 'missed'}</p></div>
              <div><span className="text-slate-500">Base vs Heatmap</span><p>{detail.base_signal_type ?? detail.signal_type} / {detail.heatmap_signal_type ?? '-'}</p></div>
              <div><span className="text-slate-500">Heatmap Result</span><p>{latestOutcome?.did_heatmap_improve_result ? 'improved' : latestOutcome?.did_heatmap_reduce_loss ? 'reduced loss' : 'not proven'}</p></div>
              <div><span className="text-slate-500">Heatmap Bias</span><p>{humanize(detail.heatmap_bias ?? 'neutral')}</p></div>
              <div><span className="text-slate-500">Actual Sweep</span><p>{humanize(latestOutcome?.actual_sweep_direction ?? 'none')}</p></div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">Select a tracked signal to inspect its outcome.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function PremiumCard({
  title,
  eyebrow,
  action,
  children,
  className,
}: {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={classNames('min-w-0 rounded-lg border border-borderSoft bg-panelBg/82 p-4 shadow-glow backdrop-blur', className)}>
      {(title || eyebrow || action) ? (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {eyebrow ? <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accentPurple">{eyebrow}</p> : null}
            {title ? <h2 className="mt-1 text-base font-semibold text-textPrimary">{title}</h2> : null}
          </div>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

function TopNavigation({
  tab,
  tabs,
  health,
  lastUpdatedAt,
  refreshLabel,
  autoRefreshSeconds,
  onTabChange,
  onRefresh,
  onAutoRefreshChange,
}: {
  tab: WorkstationTab;
  tabs: Array<[WorkstationTab, string, string]>;
  health: HealthResponse | null;
  lastUpdatedAt: Date | null;
  refreshLabel: string;
  autoRefreshSeconds: AutoRefreshIntervalSeconds;
  onTabChange: (tab: WorkstationTab) => void;
  onRefresh: () => void;
  onAutoRefreshChange: (value: AutoRefreshIntervalSeconds) => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-borderSoft bg-appBg/92 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1880px] flex-col gap-4 px-4 py-4 sm:px-6 2xl:px-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg border border-accentPurple/40 bg-accentPurple/20 text-sm font-black text-textPrimary shadow-glow">
              CX
            </div>
            <div>
              <h1 className="text-lg font-semibold leading-tight text-textPrimary">CEX AI</h1>
              <p className="text-xs text-textSecondary">Paper Trading Intelligence</p>
            </div>
          </div>

          <nav aria-label="Workspace tabs" className="flex min-w-0 gap-1 overflow-x-auto rounded-lg border border-borderSoft bg-panelBg/80 p-1">
            {tabs.map(([value, label, subtitle]) => (
              <button
                key={value}
                type="button"
                aria-current={tab === value ? 'page' : undefined}
                onClick={() => onTabChange(value)}
                className={classNames(
                  'min-w-32 rounded-md border px-4 py-2 text-left transition focus-visible:border-accentPurple',
                  tab === value
                    ? 'border-accentPurple/60 bg-accentPurple/20 text-textPrimary shadow-glow'
                    : 'border-transparent text-textSecondary hover:bg-panelBgSoft hover:text-textPrimary',
                )}
              >
                <span className="block text-sm font-semibold">{label}</span>
                <span className="mt-0.5 block text-[11px] text-textMuted">{subtitle}</span>
              </button>
            ))}
          </nav>

          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <span className={classNames('rounded-lg px-3 py-2 text-xs font-semibold', badgeTone(health?.status ?? 'unknown'))}>
              {health?.status ?? 'loading'}
            </span>
            <span className="rounded-lg border border-longGreen/25 bg-longGreen/10 px-3 py-2 text-xs font-semibold text-emerald-100">
              Paper Mode
              <span className="ml-2 text-longGreen/80">No Real Money</span>
            </span>
            <button
              type="button"
              onClick={onRefresh}
              className="rounded-lg border border-accentPurple/35 bg-accentPurple/15 px-3 py-2 text-xs font-semibold text-violet-100 transition hover:border-accentPurple hover:bg-accentPurple/25"
            >
              Refresh
            </button>
            <AutoRefreshSelector value={autoRefreshSeconds} onChange={onAutoRefreshChange} />
            <button type="button" aria-label="Theme placeholder" className="h-9 rounded-lg border border-borderSoft bg-panelBg px-3 text-xs font-semibold text-textSecondary">Theme</button>
          </div>
        </div>
        <p className="text-xs text-textMuted">Last updated {formatDateTime(lastUpdatedAt?.toISOString() ?? null)} | Auto refresh {refreshLabel}</p>
      </div>
    </header>
  );
}

function SidebarSymbolSearch({
  searchQuery,
  selectedSymbol,
  symbolResults,
  loading,
  error,
  onSearchChange,
  onSelectSymbol,
  onClearSelection,
}: {
  searchQuery: string;
  selectedSymbol: string;
  symbolResults: SpotSymbolItem[];
  loading: boolean;
  error: string | null;
  onSearchChange: (value: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onClearSelection: () => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500" htmlFor="sidebar-symbol-search">
          Watchlist
        </label>
        {selectedSymbol ? (
          <button type="button" onClick={onClearSelection} className="text-xs font-medium text-slate-400 hover:text-white">
            Clear
          </button>
        ) : null}
      </div>
      <input
        id="sidebar-symbol-search"
        value={searchQuery}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="Search BTCUSDT"
        className="mt-3 w-full rounded-lg border border-slate-800 bg-slate-950/80 px-3 py-2 text-sm text-white outline-none transition focus:border-violet-400"
      />
      {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}
      <div className="mt-3 space-y-1">
        {loading ? <p className="text-xs text-slate-500">Searching symbols...</p> : null}
        {symbolResults.slice(0, 5).map((item) => (
          <button
            key={item.symbol}
            type="button"
            onClick={() => onSelectSymbol(item.symbol)}
            className={classNames(
              'flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition',
              selectedSymbol === item.symbol ? 'bg-violet-500/20 text-violet-100' : 'bg-slate-900/55 text-slate-300 hover:bg-slate-900 hover:text-white',
            )}
          >
            <span className="font-semibold">{item.symbol}</span>
            <span className="text-xs text-slate-500">{item.base_asset}/{item.quote_asset}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function LeftSidebar({
  selectedSymbol,
  symbolSearch,
  symbolResults,
  symbolsLoading,
  symbolsError,
  futuresScan,
  livePrices,
  marketSentiment,
  technicalAnalysis,
  collapsed,
  onSearchChange,
  onSelectSymbol,
  onClearSelection,
  onViewScanner,
  onToggleCollapse,
}: {
  selectedSymbol: string;
  symbolSearch: string;
  symbolResults: SpotSymbolItem[];
  symbolsLoading: boolean;
  symbolsError: string | null;
  futuresScan: FuturesOpportunityScanResponse | null;
  livePrices: FuturesLivePriceResponse | null;
  marketSentiment: MarketSentimentResponse | null;
  technicalAnalysis: TechnicalAnalysisResponse | null;
  collapsed: boolean;
  onSearchChange: (value: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onClearSelection: () => void;
  onViewScanner: () => void;
  onToggleCollapse: () => void;
}) {
  const topSignals = [
    ...(futuresScan?.long_candidates ?? []),
    ...(futuresScan?.short_candidates ?? []),
  ]
    .sort((left, right) => right.opportunity_score - left.opportunity_score)
    .slice(0, 5);
  const livePriceBySymbol = new Map((livePrices?.items ?? []).map((item) => [item.symbol, item.live_price]));
  const marketBias = marketSentiment?.market_state ?? technicalAnalysis?.trend_direction ?? 'waiting';
  const volume = futuresScan?.scanned_count ? `${futuresScan.scanned_count} symbols scanned` : 'Scanner waiting';

  if (collapsed) {
    return (
      <aside className="min-w-0 xl:sticky xl:top-28 xl:max-h-[calc(100vh-8rem)]">
        <PremiumCard className="flex items-center gap-2 p-2 xl:flex-col">
          <button
            type="button"
            aria-label="Expand watchlist sidebar"
            onClick={onToggleCollapse}
            className="grid h-10 w-10 place-items-center rounded-md border border-borderSoft bg-panelBgSoft text-textSecondary transition hover:border-accentPurple hover:text-textPrimary"
          >
            &gt;
          </button>
          {[selectedSymbol, ...topSignals.map((signal) => signal.symbol)]
            .filter((symbol, index, list): symbol is string => Boolean(symbol) && list.indexOf(symbol) === index)
            .slice(0, 5)
            .map((symbol) => (
              <button
                key={symbol}
                type="button"
                aria-label={`Open ${symbol} signal`}
                onClick={() => onSelectSymbol(symbol)}
                className={classNames(
                  'grid h-10 w-10 place-items-center rounded-md border text-xs font-bold transition',
                  selectedSymbol === symbol
                    ? 'border-accentPurple bg-accentPurple/20 text-textPrimary shadow-glow'
                    : 'border-borderSoft bg-panelBgSoft text-textSecondary hover:border-accentPurple/60 hover:text-textPrimary',
                )}
              >
                {symbol.slice(0, 3)}
              </button>
            ))}
        </PremiumCard>
      </aside>
    );
  }

  return (
    <aside className="min-w-0 space-y-4 xl:sticky xl:top-28 xl:max-h-[calc(100vh-8rem)] xl:overflow-y-auto">
      <PremiumCard
        title="Market Overview"
        action={(
          <button
            type="button"
            aria-label="Collapse watchlist sidebar"
            onClick={onToggleCollapse}
            className="rounded-md border border-borderSoft px-2 py-1 text-xs font-semibold text-textSecondary transition hover:border-accentPurple hover:text-textPrimary"
          >
            Collapse
          </button>
        )}
      >
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-3 border-b border-borderSoft pb-3">
            <span className="text-textSecondary">Market Tone</span>
            <span className={marketBias.includes('bull') || marketBias === 'risk_on' ? 'font-semibold text-emerald-300' : marketBias.includes('bear') || marketBias === 'risk_off' ? 'font-semibold text-rose-300' : 'font-semibold text-amber-200'}>
              {humanize(marketBias)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-borderSoft pb-3">
            <span className="text-textSecondary">Scanner Coverage</span>
            <span className="font-semibold text-textPrimary">{volume}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-textSecondary">Selected Symbol</span>
            <span className="font-semibold text-textPrimary">{selectedSymbol || '-'}</span>
          </div>
        </div>
      </PremiumCard>

      <PremiumCard
        title="Top Opportunities"
        action={<button type="button" onClick={onViewScanner} className="text-xs font-semibold text-violet-300 hover:text-violet-100">View Full</button>}
      >
        <div className="space-y-2">
          {topSignals.length === 0 ? <p className="text-sm text-slate-500">Run the futures scanner to populate ranked opportunities.</p> : null}
          {topSignals.map((signal) => (
            <button
              key={`${signal.symbol}-${signal.direction}`}
              type="button"
              onClick={() => onSelectSymbol(signal.symbol)}
              className="flex w-full items-center justify-between rounded-md border border-slate-800 bg-slate-900/50 px-3 py-2 text-left transition hover:border-violet-400/40 hover:bg-slate-900"
            >
              <span>
                <span className="block text-sm font-semibold text-white">{signal.symbol}</span>
                <span className={signal.direction === 'long' ? 'text-xs text-emerald-300' : signal.direction === 'short' ? 'text-xs text-rose-300' : 'text-xs text-slate-400'}>
                  {signal.direction.toUpperCase()}
                </span>
              </span>
              <span className="text-right">
                <span className="block text-sm font-semibold text-emerald-300">{signal.opportunity_score}</span>
                <span className="text-[11px] text-slate-500">score</span>
              </span>
            </button>
          ))}
        </div>
      </PremiumCard>

      <PremiumCard>
        <SidebarSymbolSearch
          searchQuery={symbolSearch}
          selectedSymbol={selectedSymbol}
          symbolResults={symbolResults}
          loading={symbolsLoading}
          error={symbolsError}
          onSearchChange={onSearchChange}
          onSelectSymbol={onSelectSymbol}
          onClearSelection={onClearSelection}
        />
        <div className="mt-4 space-y-2">
          {[selectedSymbol, ...topSignals.map((signal) => signal.symbol)]
            .filter((symbol, index, list): symbol is string => Boolean(symbol) && list.indexOf(symbol) === index)
            .slice(0, 6)
            .map((symbol) => (
              <button
                key={symbol}
                type="button"
                onClick={() => onSelectSymbol(symbol)}
                className={classNames(
                  'flex w-full items-center justify-between rounded-md px-3 py-2 text-sm transition',
                  selectedSymbol === symbol ? 'bg-violet-500/25 text-white' : 'bg-slate-900/45 text-slate-300 hover:bg-slate-900',
                )}
              >
                <span className="font-semibold">{symbol}</span>
                <span className="text-xs text-slate-500">{livePriceBySymbol.get(symbol) ? formatCurrency(livePriceBySymbol.get(symbol) as string) : 'watch'}</span>
              </button>
          ))}
        </div>
      </PremiumCard>

      <PremiumCard>
        <div className="flex gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-accentPurple/30 bg-accentPurple/15 text-accentPurple">
            PM
          </div>
          <div>
            <p className="text-sm font-semibold text-textPrimary">Paper Mode Active</p>
            <p className="mt-2 text-sm leading-6 text-textSecondary">All orders are simulated. No real spot or futures orders are submitted.</p>
          </div>
        </div>
      </PremiumCard>
    </aside>
  );
}

function SidebarSummaryCard({
  title,
  rows,
  action,
}: {
  title: string;
  rows: Array<[string, string, string?]>;
  action?: ReactNode;
}) {
  return (
    <PremiumCard title={title} action={action}>
      <div className="space-y-3 text-sm">
        {rows.map(([label, value, tone]) => (
          <div key={label} className="flex items-center justify-between gap-3 border-b border-slate-800 pb-3 last:border-b-0 last:pb-0">
            <span className="text-slate-400">{label}</span>
            <span className={classNames('font-semibold text-white', tone)}>{value}</span>
          </div>
        ))}
      </div>
    </PremiumCard>
  );
}

function RightSidebar({
  workstation,
  health,
  signalValidation,
  performance,
  tradeQuality,
  persistence,
  onValidate,
  onAdvanced,
}: {
  workstation: WorkstationResponse | null;
  health: HealthResponse | null;
  signalValidation: SignalValidationResponse | null;
  performance: PerformanceAnalyticsResponse | null;
  tradeQuality: TradeQualityResponse | null;
  persistence: PersistenceHealthSummary;
  onValidate: () => void;
  onAdvanced: () => void;
}) {
  const validationWin = signalValidation?.horizons[0]?.win_rate_pct ? `${formatDecimal(signalValidation.horizons[0].win_rate_pct)}%` : 'Collect signals';
  const validationExp = signalValidation?.horizons[0]?.expectancy_pct ? `${formatDecimal(signalValidation.horizons[0].expectancy_pct)}%` : 'Collect signals';
  const runtimeStatus = workstation?.runtime_status.state ?? health?.status ?? 'waiting';
  const recentEvents = [
    workstation?.last_action ? ['Last action', `${workstation.last_action.signal_side} ${workstation.last_action.execution_status ?? 'pending'}`, workstation.last_action.event_time] : null,
    workstation?.last_market_event ? ['Market update', workstation.symbol, workstation.last_market_event] : null,
    persistence.persistence_last_ok_at ? ['Persistence', humanize(persistence.persistence_state), persistence.persistence_last_ok_at] : null,
  ].filter(Boolean) as Array<[string, string, string]>;
  return (
    <aside className="min-w-0 space-y-4 xl:sticky xl:top-28 xl:max-h-[calc(100vh-8rem)] xl:overflow-y-auto">
      <PremiumCard title="System Status">
        <div className="flex items-start gap-3">
          <span className={classNames('mt-1 h-3 w-3 rounded-full', workstation?.data_state === 'ready' ? 'bg-longGreen shadow-greenGlow' : 'bg-waitAmber')} />
          <div>
            <p className="font-semibold text-textPrimary">Runtime: {humanize(runtimeStatus)}</p>
            <p className="mt-2 text-sm leading-6 text-textSecondary">{workstation?.data_state === 'ready' ? 'All systems operational.' : 'Start paper runtime to collect live market context.'}</p>
          </div>
        </div>
        <button type="button" onClick={onAdvanced} className="mt-4 w-full rounded-md border border-borderSoft bg-panelBgSoft px-3 py-2 text-sm font-semibold text-violet-200 transition hover:border-accentPurple/60">
          View Details
        </button>
      </PremiumCard>

      <SidebarSummaryCard
        title="Validation Summary"
        rows={[
          ['Total Signals', String(signalValidation?.total_signals ?? 0)],
          ['Win Rate', validationWin, 'text-emerald-300'],
          ['Expectancy', validationExp, validationExp.startsWith('-') ? 'text-rose-300' : 'text-emerald-300'],
          ['Status', humanize(signalValidation?.status ?? 'insufficient_data')],
        ]}
        action={<button type="button" onClick={onValidate} className="text-xs font-semibold text-violet-300 hover:text-violet-100">View Full</button>}
      />

      <SidebarSummaryCard
        title="Performance Summary"
        rows={[
          ['Total PnL', formatCurrency(performance?.session_realized_pnl ?? '0'), pnlTone(performance?.session_realized_pnl ?? '0')],
          ['Closed Trades', String(performance?.total_closed_trades ?? 0)],
          ['Profit Factor', performance?.profit_factor ? formatDecimal(performance.profit_factor) : '-'],
          ['Max Drawdown', formatCurrency(performance?.max_drawdown ?? '0'), 'text-rose-300'],
        ]}
        action={<button type="button" onClick={onAdvanced} className="text-xs font-semibold text-violet-300 hover:text-violet-100">View Full</button>}
      />

      <PremiumCard title="Recent Events" action={<button type="button" onClick={onAdvanced} className="text-xs font-semibold text-violet-300 hover:text-violet-100">View All</button>}>
        <div className="space-y-3">
          {recentEvents.length === 0 ? <p className="text-sm leading-6 text-textSecondary">AI history and paper events will appear after the runtime generates advisory snapshots.</p> : null}
          {recentEvents.map(([label, value, time]) => (
            <div key={`${label}-${time}`} className="flex gap-3 border-b border-borderSoft pb-3 last:border-b-0 last:pb-0">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-longGreen" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-textPrimary">{label}</span>
                  <span className="text-xs text-textMuted">{formatDateTime(time)}</span>
                </div>
                <p className="mt-1 truncate text-xs text-textSecondary">{value}</p>
              </div>
            </div>
          ))}
          {tradeQuality?.summary.total_closed_trades ? (
            <div className="rounded-md border border-borderSoft bg-panelBgSoft p-3 text-xs text-textSecondary">
              Trade quality: {tradeQuality.summary.average_entry_quality_score ? `${formatDecimal(tradeQuality.summary.average_entry_quality_score)}%` : 'pending'} entry quality across {tradeQuality.summary.total_closed_trades} closed trades.
            </div>
          ) : null}
        </div>
      </PremiumCard>
    </aside>
  );
}

function SignalHeader({
  selectedSymbol,
  workstation,
  chart,
  timeframe,
  refreshing,
  onTimeframeChange,
  onRefresh,
}: {
  selectedSymbol: string;
  workstation: WorkstationResponse | null;
  chart: CandleHistoryResponse | null;
  timeframe: ChartTimeframe;
  refreshing: boolean;
  onTimeframeChange: (timeframe: ChartTimeframe) => void;
  onRefresh: () => void;
}) {
  const price = selectedPrice(workstation) ?? chart?.current_price ?? null;
  const candles = chart?.candles ?? [];
  const first = candles[0]?.close ? Number(candles[0].close) : null;
  const last = candles[candles.length - 1]?.close ? Number(candles[candles.length - 1].close) : null;
  const change = first && last ? ((last - first) / first) * 100 : null;
  return (
    <PremiumCard className="p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-3xl font-semibold text-textPrimary">{selectedSymbol || 'Select Symbol'}</h2>
            <span className="rounded-md border border-borderSoft bg-panelBgSoft px-2 py-1 text-xs font-semibold text-textSecondary">Binance Spot</span>
            <span className={change !== null && change >= 0 ? 'text-sm font-semibold text-emerald-300' : 'text-sm font-semibold text-rose-300'}>{pctDisplay(change)}</span>
          </div>
          <p className="mt-2 text-sm text-textSecondary">
            {price ? formatCurrency(price) : 'Price waiting'} | Updated {formatDateTime(workstation?.last_market_event ?? chart?.candles[chart.candles.length - 1]?.close_time ?? null)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Chart timeframe">
          {(['1m', '5m', '15m', '1h'] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={timeframe === item}
              onClick={() => onTimeframeChange(item)}
              className={classNames(
                'h-9 rounded-md border px-3 text-sm font-semibold transition',
                timeframe === item
                  ? 'border-accentPurple/60 bg-accentPurple/25 text-violet-100 shadow-glow'
                  : 'border-borderSoft bg-panelBg text-textSecondary hover:border-borderMedium hover:text-textPrimary',
              )}
            >
              {item}
            </button>
          ))}
          <button
            type="button"
            onClick={onRefresh}
            className="h-9 rounded-md border border-accentPurple/35 bg-accentPurple/15 px-3 text-sm font-semibold text-violet-100 transition hover:border-accentPurple"
          >
            {refreshing ? 'Refreshing' : 'Refresh'}
          </button>
        </div>
      </div>
    </PremiumCard>
  );
}

function PrimaryAssistantCard({
  selectedSymbol,
  workstation,
  fusionSignal,
  tradingAssistant,
  tradeEligibility,
  loading,
  error,
  onViewFullAnalysis,
}: {
  selectedSymbol: string;
  workstation: WorkstationResponse | null;
  fusionSignal: FusionSignalResponse | null;
  tradingAssistant: TradingAssistantResponse | null;
  tradeEligibility: TradeEligibilityResponse | null;
  loading: boolean;
  error: string | null;
  onViewFullAnalysis: () => void;
}) {
  if (!selectedSymbol) {
    return <StatePanel title="Select a symbol" message="Choose a Binance symbol to load the decision view." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Signal unavailable" message={error} tone="error" />;
  }
  if (loading && !workstation && !fusionSignal && !tradingAssistant) {
    return <StatePanel title="Loading core signal" message={`Preparing ${selectedSymbol} price, candles, signal, and eligibility.`} tone="loading" />;
  }
  const signal = mainSignal(tradingAssistant, fusionSignal);
  const confidence = tradingAssistant?.confidence_score ?? fusionSignal?.confidence ?? 0;
  const reasons = [
    tradingAssistant?.simple_reason,
    ...(fusionSignal?.top_reasons ?? []),
    tradeEligibility?.reason,
  ].filter(Boolean).slice(0, 5) as string[];
  const invalidation = fusionSignal?.invalidation_hint ?? (tradingAssistant?.suggested_stop_loss ? formatCurrency(tradingAssistant.suggested_stop_loss) : 'Not defined yet');
  const expectedEdge = fusionSignal?.expected_edge_pct ? `${formatDecimal(fusionSignal.expected_edge_pct)}%` : 'Collect signals';
  const risk = humanize(tradingAssistant?.risk_label ?? fusionSignal?.risk_grade);
  const entryZone = tradingAssistant?.suggested_entry_zone ?? 'Wait for a cleaner entry zone';
  const stopLoss = tradingAssistant?.suggested_stop_loss ? formatCurrency(tradingAssistant.suggested_stop_loss) : '-';
  const takeProfit = tradingAssistant?.suggested_take_profit ? formatCurrency(tradingAssistant.suggested_take_profit) : '-';
  const bestTimeframe = tradingAssistant?.best_timeframe ?? fusionSignal?.preferred_horizon ?? tradeEligibility?.preferred_horizon ?? '-';
  const confidenceTone = signal === 'BUY' ? 'border-longGreen text-longGreen' : signal === 'WAIT' ? 'border-waitAmber text-waitAmber' : 'border-shortRed text-shortRed';

  return (
    <PremiumCard
      title="AI Trading Assistant"
      action={<span className="rounded-md border border-borderSoft px-2 py-1 text-xs text-textSecondary">Beginner View</span>}
      className="h-full"
    >
      <div className="grid gap-6">
        <div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <span className={classNames('inline-flex rounded-md border px-4 py-2 text-4xl font-semibold', signalTone(signal))}>{signal}</span>
              <p className="mt-3 text-sm font-semibold text-textSecondary">{tradingAssistant?.confidence_label ? `${humanize(tradingAssistant.confidence_label)} confidence` : 'Confidence building'}</p>
            </div>
            <div className={classNames('grid h-24 w-24 shrink-0 place-items-center rounded-full border-4 bg-panelBgSoft shadow-cyanGlow', confidenceTone)}>
              <div className="text-center">
                <p className="text-2xl font-semibold">{confidence}%</p>
                <p className="text-[11px] text-textSecondary">Confidence</p>
              </div>
            </div>
          </div>
          <div className="mt-5">
            <p className="text-sm font-semibold text-textPrimary">Why?</p>
            <p className="mt-2 text-sm leading-6 text-textSecondary">{reasons[0] ?? 'Signal reasoning is waiting for more context.'}</p>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-textMuted">Entry Zone</p>
              <p className="mt-1 font-semibold text-textPrimary">{entryZone}</p>
            </div>
            <div>
              <p className="text-textMuted">Stop Loss</p>
              <p className="mt-1 font-semibold text-textPrimary">{stopLoss}</p>
            </div>
            <div>
              <p className="text-textMuted">Take Profit</p>
              <p className="mt-1 font-semibold text-textPrimary">{takeProfit}</p>
            </div>
            <div>
              <p className="text-textMuted">Best Timeframe</p>
              <p className="mt-1 font-semibold text-textPrimary">{bestTimeframe}</p>
            </div>
            <div>
              <p className="text-textMuted">Risk Level</p>
              <p className="mt-1 font-semibold text-textPrimary">{risk}</p>
            </div>
            <div>
              <p className="text-textMuted">Expected Edge</p>
              <p className="mt-1 font-semibold text-textPrimary">{expectedEdge}</p>
            </div>
          </div>
        </div>
        <div className="rounded-md border border-borderSoft bg-panelBgSoft/65 p-3 text-sm leading-6 text-textSecondary">
          <p><span className="font-semibold text-textPrimary">Invalidation:</span> {invalidation}</p>
          <p className="mt-1">{tradingAssistant?.why_not_trade ?? tradeEligibility?.reason ?? 'Paper-only advisory. Wait for deterministic risk checks before any paper action.'}</p>
        </div>
        <button
          type="button"
          onClick={onViewFullAnalysis}
          className="w-full rounded-md border border-borderSoft bg-panelBgSoft px-3 py-3 text-sm font-semibold text-textSecondary transition hover:border-accentPurple/60 hover:text-textPrimary"
        >
          View Full Analysis
        </button>
      </div>
    </PremiumCard>
  );
}

function InsightCard({ label, value, helper, tone = 'text-white' }: { label: string; value: string; helper: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/65 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={classNames('mt-2 text-lg font-semibold', tone)}>{value}</p>
      <p className="mt-1 text-xs text-slate-400">{helper}</p>
    </div>
  );
}

function KeyInsightCards({
  regime,
  technical,
  assistant,
  similarSetups,
  workstation,
}: {
  regime: RegimeAnalysisResponse | null;
  technical: TechnicalAnalysisResponse | null;
  assistant: TradingAssistantResponse | null;
  similarSetups: SimilarSetupResponse | null;
  workstation: WorkstationResponse | null;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      <InsightCard label="Market Regime" value={humanize(regime?.regime_label ?? 'waiting')} helper={regime ? `${regime.confidence}% confidence` : 'Needs regime data'} tone={regime?.regime_label?.includes('up') ? 'text-emerald-300' : regime?.regime_label?.includes('down') ? 'text-rose-300' : 'text-amber-200'} />
      <InsightCard label="Trend Strength" value={technical?.trend_strength_score !== null && technical?.trend_strength_score !== undefined ? `${technical.trend_strength_score}/100` : humanize(technical?.trend_strength ?? 'waiting')} helper={humanize(technical?.trend_direction ?? 'Trend pending')} tone={technical?.trend_direction === 'bullish' ? 'text-emerald-300' : technical?.trend_direction === 'bearish' ? 'text-rose-300' : 'text-white'} />
      <InsightCard label="Volatility" value={humanize(technical?.volatility_regime ?? 'waiting')} helper="Current technical volatility" tone={technical?.volatility_regime === 'high' ? 'text-amber-200' : 'text-white'} />
      <InsightCard label="Liquidity Bias" value={humanize(assistant?.liquidity_bias ?? 'neutral')} helper={liquiditySummary(assistant).replace('Liquidity: ', '')} tone={assistant?.liquidity_bias === 'bullish' ? 'text-emerald-300' : assistant?.liquidity_bias === 'bearish' ? 'text-rose-300' : 'text-white'} />
      <InsightCard label="Similar Setups" value={similarSetups?.horizons[0]?.win_rate_pct ? `${formatDecimal(similarSetups.horizons[0].win_rate_pct)}%` : humanize(similarSetups?.reliability_label ?? 'waiting')} helper={similarSetups ? `${similarSetups.matching_sample_size} matches` : 'Need outcome history'} tone="text-emerald-300" />
      <InsightCard label="Data Quality" value={humanize(workstation?.data_state ?? 'waiting')} helper={workstation?.is_runtime_symbol ? 'Live symbol context' : 'Runtime not attached'} tone={workstation?.data_state === 'ready' ? 'text-emerald-300' : 'text-amber-200'} />
    </div>
  );
}

function SignalAnalysisTabs({
  activeTab,
  onTabChange,
  selectedSymbol,
  aiSignal,
  aiHistory,
  aiEvaluation,
  patternAnalysis,
  selectedPatternHorizon,
  onSelectPatternHorizon,
  technicalAnalysis,
  marketSentiment,
  symbolSentiment,
  tradingAssistant,
  signalValidation,
  edgeReport,
  moduleAttribution,
  similarSetups,
  loading,
  refreshing,
  errors,
  workstationDataState,
  workstationStatusMessage,
  onAiHistoryPrevious,
  onAiHistoryNext,
}: {
  activeTab: SignalAnalysisTab;
  onTabChange: (tab: SignalAnalysisTab) => void;
  selectedSymbol: string;
  aiSignal: RemoteState<AISignalSummary | null>;
  aiHistory: RemoteState<AISignalHistoryResponse>;
  aiEvaluation: RemoteState<AIOutcomeEvaluationResponse | null>;
  patternAnalysis: RemoteState<PatternAnalysisResponse | null>;
  selectedPatternHorizon: PatternHorizon;
  onSelectPatternHorizon: (horizon: PatternHorizon) => void;
  technicalAnalysis: RemoteState<TechnicalAnalysisResponse | null>;
  marketSentiment: RemoteState<MarketSentimentResponse | null>;
  symbolSentiment: RemoteState<SymbolSentimentResponse | null>;
  tradingAssistant: RemoteState<TradingAssistantResponse | null>;
  signalValidation: RemoteState<SignalValidationResponse | null>;
  edgeReport: RemoteState<EdgeReportResponse | null>;
  moduleAttribution: RemoteState<ModuleAttributionResponse | null>;
  similarSetups: SimilarSetupResponse | null;
  loading: boolean;
  refreshing: boolean;
  errors: string | null;
  workstationDataState: WorkstationDataState;
  workstationStatusMessage: string;
  onAiHistoryPrevious: () => void;
  onAiHistoryNext: () => void;
}) {
  const tabs: Array<[SignalAnalysisTab, string]> = [
    ['ai', 'AI Analysis'],
    ['technicals', 'Technicals'],
    ['liquidity', 'Liquidity'],
    ['sentiment', 'Sentiment'],
    ['validation', 'Validation'],
    ['similar', 'Similar Setups'],
    ['notes', 'Notes'],
  ];
  return (
    <PremiumCard className="p-0">
      <div className="flex gap-1 overflow-x-auto border-b border-slate-800 px-3 pt-3">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => onTabChange(value)}
            className={classNames(
              'whitespace-nowrap border-b-2 px-3 py-3 text-sm font-semibold transition',
              activeTab === value ? 'border-violet-400 text-violet-200' : 'border-transparent text-slate-400 hover:text-white',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="p-4">
        {activeTab === 'ai' ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <AIHistorySection symbol={selectedSymbol} history={aiHistory.data.items} loading={aiHistory.loading} refreshing={aiHistory.refreshing} error={aiHistory.error} dataState={aiHistory.data.data_state} statusMessage={aiHistory.data.status_message} total={aiHistory.data.total} limit={aiHistory.data.limit} offset={aiHistory.data.offset} onPrevious={onAiHistoryPrevious} onNext={onAiHistoryNext} />
            <AIEvaluationCard symbol={selectedSymbol} evaluation={aiEvaluation.data} loading={aiEvaluation.loading} refreshing={aiEvaluation.refreshing} error={aiEvaluation.error} dataState={aiEvaluation.data?.data_state ?? workstationDataState} statusMessage={aiEvaluation.data?.status_message ?? workstationStatusMessage} />
          </div>
        ) : null}
        {activeTab === 'technicals' ? <TechnicalAnalysisSection symbol={selectedSymbol} analysis={technicalAnalysis.data} loading={technicalAnalysis.loading} refreshing={technicalAnalysis.refreshing} error={technicalAnalysis.error} /> : null}
        {activeTab === 'sentiment' ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <MarketSentimentSection symbol={selectedSymbol} sentiment={marketSentiment.data} loading={marketSentiment.loading} refreshing={marketSentiment.refreshing} error={marketSentiment.error} />
            <SymbolSentimentSection symbol={selectedSymbol} sentiment={symbolSentiment.data} loading={symbolSentiment.loading} refreshing={symbolSentiment.refreshing} error={symbolSentiment.error} />
          </div>
        ) : null}
        {activeTab === 'liquidity' ? <TradingAssistantSection symbol={selectedSymbol} assistant={tradingAssistant.data?.symbol === selectedSymbol ? tradingAssistant.data : null} loading={loading} refreshing={refreshing} error={errors} /> : null}
        {activeTab === 'validation' ? <SignalValidationSection symbol={selectedSymbol} validation={signalValidation.data} edgeReport={edgeReport.data} moduleAttribution={moduleAttribution.data} similarSetups={similarSetups} loading={signalValidation.loading} refreshing={signalValidation.refreshing || edgeReport.refreshing || moduleAttribution.refreshing} error={signalValidation.error ?? edgeReport.error ?? moduleAttribution.error} /> : null}
        {activeTab === 'similar' ? (
          <div className="grid gap-4 lg:grid-cols-[0.9fr,1.1fr]">
            <div className="grid gap-3 sm:grid-cols-2">
              <InsightCard label="Reliability" value={humanize(similarSetups?.reliability_label ?? 'waiting')} helper={similarSetups ? `${similarSetups.matching_sample_size} evaluated matches` : 'Collect paper outcomes to compare setups.'} tone="text-violet-200" />
              <InsightCard label="Best Horizon" value={similarSetups?.best_horizon ?? '-'} helper="Measured closest outcome window" />
              <InsightCard label="Pattern Window" value={selectedPatternHorizon} helper={patternAnalysis.data?.status_message ?? 'Pattern context updates with selected horizon.'} />
              <InsightCard label="Pattern State" value={humanize(patternAnalysis.data?.data_state ?? 'waiting')} helper="Trend persistence, reversal, breakout/range context" />
            </div>
            <PatternAnalysisSection symbol={selectedSymbol} selectedHorizon={selectedPatternHorizon} analysis={patternAnalysis.data} loading={patternAnalysis.loading} refreshing={patternAnalysis.refreshing} error={patternAnalysis.error} onSelectHorizon={onSelectPatternHorizon} />
          </div>
        ) : null}
        {activeTab === 'notes' ? (
          <div className="grid gap-4 md:grid-cols-3">
            <InsightCard label="Safety" value="Paper Only" helper="No live trading or real futures execution." tone="text-emerald-300" />
            <InsightCard label="Validation" value={humanize(signalValidation.data?.status ?? 'waiting')} helper="Use measured outcomes before trusting a signal." />
            <InsightCard label="Data" value={humanize(workstationDataState)} helper={workstationStatusMessage} />
          </div>
        ) : null}
      </div>
    </PremiumCard>
  );
}

function SignalWorkspace({
  selectedSymbol,
  workstation,
  fusionSignal,
  tradingAssistant,
  tradeEligibility,
  regimeAnalysis,
  technicalAnalysis,
  similarSetups,
  candles,
  selectedChartTimeframe,
  signalAnalysisTab,
  loading,
  error,
  onChartTimeframeChange,
  onSignalAnalysisTabChange,
  onRefresh,
  analysisProps,
}: {
  selectedSymbol: string;
  workstation: WorkstationResponse | null;
  fusionSignal: FusionSignalResponse | null;
  tradingAssistant: TradingAssistantResponse | null;
  tradeEligibility: TradeEligibilityResponse | null;
  regimeAnalysis: RegimeAnalysisResponse | null;
  technicalAnalysis: RemoteState<TechnicalAnalysisResponse | null>;
  similarSetups: SimilarSetupResponse | null;
  candles: RemoteState<CandleHistoryResponse | null>;
  selectedChartTimeframe: ChartTimeframe;
  signalAnalysisTab: SignalAnalysisTab;
  loading: boolean;
  error: string | null;
  onChartTimeframeChange: (timeframe: ChartTimeframe) => void;
  onSignalAnalysisTabChange: (tab: SignalAnalysisTab) => void;
  onRefresh: () => void;
  analysisProps: Omit<Parameters<typeof SignalAnalysisTabs>[0], 'activeTab' | 'onTabChange' | 'selectedSymbol' | 'technicalAnalysis' | 'similarSetups'>;
}) {
  return (
    <div className="space-y-4">
      <SignalHeader
        selectedSymbol={selectedSymbol}
        workstation={workstation}
        chart={candles.data}
        timeframe={selectedChartTimeframe}
        refreshing={candles.refreshing}
        onTimeframeChange={onChartTimeframeChange}
        onRefresh={onRefresh}
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
        <PremiumCard className="p-3">
          <SymbolCandlestickChart
            symbol={selectedSymbol}
            timeframe={selectedChartTimeframe}
            chart={candles.data}
            chartLoading={candles.loading || candles.refreshing}
            chartError={candles.error}
            technicalAnalysis={technicalAnalysis.data}
          />
        </PremiumCard>
        <PrimaryAssistantCard
          selectedSymbol={selectedSymbol}
          workstation={workstation}
          fusionSignal={fusionSignal}
          tradingAssistant={tradingAssistant}
          tradeEligibility={tradeEligibility}
          loading={loading}
          error={error}
          onViewFullAnalysis={() => onSignalAnalysisTabChange('ai')}
        />
      </div>
      <KeyInsightCards
        regime={regimeAnalysis}
        technical={technicalAnalysis.data}
        assistant={tradingAssistant}
        similarSetups={similarSetups}
        workstation={workstation}
      />
      <SignalAnalysisTabs
        {...analysisProps}
        activeTab={signalAnalysisTab}
        onTabChange={onSignalAnalysisTabChange}
        selectedSymbol={selectedSymbol}
        technicalAnalysis={technicalAnalysis}
        similarSetups={similarSetups}
      />
    </div>
  );
}

function App() {
  const [tab, setTab] = useState<WorkstationTab>('discover');
  const [signalAnalysisTab, setSignalAnalysisTab] = useState<SignalAnalysisTab>('ai');
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState<AutoRefreshIntervalSeconds>(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const [health, setHealth] = useState<RemoteState<HealthResponse | null>>(createRemoteState<HealthResponse | null>(null));
  const [botStatus, setBotStatus] = useState<RemoteState<BotStatusResponse>>(createRemoteState(INITIAL_BOT_STATUS));
  const [workstation, setWorkstation] = useState<RemoteState<WorkstationResponse | null>>(createRemoteState(INITIAL_WORKSTATION));
  const [aiSignal, setAiSignal] = useState<RemoteState<AISignalSummary | null>>(createRemoteState(INITIAL_AI_SIGNAL));
  const [aiHistory, setAiHistory] = useState<RemoteState<AISignalHistoryResponse>>(createRemoteState(INITIAL_AI_HISTORY));
  const [aiEvaluation, setAiEvaluation] = useState<RemoteState<AIOutcomeEvaluationResponse | null>>(createRemoteState(INITIAL_AI_EVALUATION));
  const [candles, setCandles] = useState<RemoteState<CandleHistoryResponse | null>>(createRemoteState(INITIAL_CANDLES));
  const [backfillStatus, setBackfillStatus] = useState<RemoteState<BackfillStatusResponse | null>>(createRemoteState(INITIAL_BACKFILL_STATUS));
  const [technicalAnalysis, setTechnicalAnalysis] = useState<RemoteState<TechnicalAnalysisResponse | null>>(createRemoteState(INITIAL_TECHNICAL_ANALYSIS));
  const [marketSentiment, setMarketSentiment] = useState<RemoteState<MarketSentimentResponse | null>>(createRemoteState(INITIAL_MARKET_SENTIMENT));
  const [symbolSentiment, setSymbolSentiment] = useState<RemoteState<SymbolSentimentResponse | null>>(createRemoteState(INITIAL_SYMBOL_SENTIMENT));
  const [patternAnalysis, setPatternAnalysis] = useState<RemoteState<PatternAnalysisResponse | null>>(createRemoteState(INITIAL_PATTERN_ANALYSIS));
  const [regimeAnalysis, setRegimeAnalysis] = useState<RemoteState<RegimeAnalysisResponse | null>>(createRemoteState(INITIAL_REGIME_ANALYSIS));
  const [fusionSignal, setFusionSignal] = useState<RemoteState<FusionSignalResponse | null>>(createRemoteState(INITIAL_FUSION_SIGNAL));
  const [tradingAssistant, setTradingAssistant] = useState<RemoteState<TradingAssistantResponse | null>>(createRemoteState(INITIAL_TRADING_ASSISTANT));
  const [opportunities, setOpportunities] = useState<RemoteState<OpportunityResponse[]>>(createRemoteState(INITIAL_OPPORTUNITIES));
  const [spotOpportunities, setSpotOpportunities] = useState<RemoteState<SpotOpportunityScanResponse | null>>(createRemoteState(INITIAL_SPOT_OPPORTUNITIES));
  const [spotScanJob, setSpotScanJob] = useState<SpotOpportunityScanJobResponse | null>(null);
  const [futuresOpportunities, setFuturesOpportunities] = useState<RemoteState<FuturesOpportunityScanResponse | null>>(createRemoteState(INITIAL_FUTURES_OPPORTUNITIES));
  const [futuresScanJob, setFuturesScanJob] = useState<FuturesOpportunityScanJobResponse | null>(null);
  const [futuresLivePrices, setFuturesLivePrices] = useState<RemoteState<FuturesLivePriceResponse | null>>(createRemoteState(INITIAL_FUTURES_LIVE_PRICES));
  const [performanceAnalytics, setPerformanceAnalytics] = useState<RemoteState<PerformanceAnalyticsResponse | null>>(createRemoteState(INITIAL_PERFORMANCE));
  const [tradeQualityAnalytics, setTradeQualityAnalytics] = useState<RemoteState<TradeQualityResponse | null>>(createRemoteState(INITIAL_TRADE_QUALITY));
  const [paperTradeReview, setPaperTradeReview] = useState<RemoteState<PaperTradeReviewResponse | null>>(createRemoteState(INITIAL_PAPER_REVIEW));
  const [profileCalibration, setProfileCalibration] = useState<RemoteState<ProfileCalibrationResponse | null>>(createRemoteState(INITIAL_PROFILE_CALIBRATION));
  const [profileCalibrationComparison, setProfileCalibrationComparison] = useState<RemoteState<ProfileCalibrationComparisonResponse | null>>(createRemoteState(INITIAL_PROFILE_CALIBRATION_COMPARISON));
  const [signalValidation, setSignalValidation] = useState<RemoteState<SignalValidationResponse | null>>(createRemoteState(INITIAL_SIGNAL_VALIDATION));
  const [edgeReport, setEdgeReport] = useState<RemoteState<EdgeReportResponse | null>>(createRemoteState(INITIAL_EDGE_REPORT));
  const [moduleAttribution, setModuleAttribution] = useState<RemoteState<ModuleAttributionResponse | null>>(createRemoteState(INITIAL_MODULE_ATTRIBUTION));
  const [similarSetups, setSimilarSetups] = useState<RemoteState<SimilarSetupResponse | null>>(createRemoteState(INITIAL_SIMILAR_SETUPS));
  const [tradeEligibility, setTradeEligibility] = useState<RemoteState<TradeEligibilityResponse | null>>(createRemoteState(INITIAL_TRADE_ELIGIBILITY));
  const [adaptiveRecommendations, setAdaptiveRecommendations] = useState<RemoteState<AdaptiveRecommendationResponse | null>>(createRemoteState(INITIAL_ADAPTIVE_RECOMMENDATIONS));
  const [scannerValidation, setScannerValidation] = useState<RemoteState<ScannerValidationReportResponse | null>>(createRemoteState(INITIAL_SCANNER_VALIDATION));
  const [postSignalPerformance, setPostSignalPerformance] = useState<RemoteState<PostSignalPerformanceSummaryResponse | null>>(createRemoteState(INITIAL_POST_SIGNAL_PERFORMANCE));
  const [postSignalHistory, setPostSignalHistory] = useState<RemoteState<PostSignalHistoryResponse>>(createRemoteState(INITIAL_POST_SIGNAL_HISTORY));
  const [postSignalDetail, setPostSignalDetail] = useState<RemoteState<PostSignalSnapshotResponse | null>>(createRemoteState(INITIAL_POST_SIGNAL_DETAIL));
  const [symbolResults, setSymbolResults] = useState<RemoteState<SpotSymbolItem[]>>(createRemoteState<SpotSymbolItem[]>([]));

  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [selectedMarket, setSelectedMarket] = useState<SelectedMarket>('spot');
  const [selectedFuturesSimulation, setSelectedFuturesSimulation] = useState<FuturesSimulationDraft | null>(null);
  const [futuresSimulationStopLoss, setFuturesSimulationStopLoss] = useState('');
  const [futuresSimulationTakeProfit, setFuturesSimulationTakeProfit] = useState('');
  const [symbolSearch, setSymbolSearch] = useState('');
  const [selectedPatternHorizon, setSelectedPatternHorizon] = useState<PatternHorizon>('7d');
  const [selectedChartTimeframe, setSelectedChartTimeframe] = useState<ChartTimeframe>('1m');
  const [futuresScannerFilters, setFuturesScannerFilters] = useState({
    maxSymbols: 50,
    minOpportunityScore: 70,
    includeWeakEvidence: true,
    horizon: '7d',
    includeAvoid: true,
    marketSensitivity: 'balanced' as TradingProfile,
  });
  const [spotScannerFilters, setSpotScannerFilters] = useState({
    maxSymbols: 50,
    minOpportunityScore: 70,
    minConfidence: 60,
    horizon: '7d',
    includeAvoid: true,
  });
  const [selectedFuturesLeverage, setSelectedFuturesLeverage] = useState<LeverageOption>(5);
  const [futuresAutoRescanMinutes, setFuturesAutoRescanMinutes] = useState<0 | 5 | 15>(0);
  const [heartbeatNow, setHeartbeatNow] = useState(new Date());
  const [futuresLiveSubscriptionWarning, setFuturesLiveSubscriptionWarning] = useState<string | null>(null);
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false);
  const [selectedTradingProfile, setSelectedTradingProfile] = useState<TradingProfile>('balanced');
  const [aiHistoryOffset, setAiHistoryOffset] = useState(0);
  const [botActionLoading, setBotActionLoading] = useState(false);
  const [botActionError, setBotActionError] = useState<string | null>(null);
  const [botActionMessage, setBotActionMessage] = useState<string | null>(null);
  const [profileApplyLoading, setProfileApplyLoading] = useState(false);
  const [scannerValidationEvaluating, setScannerValidationEvaluating] = useState(false);
  const [scannerValidationEvaluateMessage, setScannerValidationEvaluateMessage] = useState<string | null>(null);
  const [scannerValidationEvaluateError, setScannerValidationEvaluateError] = useState<string | null>(null);
  const [debouncedSelectedSymbol, setDebouncedSelectedSymbol] = useState('');
  const [advancedDataWarning, setAdvancedDataWarning] = useState<string | null>(null);
  const selectedSymbolRef = useRef(selectedSymbol);
  const selectedMarketRef = useRef<SelectedMarket>(selectedMarket);
  const workspaceRefreshControllerRef = useRef<AbortController | null>(null);
  const backfillControllerRef = useRef<AbortController | null>(null);
  const workspaceRefreshSequenceRef = useRef(0);

  const futuresHeartbeatSymbols = useMemo(() => {
    const scan = futuresOpportunities.data;
    if (!scan) {
      return [];
    }
    return Array.from(new Set([
      ...scan.long_candidates.map((signal) => signal.symbol),
      ...scan.short_candidates.map((signal) => signal.symbol),
      ...scan.neutral_candidates.map((signal) => signal.symbol),
    ]));
  }, [futuresOpportunities.data]);

  const loadSymbols = useCallback(async (query: string) => {
    setSymbolResults((current) => ({ ...current, loading: current.data.length === 0, refreshing: current.data.length > 0, error: null }));
    try {
      const symbols = await getSymbols(query, 10);
      setSymbolResults({ data: symbols, loading: false, refreshing: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load tradable Spot symbols.';
      setSymbolResults((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const refreshOpportunities = useCallback(async () => {
    setOpportunities((current) => setPending(current));
    try {
      const opportunityData = await getOpportunities(10);
      setOpportunities({ data: opportunityData, loading: false, refreshing: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh opportunity rankings.';
      setOpportunities((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const refreshSpotOpportunities = useCallback(async () => {
    setSpotOpportunities((current) => setPending(current));
    try {
      const job = await startSpotOpportunityScan(spotScannerFilters);
      setSpotScanJob(job);
      setSpotOpportunities((current) => ({
        data: job.scan ?? current.data,
        loading: !job.scan && current.data === null,
        refreshing: !job.scan && current.data !== null,
        error: null,
      }));
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh Spot paper scanner.';
      setSpotOpportunities((current) => ({
        ...current,
        data: current.data,
        loading: false,
        refreshing: false,
        error: message,
      }));
    }
  }, [spotScannerFilters]);

  const cancelSpotScan = useCallback(async () => {
    if (!spotScanJob || isTerminalSpotScanJob(spotScanJob)) {
      return;
    }
    try {
      const job = await cancelSpotOpportunityScanJob(spotScanJob.scan_id);
      setSpotScanJob(job);
      setSpotOpportunities((current) => ({
        data: job.scan ?? current.data,
        loading: false,
        refreshing: false,
        error: job.status === 'cancelled' ? null : current.error,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to cancel Spot paper scanner.';
      setSpotOpportunities((current) => ({
        ...current,
        loading: false,
        refreshing: false,
        error: message,
      }));
    }
  }, [spotScanJob]);

  const refreshFuturesOpportunities = useCallback(async () => {
    setFuturesOpportunities((current) => setPending(current));
    try {
      const job = await startFuturesOpportunityScan(futuresScannerFilters);
      setFuturesScanJob(job);
      setFuturesOpportunities((current) => ({
        data: job.scan ?? current.data,
        loading: !job.scan && current.data === null,
        refreshing: !job.scan && current.data !== null,
        error: null,
      }));
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = futuresScannerErrorMessage(error);
      setFuturesOpportunities((current) => ({
        ...current,
        data: current.data,
        loading: false,
        refreshing: false,
        error: message,
      }));
    }
  }, [futuresScannerFilters]);

  const cancelFuturesScan = useCallback(async () => {
    if (!futuresScanJob || isTerminalFuturesScanJob(futuresScanJob)) {
      return;
    }
    try {
      const job = await cancelFuturesOpportunityScanJob(futuresScanJob.scan_id);
      setFuturesScanJob(job);
      setFuturesOpportunities((current) => ({
        data: job.scan ?? current.data,
        loading: false,
        refreshing: false,
        error: job.status === 'cancelled' ? null : current.error,
      }));
    } catch (error) {
      const message = futuresScannerErrorMessage(error);
      setFuturesOpportunities((current) => ({
        ...current,
        loading: false,
        refreshing: false,
        error: message,
      }));
    }
  }, [futuresScanJob]);

  const refreshFuturesLivePrices = useCallback(async (symbols: string[]) => {
    if (symbols.length === 0) {
      setFuturesLivePrices({ data: null, loading: false, refreshing: false, error: null });
      return;
    }
    setFuturesLivePrices((current) => setPending(current));
    try {
      const heartbeat = await getFuturesLivePrices(symbols);
      setFuturesLivePrices({ data: heartbeat, loading: false, refreshing: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh futures scanner heartbeat.';
      setFuturesLivePrices((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const refreshScannerValidation = useCallback(async () => {
    setScannerValidation((current) => setPending(current));
    try {
      const report = await getScannerValidationReport();
      setScannerValidation({ data: report, loading: false, refreshing: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh scanner validation report.';
      setScannerValidation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const refreshPostSignalPerformance = useCallback(async (symbol?: string) => {
    setPostSignalPerformance((current) => setPending(current));
    setPostSignalHistory((current) => setPending(current));
    try {
      const [summary, history] = await Promise.all([
        getPostSignalPerformanceSummary('15m'),
        getPostSignalHistory(symbol, 10),
      ]);
      setPostSignalPerformance({ data: summary, loading: false, refreshing: false, error: null });
      setPostSignalHistory({ data: history, loading: false, refreshing: false, error: null });
      if (!postSignalDetail.data && history.items[0]) {
        const detail = await getPostSignalDetail(history.items[0].id);
        setPostSignalDetail({ data: detail, loading: false, refreshing: false, error: null });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh post-signal performance.';
      setPostSignalPerformance((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      setPostSignalHistory((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, [postSignalDetail.data]);

  const refreshWorkspace = useCallback(async (
    symbol: string,
    options: WorkspaceRefreshOptions = {},
  ) => {
    const includeSignal = options.includeSignal ?? true;
    const includeAutoTrade = options.includeAutoTrade ?? false;
    const requestedSymbol = symbol.trim().toUpperCase();
    const selectedMarketForRefresh = selectedMarketRef.current;
    const useFuturesMarket = selectedMarketForRefresh === 'futures';
    workspaceRefreshControllerRef.current?.abort();
    const controller = new AbortController();
    workspaceRefreshControllerRef.current = controller;
    const refreshSequence = workspaceRefreshSequenceRef.current + 1;
    workspaceRefreshSequenceRef.current = refreshSequence;
    const fastOptions = { signal: controller.signal };
    const advancedOptions = { signal: controller.signal };
    const isCurrentRefresh = () => (
      workspaceRefreshSequenceRef.current === refreshSequence
      && !controller.signal.aborted
      && (requestedSymbol.length === 0 || selectedSymbolRef.current === requestedSymbol)
    );

    setAdvancedDataWarning(null);
    setHealth((current) => setPending(current));
    setBotStatus((current) => setPending(current));
    if (includeSignal) {
      setWorkstation((current) => setPending(current));
      setCandles((current) => setPending(current));
      setBackfillStatus((current) => setPending(current));
      setTechnicalAnalysis((current) => setPending(current));
      setRegimeAnalysis((current) => setPending(current));
      setFusionSignal((current) => setPending(current));
      setTradingAssistant((current) => setPending(current));
      setTradeEligibility((current) => setPending(current));
      setAiSignal((current) => setPending(current));
      setAiHistory((current) => setPending(current));
      setAiEvaluation((current) => setPending(current));
      setMarketSentiment((current) => setPending(current));
      setSymbolSentiment((current) => setPending(current));
      setPatternAnalysis((current) => setPending(current));
    }
    if (includeAutoTrade) {
      setPerformanceAnalytics((current) => setPending(current));
      setTradeQualityAnalytics((current) => setPending(current));
      setPaperTradeReview((current) => setPending(current));
      setProfileCalibration((current) => setPending(current));
      setProfileCalibrationComparison((current) => setPending(current));
      setSignalValidation((current) => setPending(current));
      setEdgeReport((current) => setPending(current));
      setModuleAttribution((current) => setPending(current));
      setSimilarSetups((current) => setPending(current));
      setTradeEligibility((current) => setPending(current));
      setAdaptiveRecommendations((current) => setPending(current));
    }

    try {
      const [healthResult, botStatusResult] = await Promise.allSettled([
        getHealth(fastOptions),
        getBotStatus(fastOptions),
      ]);
      if (!isCurrentRefresh()) {
        return;
      }
      if (healthResult.status === 'fulfilled') {
        setHealth({ data: healthResult.value, loading: false, refreshing: false, error: null });
      } else if (!isCanceledRequest(healthResult.reason)) {
        setHealth((current) => ({
          ...current,
          loading: false,
          refreshing: false,
          error: errorMessage(healthResult.reason, 'Unable to refresh backend health.'),
        }));
      }
      const botStatusData = botStatusResult.status === 'fulfilled' ? botStatusResult.value : null;
      if (botStatusData) {
        setBotStatus({ data: botStatusData, loading: false, refreshing: false, error: null });
      } else if (botStatusResult.status === 'rejected' && !isCanceledRequest(botStatusResult.reason)) {
        setBotStatus((current) => ({
          ...current,
          loading: false,
          refreshing: false,
          error: errorMessage(botStatusResult.reason, 'Unable to refresh paper runtime status.'),
        }));
      }
      const resolvedSymbol = requestedSymbol;
      if (botStatusData && botStatusData.state !== 'stopped') {
        setSelectedTradingProfile(botStatusData.trading_profile);
      }

      if (includeSignal) {
        const criticalSignalData = await Promise.allSettled([
          resolvedSymbol && !useFuturesMarket ? getWorkstation(resolvedSymbol, fastOptions) : Promise.resolve<WorkstationResponse | null>(null),
          resolvedSymbol ? getCandles(resolvedSymbol, selectedChartTimeframe, 120, fastOptions, selectedMarketForRefresh) : Promise.resolve<CandleHistoryResponse | null>(null),
          resolvedSymbol ? getBackfillStatus(resolvedSymbol, fastOptions, selectedMarketForRefresh) : Promise.resolve<BackfillStatusResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getTechnicalAnalysis(resolvedSymbol, fastOptions) : Promise.resolve<TechnicalAnalysisResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getRegimeAnalysis(resolvedSymbol, selectedPatternHorizon, fastOptions) : Promise.resolve<RegimeAnalysisResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getFusionSignal(resolvedSymbol, fastOptions) : Promise.resolve<FusionSignalResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getTradingAssistant(resolvedSymbol, fastOptions) : Promise.resolve<TradingAssistantResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getTradeEligibility(resolvedSymbol, undefined, fastOptions) : Promise.resolve<TradeEligibilityResponse | null>(null),
        ]);
        if (!isCurrentRefresh()) {
          return;
        }
        const workstationResult = criticalSignalData[0] as PromiseSettledResult<WorkstationResponse | null>;
        const candleResult = criticalSignalData[1] as PromiseSettledResult<CandleHistoryResponse | null>;
        const backfillResult = criticalSignalData[2] as PromiseSettledResult<BackfillStatusResponse | null>;
        const technicalResult = criticalSignalData[3] as PromiseSettledResult<TechnicalAnalysisResponse | null>;
        const regimeResult = criticalSignalData[4] as PromiseSettledResult<RegimeAnalysisResponse | null>;
        const fusionResult = criticalSignalData[5] as PromiseSettledResult<FusionSignalResponse | null>;
        const assistantResult = criticalSignalData[6] as PromiseSettledResult<TradingAssistantResponse | null>;
        const eligibilityResult = criticalSignalData[7] as PromiseSettledResult<TradeEligibilityResponse | null>;
        setWorkstation(workstationResult.status === 'fulfilled'
          ? { data: workstationResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(workstationResult.reason, 'Unable to refresh workstation state.') });
        setCandles(candleResult.status === 'fulfilled'
          ? { data: candleResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(candleResult.reason, 'Unable to refresh chart candles.') });
        setBackfillStatus(backfillResult.status === 'fulfilled'
          ? { data: backfillResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(backfillResult.reason, 'Unable to refresh backfill status.') });
        setTechnicalAnalysis(technicalResult.status === 'fulfilled'
          ? { data: technicalResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(technicalResult.reason, 'Unable to refresh technical analysis.') });
        setRegimeAnalysis(regimeResult.status === 'fulfilled'
          ? { data: regimeResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(regimeResult.reason, 'Unable to refresh regime analysis.') });
        setFusionSignal(fusionResult.status === 'fulfilled'
          ? { data: fusionResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(fusionResult.reason, 'Unable to refresh final signal.') });
        setTradingAssistant(assistantResult.status === 'fulfilled'
          ? { data: assistantResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(assistantResult.reason, 'Unable to refresh trading assistant.') });
        setTradeEligibility(eligibilityResult.status === 'fulfilled'
          ? { data: eligibilityResult.value, loading: false, refreshing: false, error: null }
          : { data: null, loading: false, refreshing: false, error: errorMessage(eligibilityResult.reason, 'Unable to refresh trade eligibility.') });
        setLastUpdatedAt(new Date());

        await delay(ADVANCED_LOAD_DELAY_MS, controller.signal);
        if (!isCurrentRefresh()) {
          return;
        }
        const advancedSignalData = await Promise.allSettled([
          resolvedSymbol && !useFuturesMarket ? getAISignal(resolvedSymbol, advancedOptions) : Promise.resolve<AISignalSummary | null>(null),
          resolvedSymbol && !useFuturesMarket
            ? getAISignalHistory(resolvedSymbol, { limit: AI_HISTORY_PAGE_SIZE, offset: aiHistoryOffset }, advancedOptions)
            : Promise.resolve<AISignalHistoryResponse>(INITIAL_AI_HISTORY),
          resolvedSymbol && !useFuturesMarket ? getAISignalEvaluation(resolvedSymbol, advancedOptions) : Promise.resolve<AIOutcomeEvaluationResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getMarketSentiment(resolvedSymbol, advancedOptions) : Promise.resolve<MarketSentimentResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getSymbolSentiment(resolvedSymbol, advancedOptions) : Promise.resolve<SymbolSentimentResponse | null>(null),
          resolvedSymbol && !useFuturesMarket ? getPatternAnalysis(resolvedSymbol, selectedPatternHorizon, advancedOptions) : Promise.resolve<PatternAnalysisResponse | null>(null),
        ]);
        if (!isCurrentRefresh()) {
          return;
        }
        let advancedHadIssue = false;
        const aiSignalResult = advancedSignalData[0] as PromiseSettledResult<AISignalSummary | null>;
        const aiHistoryResult = advancedSignalData[1] as PromiseSettledResult<AISignalHistoryResponse>;
        const aiEvaluationResult = advancedSignalData[2] as PromiseSettledResult<AIOutcomeEvaluationResponse | null>;
        const marketSentimentResult = advancedSignalData[3] as PromiseSettledResult<MarketSentimentResponse | null>;
        const symbolSentimentResult = advancedSignalData[4] as PromiseSettledResult<SymbolSentimentResponse | null>;
        const patternResult = advancedSignalData[5] as PromiseSettledResult<PatternAnalysisResponse | null>;
        advancedHadIssue = advancedHadIssue || aiSignalResult.status === 'rejected';
        advancedHadIssue = advancedHadIssue || aiHistoryResult.status === 'rejected';
        advancedHadIssue = advancedHadIssue || aiEvaluationResult.status === 'rejected';
        advancedHadIssue = advancedHadIssue || marketSentimentResult.status === 'rejected';
        advancedHadIssue = advancedHadIssue || symbolSentimentResult.status === 'rejected';
        advancedHadIssue = advancedHadIssue || patternResult.status === 'rejected';
        setAiSignal(aiSignalResult.status === 'fulfilled'
          ? { data: aiSignalResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setAiHistory(aiHistoryResult.status === 'fulfilled'
          ? { data: aiHistoryResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setAiEvaluation(aiEvaluationResult.status === 'fulfilled'
          ? { data: aiEvaluationResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setMarketSentiment(marketSentimentResult.status === 'fulfilled'
          ? { data: marketSentimentResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setSymbolSentiment(symbolSentimentResult.status === 'fulfilled'
          ? { data: symbolSentimentResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setPatternAnalysis(patternResult.status === 'fulfilled'
          ? { data: patternResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        if (advancedHadIssue) {
          setAdvancedDataWarning(ADVANCED_DATA_WARNING);
        }
      }
      if (includeAutoTrade && !useFuturesMarket) {
        const autoTradeData = await Promise.allSettled([
          resolvedSymbol ? getPerformanceAnalytics(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<PerformanceAnalyticsResponse | null>(null),
          resolvedSymbol ? getTradeQualityAnalytics(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<TradeQualityResponse | null>(null),
          resolvedSymbol ? getPaperTradeReview(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<PaperTradeReviewResponse | null>(null),
          resolvedSymbol
            ? getProfileCalibration(resolvedSymbol, { profile: selectedTradingProfile }, advancedOptions)
            : Promise.resolve<ProfileCalibrationResponse | null>(null),
          resolvedSymbol
            ? getProfileCalibrationComparison(resolvedSymbol, selectedTradingProfile, undefined, advancedOptions)
            : Promise.resolve<ProfileCalibrationComparisonResponse | null>(null),
          resolvedSymbol ? getSignalValidation(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<SignalValidationResponse | null>(null),
          resolvedSymbol ? getEdgeReport(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<EdgeReportResponse | null>(null),
          resolvedSymbol ? getModuleAttribution(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<ModuleAttributionResponse | null>(null),
          resolvedSymbol ? getSimilarSetups(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<SimilarSetupResponse | null>(null),
          resolvedSymbol ? getAdaptiveRecommendations(resolvedSymbol, undefined, advancedOptions) : Promise.resolve<AdaptiveRecommendationResponse | null>(null),
        ]);
        if (!isCurrentRefresh()) {
          return;
        }
        const performanceResult = autoTradeData[0] as PromiseSettledResult<PerformanceAnalyticsResponse | null>;
        const tradeQualityResult = autoTradeData[1] as PromiseSettledResult<TradeQualityResponse | null>;
        const paperReviewResult = autoTradeData[2] as PromiseSettledResult<PaperTradeReviewResponse | null>;
        const profileCalibrationResult = autoTradeData[3] as PromiseSettledResult<ProfileCalibrationResponse | null>;
        const profileComparisonResult = autoTradeData[4] as PromiseSettledResult<ProfileCalibrationComparisonResponse | null>;
        const signalValidationResult = autoTradeData[5] as PromiseSettledResult<SignalValidationResponse | null>;
        const edgeReportResult = autoTradeData[6] as PromiseSettledResult<EdgeReportResponse | null>;
        const moduleAttributionResult = autoTradeData[7] as PromiseSettledResult<ModuleAttributionResponse | null>;
        const similarSetupsResult = autoTradeData[8] as PromiseSettledResult<SimilarSetupResponse | null>;
        const adaptiveResult = autoTradeData[9] as PromiseSettledResult<AdaptiveRecommendationResponse | null>;
        const autoHadIssue = autoTradeData.some((result) => result.status === 'rejected');
        setPerformanceAnalytics(performanceResult.status === 'fulfilled'
          ? { data: performanceResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setTradeQualityAnalytics(tradeQualityResult.status === 'fulfilled'
          ? { data: tradeQualityResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setPaperTradeReview(paperReviewResult.status === 'fulfilled'
          ? { data: paperReviewResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setProfileCalibration(profileCalibrationResult.status === 'fulfilled'
          ? { data: profileCalibrationResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setProfileCalibrationComparison(profileComparisonResult.status === 'fulfilled'
          ? { data: profileComparisonResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setSignalValidation(signalValidationResult.status === 'fulfilled'
          ? { data: signalValidationResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setEdgeReport(edgeReportResult.status === 'fulfilled'
          ? { data: edgeReportResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setModuleAttribution(moduleAttributionResult.status === 'fulfilled'
          ? { data: moduleAttributionResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setSimilarSetups(similarSetupsResult.status === 'fulfilled'
          ? { data: similarSetupsResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        setAdaptiveRecommendations(adaptiveResult.status === 'fulfilled'
          ? { data: adaptiveResult.value, loading: false, refreshing: false, error: null }
          : (current) => stopSoftLoading(current));
        if (autoHadIssue) {
          setAdvancedDataWarning(ADVANCED_DATA_WARNING);
        }
      }
      setLastUpdatedAt(new Date());
    } catch (error) {
      if (controller.signal.aborted || isCanceledRequest(error)) {
        return;
      }
      const message = error instanceof Error ? error.message : 'Unable to refresh workstation state.';
      setHealth((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      setBotStatus((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      if (includeSignal && symbol.trim().length > 0) {
        setWorkstation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiSignal((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiHistory((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAiEvaluation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setCandles((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setBackfillStatus((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setTechnicalAnalysis((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setMarketSentiment((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setSymbolSentiment((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setPatternAnalysis((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setRegimeAnalysis((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setFusionSignal((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setTradingAssistant((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setTradeEligibility((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      }
      if (includeAutoTrade && symbol.trim().length > 0) {
        setPerformanceAnalytics((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setTradeQualityAnalytics((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setPaperTradeReview((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setProfileCalibration((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setProfileCalibrationComparison((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setSignalValidation((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setEdgeReport((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setModuleAttribution((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setSimilarSetups((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setTradeEligibility((current) => ({ ...current, loading: false, refreshing: false, error: message }));
        setAdaptiveRecommendations((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      }
    }
  }, [aiHistoryOffset, selectedChartTimeframe, selectedPatternHorizon, selectedTradingProfile]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadSymbols(symbolSearch);
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [loadSymbols, symbolSearch]);

  useEffect(() => {
    selectedSymbolRef.current = selectedSymbol;
    selectedMarketRef.current = selectedMarket;
    workspaceRefreshControllerRef.current?.abort();
    backfillControllerRef.current?.abort();
    const timeoutId = window.setTimeout(() => {
      setDebouncedSelectedSymbol(selectedSymbol);
    }, SYMBOL_SWITCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [selectedMarket, selectedSymbol]);

  useEffect(() => () => {
    workspaceRefreshControllerRef.current?.abort();
    backfillControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    void refreshWorkspace(debouncedSelectedSymbol, {
      includeSignal: true,
      includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab),
    });
  }, [debouncedSelectedSymbol, refreshWorkspace, selectedMarket, tab]);

  useEffect(() => {
    void refreshOpportunities();
  }, [refreshOpportunities]);

  useEffect(() => {
    void refreshSpotOpportunities();
  }, [refreshSpotOpportunities]);

  useEffect(() => {
    void refreshFuturesOpportunities();
  }, [refreshFuturesOpportunities]);

  useEffect(() => {
    if (!spotScanJob || isTerminalSpotScanJob(spotScanJob)) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const job = await getSpotOpportunityScanJob(spotScanJob.scan_id);
        if (cancelled) {
          return;
        }
        setSpotScanJob(job);
        if (job.scan) {
          setSpotOpportunities({
            data: job.scan,
            loading: false,
            refreshing: !isTerminalSpotScanJob(job),
            error: null,
          });
          if (job.status === 'completed') {
            setLastUpdatedAt(new Date());
          }
        } else if (job.status === 'failed') {
          setSpotOpportunities((current) => ({
            ...current,
            loading: false,
            refreshing: false,
            error: 'Spot scanner failed. Last successful results are still shown.',
          }));
        }
        if (job.status === 'cancelled') {
          setSpotOpportunities((current) => ({
            ...current,
            loading: false,
            refreshing: false,
            error: null,
          }));
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : 'Unable to poll Spot paper scanner.';
        setSpotOpportunities((current) => ({
          ...current,
          loading: false,
          refreshing: false,
          error: message,
        }));
      }
    };
    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [spotScanJob?.scan_id, spotScanJob?.status]);

  useEffect(() => {
    if (!futuresScanJob || isTerminalFuturesScanJob(futuresScanJob)) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const job = await getFuturesOpportunityScanJob(futuresScanJob.scan_id);
        if (cancelled) {
          return;
        }
        setFuturesScanJob(job);
        if (job.scan) {
          setFuturesOpportunities({
            data: job.scan,
            loading: false,
            refreshing: !isTerminalFuturesScanJob(job),
            error: null,
          });
          if (job.status === 'completed') {
            setLastUpdatedAt(new Date());
          }
        } else if (job.status === 'failed') {
          setFuturesOpportunities((current) => ({
            ...current,
            loading: false,
            refreshing: false,
            error: 'Scanner failed. Last successful results are still shown.',
          }));
        }
        if (job.status === 'cancelled') {
          setFuturesOpportunities((current) => ({
            ...current,
            loading: false,
            refreshing: false,
            error: null,
          }));
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = futuresScannerErrorMessage(error);
        setFuturesOpportunities((current) => ({
          ...current,
          loading: false,
          refreshing: false,
          error: message,
        }));
      }
    };
    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [futuresScanJob?.scan_id, futuresScanJob?.status]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setHeartbeatNow(new Date());
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void updateFuturesLiveSubscriptions(futuresHeartbeatSymbols)
        .then((response) => {
          setFuturesLiveSubscriptionWarning(response.warning);
        })
        .catch((error) => {
          const message = error instanceof Error
            ? error.message
            : 'Unable to update futures scanner WebSocket subscriptions.';
          setFuturesLiveSubscriptionWarning(message);
        });
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [futuresHeartbeatSymbols]);

  useEffect(() => {
    void refreshFuturesLivePrices(futuresHeartbeatSymbols);
    if (futuresHeartbeatSymbols.length === 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refreshFuturesLivePrices(futuresHeartbeatSymbols);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [futuresHeartbeatSymbols, refreshFuturesLivePrices]);

  useEffect(() => {
    if (futuresAutoRescanMinutes === 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refreshFuturesOpportunities();
    }, futuresAutoRescanMinutes * 60 * 1000);
    return () => window.clearInterval(intervalId);
  }, [futuresAutoRescanMinutes, refreshFuturesOpportunities]);

  useEffect(() => {
    void refreshScannerValidation();
  }, [refreshScannerValidation]);

  useEffect(() => {
    if (tab !== 'validate') {
      return;
    }
    void refreshPostSignalPerformance(debouncedSelectedSymbol);
  }, [debouncedSelectedSymbol, refreshPostSignalPerformance, tab]);

  useEffect(() => {
    const symbol = debouncedSelectedSymbol.trim();
    if (!symbol) {
      return;
    }
    const market = selectedMarketRef.current;
    backfillControllerRef.current?.abort();
    const controller = new AbortController();
    backfillControllerRef.current = controller;
    setBackfillStatus((current) => setPending(current));
    void triggerBackfill(symbol, { signal: controller.signal }, market)
      .then((status) => {
        if (
          controller.signal.aborted
          || selectedSymbolRef.current !== symbol.toUpperCase()
          || selectedMarketRef.current !== market
        ) {
          return;
        }
        setBackfillStatus({ data: status, loading: false, refreshing: false, error: null });
        setLastUpdatedAt(new Date());
        if (status.status === 'ready' || status.status === 'partial') {
          void refreshWorkspace(symbol, {
            includeSignal: true,
            includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab),
          });
        }
      })
      .catch((error) => {
        if (controller.signal.aborted || isCanceledRequest(error)) {
          return;
        }
        const message = error instanceof Error ? error.message : 'Unable to start historical backfill.';
        setBackfillStatus((current) => ({ ...current, loading: false, refreshing: false, error: message }));
      });
    return () => controller.abort();
  }, [debouncedSelectedSymbol, refreshWorkspace, selectedMarket, tab]);

  useEffect(() => {
    const symbol = debouncedSelectedSymbol.trim();
    const status = backfillStatus.data?.status;
    if (!symbol || !status || !['loading', 'not_started'].includes(status)) {
      return undefined;
    }
    const market = selectedMarketRef.current;
    let cancelled = false;
    const intervalId = window.setInterval(() => {
      void getBackfillStatus(symbol, undefined, market)
        .then((nextStatus) => {
          if (
            cancelled
            || selectedSymbolRef.current !== symbol.toUpperCase()
            || selectedMarketRef.current !== market
          ) {
            return;
          }
          setBackfillStatus({ data: nextStatus, loading: false, refreshing: nextStatus.status === 'loading', error: null });
          if (nextStatus.status === 'ready' || nextStatus.status === 'partial') {
            window.clearInterval(intervalId);
            void refreshWorkspace(symbol, {
              includeSignal: true,
              includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab),
            });
          }
          if (nextStatus.status === 'failed') {
            window.clearInterval(intervalId);
          }
        })
        .catch((error) => {
          if (cancelled || isCanceledRequest(error)) {
            return;
          }
          const message = error instanceof Error ? error.message : 'Unable to refresh historical backfill status.';
          setBackfillStatus((current) => ({ ...current, loading: false, refreshing: false, error: message }));
          window.clearInterval(intervalId);
        });
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [backfillStatus.data?.status, debouncedSelectedSymbol, refreshWorkspace, selectedMarket, tab]);

  useEffect(() => {
    if (autoRefreshSeconds === 0 || selectedSymbol.trim().length === 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refreshWorkspace(selectedSymbol, { includeSignal: true, includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab) });
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshSeconds, refreshWorkspace, selectedSymbol, tab]);

  const handleSymbolSearchChange = useCallback((value: string) => {
    setSymbolSearch(value);
    if (value.trim().toUpperCase() !== selectedSymbol) {
      workspaceRefreshControllerRef.current?.abort();
      backfillControllerRef.current?.abort();
      selectedSymbolRef.current = '';
      selectedMarketRef.current = 'spot';
      setSelectedSymbol('');
      setSelectedMarket('spot');
      setSelectedFuturesSimulation(null);
      setFuturesSimulationStopLoss('');
      setFuturesSimulationTakeProfit('');
    }
    setBotActionError(null);
    setBotActionMessage(null);
  }, [selectedSymbol]);

  const handleSelectSymbol = useCallback((
    symbol: string,
    market: SelectedMarket = 'spot',
    futuresDraft: FuturesSimulationDraft | null = null,
  ) => {
    const normalizedSymbol = symbol.trim().toUpperCase();
    workspaceRefreshControllerRef.current?.abort();
    backfillControllerRef.current?.abort();
    selectedSymbolRef.current = normalizedSymbol;
    selectedMarketRef.current = market;
    setAiHistoryOffset(0);
    setSelectedSymbol(normalizedSymbol);
    setSelectedMarket(market);
    setSelectedFuturesSimulation(futuresDraft);
    setFuturesSimulationStopLoss(futuresDraft?.stopLoss ?? '');
    setFuturesSimulationTakeProfit(futuresDraft?.takeProfit ?? '');
    setSymbolSearch(normalizedSymbol);
    setAdvancedDataWarning(null);
    setBotActionError(null);
    setBotActionMessage(null);
    setWorkstation({ data: null, loading: true, refreshing: false, error: null });
    setAiSignal({ data: null, loading: true, refreshing: false, error: null });
    setAiHistory({ data: INITIAL_AI_HISTORY, loading: true, refreshing: false, error: null });
    setAiEvaluation({ data: null, loading: true, refreshing: false, error: null });
    setCandles({ data: null, loading: true, refreshing: false, error: null });
    setBackfillStatus({ data: null, loading: true, refreshing: false, error: null });
    setTechnicalAnalysis({ data: null, loading: true, refreshing: false, error: null });
    setMarketSentiment({ data: null, loading: true, refreshing: false, error: null });
    setSymbolSentiment({ data: null, loading: true, refreshing: false, error: null });
    setPatternAnalysis({ data: null, loading: true, refreshing: false, error: null });
    setRegimeAnalysis({ data: null, loading: true, refreshing: false, error: null });
    setFusionSignal({ data: null, loading: true, refreshing: false, error: null });
    setTradingAssistant({ data: null, loading: true, refreshing: false, error: null });
    setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
    setTradeQualityAnalytics({ data: null, loading: false, refreshing: false, error: null });
    setPaperTradeReview({ data: null, loading: false, refreshing: false, error: null });
    setProfileCalibration({ data: null, loading: false, refreshing: false, error: null });
    setProfileCalibrationComparison({ data: null, loading: false, refreshing: false, error: null });
    setSignalValidation({ data: null, loading: false, refreshing: false, error: null });
    setEdgeReport({ data: null, loading: false, refreshing: false, error: null });
    setModuleAttribution({ data: null, loading: false, refreshing: false, error: null });
    setSimilarSetups({ data: null, loading: false, refreshing: false, error: null });
    setTradeEligibility({ data: null, loading: true, refreshing: false, error: null });
    setAdaptiveRecommendations({ data: null, loading: false, refreshing: false, error: null });
  }, []);

  const handleClearSelection = useCallback(() => {
    workspaceRefreshControllerRef.current?.abort();
    backfillControllerRef.current?.abort();
    selectedSymbolRef.current = '';
    selectedMarketRef.current = 'spot';
    setAiHistoryOffset(0);
    setSelectedSymbol('');
    setSelectedMarket('spot');
    setSelectedFuturesSimulation(null);
    setFuturesSimulationStopLoss('');
    setFuturesSimulationTakeProfit('');
    setSymbolSearch('');
    setAdvancedDataWarning(null);
    setBotActionError(null);
    setBotActionMessage(null);
    setWorkstation({ data: null, loading: false, refreshing: false, error: null });
    setAiSignal({ data: null, loading: false, refreshing: false, error: null });
    setAiHistory({ data: INITIAL_AI_HISTORY, loading: false, refreshing: false, error: null });
    setAiEvaluation({ data: null, loading: false, refreshing: false, error: null });
    setCandles({ data: null, loading: false, refreshing: false, error: null });
    setBackfillStatus({ data: null, loading: false, refreshing: false, error: null });
    setTechnicalAnalysis({ data: null, loading: false, refreshing: false, error: null });
    setMarketSentiment({ data: null, loading: false, refreshing: false, error: null });
    setSymbolSentiment({ data: null, loading: false, refreshing: false, error: null });
    setPatternAnalysis({ data: null, loading: false, refreshing: false, error: null });
    setRegimeAnalysis({ data: null, loading: false, refreshing: false, error: null });
    setFusionSignal({ data: null, loading: false, refreshing: false, error: null });
    setTradingAssistant({ data: null, loading: false, refreshing: false, error: null });
    setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
    setTradeQualityAnalytics({ data: null, loading: false, refreshing: false, error: null });
    setPaperTradeReview({ data: null, loading: false, refreshing: false, error: null });
    setProfileCalibration({ data: null, loading: false, refreshing: false, error: null });
    setProfileCalibrationComparison({ data: null, loading: false, refreshing: false, error: null });
    setSignalValidation({ data: null, loading: false, refreshing: false, error: null });
    setEdgeReport({ data: null, loading: false, refreshing: false, error: null });
    setModuleAttribution({ data: null, loading: false, refreshing: false, error: null });
    setSimilarSetups({ data: null, loading: false, refreshing: false, error: null });
    setTradeEligibility({ data: null, loading: false, refreshing: false, error: null });
    setAdaptiveRecommendations({ data: null, loading: false, refreshing: false, error: null });
    setPostSignalPerformance({ data: null, loading: false, refreshing: false, error: null });
    setPostSignalHistory({ data: INITIAL_POST_SIGNAL_HISTORY, loading: false, refreshing: false, error: null });
    setPostSignalDetail({ data: null, loading: false, refreshing: false, error: null });
    setScannerValidationEvaluateMessage(null);
    setScannerValidationEvaluateError(null);
  }, []);

  const runBotAction = useCallback(async (action: () => Promise<BotStatusResponse>) => {
    setBotActionLoading(true);
    setBotActionError(null);
    setBotActionMessage(null);
    let refreshSymbol = selectedSymbol;
    try {
      const nextStatus = await action();
      setBotStatus({ data: nextStatus, loading: false, refreshing: false, error: null });
      setSelectedTradingProfile(nextStatus.trading_profile);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to update the paper bot.';
      setBotActionError(message);
      return;
    } finally {
      setBotActionLoading(false);
    }
    void refreshWorkspace(refreshSymbol, { includeSignal: true, includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab) });
  }, [refreshWorkspace, selectedSymbol, tab]);

  const runManualTradeAction = useCallback(async (action: () => Promise<ManualTradeResponse>) => {
    setBotActionLoading(true);
    setBotActionError(null);
    setBotActionMessage(null);
    try {
      const result = await action();
      setBotActionMessage(result.message);
      if (!result.current_position_open) {
        setWorkstation((current) => {
          if (!current.data || current.data.symbol !== result.symbol) {
            return current;
          }
          return {
            ...current,
            data: {
              ...current.data,
              current_position: null,
            },
          };
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to submit the manual paper trade.';
      setBotActionError(message);
      return;
    } finally {
      setBotActionLoading(false);
    }
    void refreshWorkspace(selectedSymbol, { includeSignal: true, includeAutoTrade: ['simulate', 'validate', 'advanced'].includes(tab) });
  }, [refreshWorkspace, selectedSymbol, tab]);

  const handleResetSession = useCallback(async () => {
    setBotActionLoading(true);
    setBotActionError(null);
    setBotActionMessage(null);
    try {
      const nextStatus = await resetBotSession();
      setAiHistoryOffset(0);
      setBotStatus({ data: nextStatus, loading: false, refreshing: false, error: null });
      setSelectedTradingProfile(nextStatus.trading_profile);
      setWorkstation({ data: null, loading: false, refreshing: false, error: null });
      setAiSignal({ data: null, loading: false, refreshing: false, error: null });
      setAiHistory({ data: INITIAL_AI_HISTORY, loading: false, refreshing: false, error: null });
      setAiEvaluation({ data: null, loading: false, refreshing: false, error: null });
      setCandles({ data: null, loading: false, refreshing: false, error: null });
      setBackfillStatus({ data: null, loading: false, refreshing: false, error: null });
      setTechnicalAnalysis({ data: null, loading: false, refreshing: false, error: null });
      setMarketSentiment({ data: null, loading: false, refreshing: false, error: null });
      setSymbolSentiment({ data: null, loading: false, refreshing: false, error: null });
      setPatternAnalysis({ data: null, loading: false, refreshing: false, error: null });
      setRegimeAnalysis({ data: null, loading: false, refreshing: false, error: null });
      setFusionSignal({ data: null, loading: false, refreshing: false, error: null });
      setTradingAssistant({ data: null, loading: false, refreshing: false, error: null });
      setPerformanceAnalytics({ data: null, loading: false, refreshing: false, error: null });
      setTradeQualityAnalytics({ data: null, loading: false, refreshing: false, error: null });
      setPaperTradeReview({ data: null, loading: false, refreshing: false, error: null });
      setProfileCalibration({ data: null, loading: false, refreshing: false, error: null });
      setProfileCalibrationComparison({ data: null, loading: false, refreshing: false, error: null });
      setSignalValidation({ data: null, loading: false, refreshing: false, error: null });
      setEdgeReport({ data: null, loading: false, refreshing: false, error: null });
      setModuleAttribution({ data: null, loading: false, refreshing: false, error: null });
      setSimilarSetups({ data: null, loading: false, refreshing: false, error: null });
      setTradeEligibility({ data: null, loading: false, refreshing: false, error: null });
      setAdaptiveRecommendations({ data: null, loading: false, refreshing: false, error: null });
      setPostSignalPerformance({ data: null, loading: false, refreshing: false, error: null });
      setPostSignalHistory({ data: INITIAL_POST_SIGNAL_HISTORY, loading: false, refreshing: false, error: null });
      setPostSignalDetail({ data: null, loading: false, refreshing: false, error: null });
      setLastUpdatedAt(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to reset the paper session.';
      setBotActionError(message);
    } finally {
      setBotActionLoading(false);
    }
  }, []);

  const effectiveWorkstation = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (workstation.data?.symbol === selectedSymbol) {
      return workstation.data;
    }
    return null;
  }, [selectedMarket, selectedSymbol, workstation.data]);
  const effectiveAiSignal = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (aiSignal.data?.symbol === selectedSymbol) {
      return aiSignal.data;
    }
    return null;
  }, [aiSignal.data, selectedMarket, selectedSymbol]);
  const effectiveFusionSignal = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (fusionSignal.data?.symbol === selectedSymbol) {
      return fusionSignal.data;
    }
    return null;
  }, [fusionSignal.data, selectedMarket, selectedSymbol]);
  const effectiveTradingAssistant = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (tradingAssistant.data?.symbol === selectedSymbol) {
      return tradingAssistant.data;
    }
    return null;
  }, [selectedMarket, selectedSymbol, tradingAssistant.data]);
  const effectiveTradeEligibility = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (tradeEligibility.data?.symbol === selectedSymbol) {
      return tradeEligibility.data;
    }
    return null;
  }, [selectedMarket, selectedSymbol, tradeEligibility.data]);
  const effectiveRegimeAnalysis = useMemo(() => {
    if (selectedMarket !== 'spot') {
      return null;
    }
    if (regimeAnalysis.data?.symbol === selectedSymbol) {
      return regimeAnalysis.data;
    }
    return null;
  }, [regimeAnalysis.data, selectedMarket, selectedSymbol]);

  const trendLabel = effectiveWorkstation?.trend_bias ?? (selectedMarket === 'futures' ? 'Using USD-M Futures scanner context.' : 'Start paper runtime to collect live market context.');
  const workstationDataState = effectiveWorkstation?.data_state ?? (selectedMarket === 'futures' ? 'waiting_for_history' : 'waiting_for_runtime');
  const workstationStatusMessage = effectiveWorkstation?.status_message ?? (
    selectedSymbol
      ? (selectedMarket === 'futures'
        ? `USD-M Futures analysis for ${selectedSymbol} uses futures candles and scanner simulation context.`
        : `Start or attach the live runtime for ${selectedSymbol} to populate symbol-scoped workstation data.`)
      : 'Select one symbol to populate the workstation.'
  );
  const signalExplanation = effectiveWorkstation?.explanation ?? (
    selectedMarket === 'futures'
      ? 'Futures scanner simulation is paper-only and does not require starting the Spot paper runtime.'
      : 'Select a symbol, then start or pause the live paper runtime to populate live signal state.'
  );
  const refreshLabel = autoRefreshSeconds === 0 ? 'Off' : `${autoRefreshSeconds}s`;
  const readiness = effectiveWorkstation?.trade_readiness ?? null;
  const derivedMidPrice = effectiveWorkstation?.feature?.mid_price ?? computeMidPrice(effectiveWorkstation);
  const derivedSpread = effectiveWorkstation?.feature?.bid_ask_spread ?? computeSpread(effectiveWorkstation);
  const derivedBookImbalance = effectiveWorkstation?.feature?.order_book_imbalance ?? computeBookImbalance(effectiveWorkstation);
  const liveFieldGap = describeLiveFieldGap(effectiveWorkstation);
  const handleAiHistoryPrevious = useCallback(() => {
    setAiHistoryOffset((current) => Math.max(current - AI_HISTORY_PAGE_SIZE, 0));
  }, []);

  const handleApplyProfileCalibration = useCallback(async (profile: TradingProfile, thresholds?: string[]) => {
    if (!selectedSymbol) {
      return;
    }
    setProfileApplyLoading(true);
    setBotActionError(null);
    setBotActionMessage(null);
    try {
      const result: ProfileCalibrationApplyResponse = await applyProfileCalibration(selectedSymbol, profile, thresholds);
      setBotActionMessage(result.status_message);
      await refreshWorkspace(selectedSymbol, { includeSignal: false, includeAutoTrade: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to apply the tuning recommendation.';
      setBotActionError(message);
    } finally {
      setProfileApplyLoading(false);
    }
  }, [refreshWorkspace, selectedSymbol]);

  const handleEvaluateScannerValidation = useCallback(async () => {
    setScannerValidationEvaluating(true);
    setScannerValidationEvaluateMessage(null);
    setScannerValidationEvaluateError(null);
    try {
      const result = await evaluateScannerValidation();
      setScannerValidationEvaluateMessage(result.message);
      await refreshScannerValidation();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to evaluate pending scanner results.';
      setScannerValidationEvaluateError(message);
    } finally {
      setScannerValidationEvaluating(false);
    }
  }, [refreshScannerValidation]);

  const handleSelectPostSignal = useCallback(async (signalId: string) => {
    setPostSignalDetail((current) => setPending(current));
    try {
      const detail = await getPostSignalDetail(signalId);
      setPostSignalDetail({ data: detail, loading: false, refreshing: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load signal outcome detail.';
      setPostSignalDetail((current) => ({ ...current, loading: false, refreshing: false, error: message }));
    }
  }, []);

  const handleAiHistoryNext = useCallback(() => {
    setAiHistoryOffset((current) => {
      const total = aiHistory.data.total;
      if (current + AI_HISTORY_PAGE_SIZE >= total) {
        return current;
      }
      return current + AI_HISTORY_PAGE_SIZE;
    });
  }, [aiHistory.data.total]);

  const assistantTabs: Array<[WorkstationTab, string, string]> = [
    ['discover', 'Discover', 'Market Scanner'],
    ['signal', 'Signal', 'Symbol Analysis'],
    ['simulate', 'Simulate', 'Paper Trading'],
    ['futures', 'Futures', 'Paper Long/Short'],
    ['validate', 'Validate', 'Signal Performance'],
    ['advanced', 'Advanced', 'Analytics & Insights'],
  ];
  const isDetailTab = ['simulate', 'futures', 'validate', 'advanced'].includes(tab);
  const refreshAll = () => {
    void refreshWorkspace(selectedSymbol, { includeSignal: true, includeAutoTrade: isDetailTab });
    void refreshOpportunities();
    void refreshFuturesOpportunities();
    void refreshFuturesLivePrices(futuresHeartbeatSymbols);
    if (tab === 'validate') {
      void refreshScannerValidation();
      void refreshPostSignalPerformance(selectedSymbol);
    }
  };

  return (
    <div className="min-h-screen overflow-x-hidden bg-appBg text-textPrimary">
      <TopNavigation
        tab={tab}
        tabs={assistantTabs}
        health={health.data}
        lastUpdatedAt={lastUpdatedAt}
        refreshLabel={refreshLabel}
        autoRefreshSeconds={autoRefreshSeconds}
        onTabChange={setTab}
        onRefresh={refreshAll}
        onAutoRefreshChange={setAutoRefreshSeconds}
      />

      <div
        className={classNames(
          'mx-auto grid max-w-[1880px] gap-4 px-4 py-4 sm:px-6 xl:px-6 2xl:px-8',
          leftSidebarCollapsed
            ? 'xl:grid-cols-[76px_minmax(0,1fr)_300px]'
            : 'xl:grid-cols-[260px_minmax(0,1fr)_300px]',
        )}
      >
        <LeftSidebar
          selectedSymbol={selectedSymbol}
          symbolSearch={symbolSearch}
          symbolResults={symbolResults.data}
          symbolsLoading={symbolResults.loading || symbolResults.refreshing}
          symbolsError={symbolResults.error}
          futuresScan={futuresOpportunities.data}
          livePrices={futuresLivePrices.data}
          marketSentiment={marketSentiment.data}
          technicalAnalysis={technicalAnalysis.data}
          collapsed={leftSidebarCollapsed}
          onSearchChange={handleSymbolSearchChange}
          onSelectSymbol={(symbol) => {
            handleSelectSymbol(symbol);
            setTab('signal');
          }}
          onClearSelection={handleClearSelection}
          onViewScanner={() => setTab('discover')}
          onToggleCollapse={() => setLeftSidebarCollapsed((current) => !current)}
        />

        <main className="min-w-0 space-y-4">
          <PremiumCard className="p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-textSecondary">
                <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1">Selected {selectedSymbol || '-'}</span>
                <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1">Market {selectedMarket.toUpperCase()}</span>
                <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1">Runtime {botStatus.data.state}{botStatus.data.symbol ? ` ${botStatus.data.symbol}` : ''}</span>
                <span className="rounded-md border border-borderSoft bg-panelBgSoft px-3 py-1">Sensitivity {selectedTradingProfile === 'aggressive' ? 'active' : selectedTradingProfile}</span>
                {selectedSymbol && (workstation.loading || tradingAssistant.loading || fusionSignal.loading) ? (
                  <span className="rounded-md border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-sky-100">Loading core signal</span>
                ) : null}
                {selectedSymbol && !workstation.loading && (aiSignal.loading || marketSentiment.loading || symbolSentiment.loading || patternAnalysis.loading) ? (
                  <span className="rounded-md border border-violet-400/25 bg-violet-400/10 px-3 py-1 text-violet-100">Advanced details updating</span>
                ) : null}
                {selectedSymbol && backfillStatus.data?.status === 'loading' ? (
                  <span className="rounded-md border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-sky-100">Fetching historical candles</span>
                ) : null}
                {selectedSymbol && backfillStatus.data?.status === 'ready' ? (
                  <span className="rounded-md border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-emerald-100">Backfill complete</span>
                ) : null}
                {selectedSymbol && backfillStatus.data?.status === 'failed' ? (
                  <span className="rounded-md border border-rose-400/25 bg-rose-400/10 px-3 py-1 text-rose-100">Backfill failed</span>
                ) : null}
                <span className="rounded-md border border-longGreen/25 bg-longGreen/10 px-3 py-1 text-emerald-100">Paper Mode</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="self-center text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Paper Trading Controls</span>
                <button type="button" disabled={!selectedSymbol || selectedMarket !== 'spot' || botActionLoading} onClick={() => void runBotAction(() => startBot(selectedSymbol, selectedTradingProfile))} className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">Start</button>
                <button type="button" disabled={botStatus.data.state === 'stopped' || botActionLoading} onClick={() => void runBotAction(() => (botStatus.data.state === 'paused' ? resumeBot() : pauseBot()))} className="rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-50">{botStatus.data.state === 'paused' ? 'Resume' : 'Pause'}</button>
                <button type="button" disabled={botStatus.data.state === 'stopped' || botActionLoading} onClick={() => void runBotAction(stopBot)} className="rounded-md border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs font-semibold text-rose-100 disabled:cursor-not-allowed disabled:opacity-50">Stop</button>
              </div>
            </div>
            {botActionMessage ? <p className="mt-2 text-xs text-emerald-300">{botActionMessage}</p> : null}
            {botActionError ? <p className="mt-2 text-xs text-rose-300">{botActionError}</p> : null}
          </PremiumCard>

          {advancedDataWarning ? (
            <div
              role="status"
              className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100"
            >
              <span className="font-semibold">{advancedDataWarning}</span>
              <span className="ml-2 text-amber-100/75">{ADVANCED_SOFT_MESSAGE}</span>
            </div>
          ) : null}

          {tab === 'discover' ? (
            <div className="space-y-5">
              <ErrorBoundary fallbackTitle="Spot paper scanner unavailable">
                <SpotPaperScannerSection
                  scan={spotOpportunities.data}
                  scanJob={spotScanJob}
                  loading={spotOpportunities.loading}
                  refreshing={spotOpportunities.refreshing}
                  error={spotOpportunities.error}
                  filters={spotScannerFilters}
                  onFiltersChange={setSpotScannerFilters}
                  onViewSignal={(symbol) => {
                    handleSelectSymbol(symbol, 'spot');
                    setTab('signal');
                  }}
                  onSimulate={(signal: SpotOpportunitySignalResponse) => {
                    handleSelectSymbol(signal.symbol, 'spot');
                    setTab('simulate');
                  }}
                  onRefresh={() => void refreshSpotOpportunities()}
                  onCancelScan={() => void cancelSpotScan()}
                />
              </ErrorBoundary>
              <ErrorBoundary fallbackTitle="Futures paper scanner unavailable">
                <FuturesPaperScannerSection
                  scan={futuresOpportunities.data}
                  scanJob={futuresScanJob}
                  loading={futuresOpportunities.loading}
                  refreshing={futuresOpportunities.refreshing}
                  error={futuresOpportunities.error}
                  livePrices={futuresLivePrices.data}
                  livePricesLoading={futuresLivePrices.loading || futuresLivePrices.refreshing}
                  livePricesError={futuresLivePrices.error ?? futuresLiveSubscriptionWarning}
                  heartbeatNow={heartbeatNow}
                  filters={futuresScannerFilters}
                  onFiltersChange={setFuturesScannerFilters}
                  autoRescanMinutes={futuresAutoRescanMinutes}
                  onAutoRescanChange={setFuturesAutoRescanMinutes}
                  selectedLeverage={selectedFuturesLeverage}
                  onSelectedLeverageChange={setSelectedFuturesLeverage}
                  onViewSignal={(symbol) => {
                    handleSelectSymbol(symbol);
                    setTab('signal');
                  }}
                  onSimulate={(signal, livePrice) => {
                    const draft = futuresSimulationDraftFromSignal(signal, livePrice);
                    handleSelectSymbol(signal.symbol, 'futures', draft);
                    setTab('simulate');
                  }}
                  onRefresh={() => void refreshFuturesOpportunities()}
                  onCancelScan={() => void cancelFuturesScan()}
                />
              </ErrorBoundary>
            </div>
          ) : null}

          {tab === 'signal' ? (
            <ErrorBoundary fallbackTitle="Signal workspace unavailable">
              <SignalWorkspace
                selectedSymbol={selectedSymbol}
                workstation={effectiveWorkstation}
                fusionSignal={effectiveFusionSignal}
                tradingAssistant={effectiveTradingAssistant}
                tradeEligibility={effectiveTradeEligibility}
                regimeAnalysis={effectiveRegimeAnalysis}
                technicalAnalysis={technicalAnalysis}
                similarSetups={similarSetups.data}
                candles={candles}
                selectedChartTimeframe={selectedChartTimeframe}
                signalAnalysisTab={signalAnalysisTab}
                loading={workstation.loading || fusionSignal.loading || tradingAssistant.loading}
                error={workstation.error ?? fusionSignal.error ?? tradingAssistant.error}
                onChartTimeframeChange={setSelectedChartTimeframe}
                onSignalAnalysisTabChange={setSignalAnalysisTab}
                onRefresh={() => void refreshWorkspace(selectedSymbol, { includeSignal: true, includeAutoTrade: false })}
                analysisProps={{
                  aiSignal,
                  aiHistory,
                  aiEvaluation,
                  patternAnalysis,
                  selectedPatternHorizon,
                  onSelectPatternHorizon: setSelectedPatternHorizon,
                  marketSentiment,
                  symbolSentiment,
                  tradingAssistant,
                  signalValidation,
                  edgeReport,
                  moduleAttribution,
                  loading: tradingAssistant.loading,
                  refreshing: tradingAssistant.refreshing,
                  errors: tradingAssistant.error,
                  workstationDataState,
                  workstationStatusMessage,
                  onAiHistoryPrevious: handleAiHistoryPrevious,
                  onAiHistoryNext: handleAiHistoryNext,
                }}
              />
              <AdvancedDetailsPro>
                <div className="grid gap-4">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><AIAdvisorySection symbol={selectedSymbol} signal={effectiveAiSignal} loading={aiSignal.loading} refreshing={aiSignal.refreshing} error={aiSignal.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><FusionSignalSection symbol={selectedSymbol} signal={effectiveFusionSignal} loading={fusionSignal.loading} refreshing={fusionSignal.refreshing} error={fusionSignal.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><TradeEligibilitySection symbol={selectedSymbol} eligibility={effectiveTradeEligibility} loading={tradeEligibility.loading} refreshing={tradeEligibility.refreshing} error={tradeEligibility.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><RegimeAnalysisSection symbol={selectedSymbol} analysis={effectiveRegimeAnalysis} loading={regimeAnalysis.loading} refreshing={regimeAnalysis.refreshing} error={regimeAnalysis.error} /></div>
                </div>
              </AdvancedDetailsPro>
            </ErrorBoundary>
          ) : null}

        {tab === 'simulate' ? (
          <div className="space-y-5">
            <SimulatePanel
              selectedSymbol={selectedSymbol}
              selectedMarket={selectedMarket}
              futuresDraft={selectedFuturesSimulation}
              futuresStopLoss={futuresSimulationStopLoss}
              futuresTakeProfit={futuresSimulationTakeProfit}
              workstation={effectiveWorkstation}
              tradingAssistant={effectiveTradingAssistant}
              fusionSignal={effectiveFusionSignal}
              leverage={selectedFuturesLeverage}
              onLeverageChange={setSelectedFuturesLeverage}
              onFuturesStopLossChange={setFuturesSimulationStopLoss}
              onFuturesTakeProfitChange={setFuturesSimulationTakeProfit}
              onFuturesReset={() => {
                setSelectedFuturesSimulation(null);
                setFuturesSimulationStopLoss('');
                setFuturesSimulationTakeProfit('');
              }}
              actionLoading={botActionLoading}
              actionError={botActionError}
              actionMessage={botActionMessage}
              onManualBuy={() => void runManualTradeAction(() => manualBuyMarket(selectedSymbol))}
              onManualClose={() => void runManualTradeAction(() => manualClosePosition(selectedSymbol))}
            />
            <AdvancedDetailsPro>
              <WhyNoTradePanel symbol={selectedSymbol} />
              <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                <TradeReadinessPanel symbol={selectedSymbol} readiness={readiness} />
              </div>
            </AdvancedDetailsPro>
          </div>
        ) : null}

        {tab === 'validate' ? (
          <div className="space-y-5">
            <ValidationSummary report={scannerValidation.data} signalValidation={signalValidation.data} similarSetups={similarSetups.data} />
            <PostSignalPerformancePanel
              summary={postSignalPerformance.data}
              history={postSignalHistory.data}
              detail={postSignalDetail.data}
              loading={postSignalPerformance.loading || postSignalHistory.loading}
              error={postSignalPerformance.error ?? postSignalHistory.error ?? postSignalDetail.error}
              onSelectSignal={handleSelectPostSignal}
            />
            <ErrorBoundary fallbackTitle="Validation details unavailable">
              <AdvancedDetailsPro
                action={scannerValidation.refreshing || signalValidation.refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
              >
                <div className="grid gap-4">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                    <ScannerValidationReportSection
                      report={scannerValidation.data}
                      loading={scannerValidation.loading}
                      refreshing={scannerValidation.refreshing}
                      error={scannerValidation.error}
                      evaluating={scannerValidationEvaluating}
                      evaluateMessage={scannerValidationEvaluateMessage}
                      evaluateError={scannerValidationEvaluateError}
                      onRefresh={() => void refreshScannerValidation()}
                      onEvaluate={() => void handleEvaluateScannerValidation()}
                    />
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                    <SignalValidationSection
                      symbol={selectedSymbol}
                      validation={signalValidation.data}
                      edgeReport={edgeReport.data}
                      moduleAttribution={moduleAttribution.data}
                      similarSetups={similarSetups.data}
                      loading={signalValidation.loading}
                      refreshing={signalValidation.refreshing || edgeReport.refreshing || moduleAttribution.refreshing || similarSetups.refreshing}
                      error={signalValidation.error ?? edgeReport.error ?? moduleAttribution.error ?? similarSetups.error}
                    />
                  </div>
                </div>
              </AdvancedDetailsPro>
            </ErrorBoundary>
          </div>
        ) : null}

        {tab === 'futures' ? (
          <ErrorBoundary fallbackTitle="Futures paper controls unavailable">
            <FuturesPaperTradingSection symbol={selectedSymbol} />
          </ErrorBoundary>
        ) : null}

        {tab === 'advanced' ? (
          <div className="space-y-5">
            <ErrorBoundary fallbackTitle="Advanced workspace unavailable">
              <AdvancedDetailsPro>
                <div className="grid gap-4">
                  <BotControlPanel
                    searchQuery={symbolSearch}
                    selectedSymbol={selectedSymbol}
                    hasValidSelection={selectedSymbol.length > 0}
                    tradingProfile={selectedTradingProfile}
                    onTradingProfileChange={setSelectedTradingProfile}
                    symbolResults={symbolResults.data}
                    symbolsLoading={symbolResults.loading || symbolResults.refreshing}
                    symbolsError={symbolResults.error}
                    chart={candles.data}
                    chartLoading={candles.loading || candles.refreshing}
                    chartError={candles.error}
                    chartTimeframe={selectedChartTimeframe}
                    onChartTimeframeChange={setSelectedChartTimeframe}
                    technicalAnalysis={technicalAnalysis.data}
                    status={botStatus.data}
                    actionLoading={botActionLoading}
                    actionError={botActionError ?? botStatus.error}
                    actionMessage={botActionMessage}
                    hasOpenPosition={Boolean(effectiveWorkstation?.current_position)}
                    onSearchChange={handleSymbolSearchChange}
                    onSelectSymbol={handleSelectSymbol}
                    onClearSelection={handleClearSelection}
                    onStart={() => void runBotAction(() => startBot(selectedSymbol, selectedTradingProfile))}
                    onStop={() => void runBotAction(stopBot)}
                    onPauseResume={() => void runBotAction(() => (botStatus.data.state === 'paused' ? resumeBot() : pauseBot()))}
                    onManualBuy={() => void runManualTradeAction(() => manualBuyMarket(selectedSymbol))}
                    onManualClose={() => void runManualTradeAction(() => manualClosePosition(selectedSymbol))}
                    onReset={() => void handleResetSession()}
                  />
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><TechnicalAnalysisSection symbol={selectedSymbol} analysis={technicalAnalysis.data} loading={technicalAnalysis.loading} refreshing={technicalAnalysis.refreshing} error={technicalAnalysis.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><PatternAnalysisSection symbol={selectedSymbol} selectedHorizon={selectedPatternHorizon} analysis={patternAnalysis.data} loading={patternAnalysis.loading} refreshing={patternAnalysis.refreshing} error={patternAnalysis.error} onSelectHorizon={setSelectedPatternHorizon} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><MarketSentimentSection symbol={selectedSymbol} sentiment={marketSentiment.data} loading={marketSentiment.loading} refreshing={marketSentiment.refreshing} error={marketSentiment.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><SymbolSentimentSection symbol={selectedSymbol} sentiment={symbolSentiment.data} loading={symbolSentiment.loading} refreshing={symbolSentiment.refreshing} error={symbolSentiment.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><AdaptiveRecommendationsSection symbol={selectedSymbol} recommendations={adaptiveRecommendations.data} loading={adaptiveRecommendations.loading} refreshing={adaptiveRecommendations.refreshing} error={adaptiveRecommendations.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><PerformanceAnalyticsSection symbol={selectedSymbol} analytics={performanceAnalytics.data} loading={performanceAnalytics.loading} refreshing={performanceAnalytics.refreshing} error={performanceAnalytics.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><TradeQualitySection symbol={selectedSymbol} analytics={tradeQualityAnalytics.data} loading={tradeQualityAnalytics.loading} refreshing={tradeQualityAnalytics.refreshing} error={tradeQualityAnalytics.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><PaperTradeReviewSection symbol={selectedSymbol} review={paperTradeReview.data} loading={paperTradeReview.loading} refreshing={paperTradeReview.refreshing} error={paperTradeReview.error} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><ProfileCalibrationSection symbol={selectedSymbol} calibration={profileCalibration.data} comparison={profileCalibrationComparison.data} loading={profileCalibration.loading} refreshing={profileCalibration.refreshing || profileCalibrationComparison.refreshing} error={profileCalibration.error ?? profileCalibrationComparison.error} actionLoading={profileApplyLoading} activeProfile={selectedTradingProfile} onApply={handleApplyProfileCalibration} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><OpportunityScannerSection opportunities={opportunities.data} loading={opportunities.loading} refreshing={opportunities.refreshing} error={opportunities.error} selectedSymbol={selectedSymbol} onSelectSymbol={handleSelectSymbol} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><AIHistorySection symbol={selectedSymbol} history={aiHistory.data.items} loading={aiHistory.loading} refreshing={aiHistory.refreshing} error={aiHistory.error} dataState={aiHistory.data.data_state} statusMessage={aiHistory.data.status_message} total={aiHistory.data.total} limit={aiHistory.data.limit} offset={aiHistory.data.offset} onPrevious={handleAiHistoryPrevious} onNext={handleAiHistoryNext} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><AIEvaluationCard symbol={selectedSymbol} evaluation={aiEvaluation.data} loading={aiEvaluation.loading} refreshing={aiEvaluation.refreshing} error={aiEvaluation.error} dataState={aiEvaluation.data?.data_state ?? workstationDataState} statusMessage={aiEvaluation.data?.status_message ?? workstationStatusMessage} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><PersistenceHealthCard persistence={effectiveWorkstation?.persistence ?? botStatus.data.persistence} /></div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><DiagnosticsPanel selectedSymbol={selectedSymbol} health={health.data} status={botStatus.data} workstation={effectiveWorkstation} backfillStatus={backfillStatus.data} latestSignalTimestamp={effectiveFusionSignal?.generated_at ?? effectiveAiSignal?.timestamp ?? effectiveWorkstation?.last_market_event ?? null} persistence={effectiveWorkstation?.persistence ?? botStatus.data.persistence} /></div>
                </div>
              </AdvancedDetailsPro>
            </ErrorBoundary>
          </div>
        ) : null}
        </main>

        <RightSidebar
          workstation={effectiveWorkstation}
          health={health.data}
          signalValidation={signalValidation.data}
          performance={performanceAnalytics.data}
          tradeQuality={tradeQualityAnalytics.data}
          persistence={effectiveWorkstation?.persistence ?? botStatus.data.persistence}
          onValidate={() => setTab('validate')}
          onAdvanced={() => setTab('advanced')}
        />
      </div>
    </div>
  );
}

export default App;
