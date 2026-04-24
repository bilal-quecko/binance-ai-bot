export type DecimalString = string;
export type RangePreset = '1D' | '7D' | '30D' | 'ALL';
export type AutoRefreshIntervalSeconds = 0 | 5 | 10 | 30;
export type WorkstationDataState = 'ready' | 'waiting_for_runtime' | 'waiting_for_history' | 'degraded_storage';
export type PatternHorizon = '1d' | '3d' | '7d' | '14d' | '30d';
export type ChartTimeframe = '1m' | '5m' | '15m' | '1h';
export type TradingProfile = 'conservative' | 'balanced' | 'aggressive';
export type PersistenceState =
  | 'healthy'
  | 'degraded_in_memory_only'
  | 'recovered_from_persistence'
  | 'unavailable';

export interface PersistenceHealthSummary {
  persistence_state: PersistenceState;
  persistence_message: string;
  persistence_last_ok_at: string | null;
  recovery_source: string | null;
}

export interface SpotSymbolItem {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  status: string;
}

export interface BotStatusResponse {
  state: 'stopped' | 'running' | 'paused' | 'error';
  mode: 'auto_paper' | 'paused' | 'stopped' | 'error';
  symbol: string | null;
  timeframe: string;
  paper_only: boolean;
  session_id: string | null;
  started_at: string | null;
  last_event_time: string | null;
  last_error: string | null;
  recovered_from_prior_session: boolean;
  broker_state_restored: boolean;
  recovery_message: string | null;
  trading_profile: TradingProfile;
  tuning_version_id: string | null;
  baseline_tuning_version_id: string | null;
  persistence: PersistenceHealthSummary;
}

export interface CandleSummary {
  timeframe: string;
  open_time: string;
  close_time: string;
  open: DecimalString;
  high: DecimalString;
  low: DecimalString;
  close: DecimalString;
  volume: DecimalString;
  is_closed: boolean;
}

export interface CandleHistoryResponse {
  symbol: string;
  timeframe: ChartTimeframe;
  source_timeframe: string;
  derived_from_lower_timeframe: boolean;
  data_state: WorkstationDataState;
  status_message: string | null;
  candles: CandleSummary[];
  current_price: DecimalString | null;
}

export interface TopOfBookSummary {
  bid_price: DecimalString;
  bid_quantity: DecimalString;
  ask_price: DecimalString;
  ask_quantity: DecimalString;
  event_time: string;
}

export interface FeatureSummary {
  regime: 'bullish' | 'bearish' | 'neutral' | null;
  ema_fast: DecimalString | null;
  ema_slow: DecimalString | null;
  atr: DecimalString | null;
  mid_price: DecimalString | null;
  bid_ask_spread: DecimalString | null;
  order_book_imbalance: DecimalString | null;
  timestamp: string | null;
}

export interface AISignalFeatureSummary {
  candle_count: number;
  close_price: DecimalString;
  volatility_pct: DecimalString | null;
  momentum: DecimalString | null;
  volume_change_pct: DecimalString | null;
  volume_spike_ratio: DecimalString | null;
  spread_ratio: DecimalString | null;
  microstructure_healthy: boolean;
  momentum_persistence: DecimalString | null;
  direction_flip_rate: DecimalString | null;
  structure_quality: DecimalString | null;
  recent_false_positive_rate_5m: DecimalString | null;
}

export interface AIHorizonSignalSummary {
  horizon: '5m' | '15m' | '1h';
  bias: 'bullish' | 'bearish' | 'sideways';
  confidence: number;
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit' | 'abstain';
  abstain: boolean;
  confirmation_needed: boolean;
  explanation: string;
}

export interface AISignalSummary {
  symbol: string;
  timestamp: string;
  bias: 'bullish' | 'bearish' | 'sideways';
  confidence: number;
  entry_signal: boolean;
  exit_signal: boolean;
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit' | 'abstain';
  regime: 'trending' | 'ranging' | 'choppy' | 'breakout_building' | 'reversal_risk' | 'high_volatility_unstable' | 'insufficient_data';
  noise_level: 'low' | 'moderate' | 'high' | 'extreme' | 'unknown';
  abstain: boolean;
  low_confidence: boolean;
  confirmation_needed: boolean;
  preferred_horizon: '5m' | '15m' | '1h' | null;
  weakening_factors: string[];
  explanation: string;
  horizons: AIHorizonSignalSummary[];
  features: AISignalFeatureSummary;
}

export interface TechnicalTimeframeSummary {
  timeframe: string;
  trend_direction: 'bullish' | 'bearish' | 'sideways';
  trend_strength: 'weak' | 'moderate' | 'strong';
}

export interface TechnicalAnalysisResponse {
  symbol: string;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  trend_direction: 'bullish' | 'bearish' | 'sideways' | null;
  trend_strength: 'weak' | 'moderate' | 'strong' | null;
  trend_strength_score: number | null;
  support_levels: DecimalString[];
  resistance_levels: DecimalString[];
  momentum_state: 'bullish' | 'bearish' | 'neutral' | 'overbought' | 'oversold' | 'unknown' | null;
  volatility_regime: 'low' | 'normal' | 'high' | 'unknown' | null;
  breakout_readiness: 'low' | 'medium' | 'high' | 'unknown' | null;
  breakout_bias: 'upside' | 'downside' | 'none' | null;
  reversal_risk: 'low' | 'medium' | 'high' | 'unknown' | null;
  multi_timeframe_agreement: 'bullish_alignment' | 'bearish_alignment' | 'mixed' | 'insufficient_data' | null;
  timeframe_summaries: TechnicalTimeframeSummary[];
  explanation: string | null;
}

export interface PatternAnalysisResponse {
  symbol: string;
  horizon: PatternHorizon;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  coverage_start: string | null;
  coverage_end: string | null;
  coverage_ratio_pct: DecimalString;
  partial_coverage: boolean;
  overall_direction: 'bullish' | 'bearish' | 'sideways' | null;
  net_return_pct: DecimalString | null;
  up_moves: number;
  down_moves: number;
  flat_moves: number;
  up_move_ratio_pct: DecimalString | null;
  down_move_ratio_pct: DecimalString | null;
  realized_volatility_pct: DecimalString | null;
  max_drawdown_pct: DecimalString | null;
  trend_character: 'persistent' | 'balanced' | 'choppy' | null;
  breakout_tendency: 'breakout_prone' | 'range_bound' | 'mixed' | null;
  reversal_tendency: 'elevated' | 'normal' | 'low' | 'unknown' | null;
  explanation: string | null;
}

export interface MarketSentimentResponse {
  symbol: string;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  market_state: 'risk_on' | 'risk_off' | 'mixed' | 'insufficient_data';
  sentiment_score: number | null;
  btc_bias: 'bullish' | 'bearish' | 'neutral' | null;
  eth_bias: 'bullish' | 'bearish' | 'neutral' | null;
  selected_symbol_relative_strength: 'outperforming_btc' | 'underperforming_btc' | 'in_line' | 'insufficient_data';
  relative_strength_pct: DecimalString | null;
  market_breadth_state: 'positive' | 'negative' | 'mixed' | 'insufficient_data';
  breadth_advancing_symbols: number;
  breadth_declining_symbols: number;
  breadth_sample_size: number;
  volatility_environment: 'calm' | 'normal' | 'stressed' | 'insufficient_data';
  explanation: string | null;
}

export interface SymbolSentimentResponse {
  symbol: string;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  score: number | null;
  label: 'bullish' | 'bearish' | 'neutral' | 'mixed' | 'insufficient_data';
  confidence: number | null;
  momentum_state: 'rising' | 'fading' | 'stable' | 'unknown';
  risk_flag: 'hype' | 'panic' | 'normal' | 'unknown';
  source_mode: 'proxy' | 'external' | 'mixed';
  components: string[];
  explanation: string | null;
}

export interface FusionSignalResponse {
  symbol: string;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  final_signal: 'long' | 'short' | 'wait' | 'reduce_risk' | 'exit_long' | 'exit_short';
  confidence: number;
  expected_edge_pct: DecimalString | null;
  preferred_horizon: '5m' | '15m' | '1h';
  risk_grade: 'low' | 'medium' | 'high';
  alignment_score: number;
  top_reasons: string[];
  warnings: string[];
  invalidation_hint: string | null;
}

export interface TradeReadinessResponse {
  selected_symbol: string;
  runtime_active: boolean;
  mode: 'auto_paper' | 'paused' | 'stopped' | 'error';
  trading_profile: TradingProfile;
  enough_candle_history: boolean;
  deterministic_entry_signal: boolean;
  deterministic_exit_signal: boolean;
  risk_ready: boolean;
  risk_blocked: boolean;
  broker_ready: boolean;
  next_action: string;
  reason_if_not_trading: string | null;
  blocking_reasons: string[];
  signal_reason_codes: string[];
  risk_reason_codes: string[];
  expected_edge_pct: DecimalString | null;
  estimated_round_trip_cost_pct: DecimalString | null;
}

export interface ManualTradeResponse {
  symbol: string;
  action: 'buy_market' | 'close_position';
  requested_side: 'BUY' | 'SELL';
  status: 'executed' | 'rejected';
  message: string;
  reason_codes: string[];
  approved_quantity: DecimalString | null;
  filled_quantity: DecimalString | null;
  fill_price: DecimalString | null;
  current_position_quantity: DecimalString | null;
  current_pnl: DecimalString;
}

export interface AISignalHistoryResponse {
  items: AISignalSummary[];
  total: number;
  limit: number;
  offset: number;
  data_state: WorkstationDataState;
  status_message: string | null;
}

export interface AIOutcomeHorizonSummary {
  horizon: '5m' | '15m' | '1h';
  sample_size: number;
  directional_accuracy_pct: DecimalString;
  confidence_calibration_pct: DecimalString;
  actionable_sample_size: number;
  abstain_count: number;
  abstain_rate_pct: DecimalString;
  false_positive_count: number;
  false_positive_rate_pct: DecimalString;
  false_reversal_count: number;
  false_reversal_rate_pct: DecimalString;
}

export interface AIOutcomeSampleSummary {
  symbol: string;
  snapshot_time: string;
  horizon: '5m' | '15m' | '1h';
  bias: 'bullish' | 'bearish' | 'sideways';
  confidence: number;
  entry_signal: boolean;
  exit_signal: boolean;
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit' | 'abstain';
  baseline_close: DecimalString;
  future_close: DecimalString;
  return_pct: DecimalString;
  observed_direction: 'bullish' | 'bearish' | 'sideways' | 'unknown';
  directional_correct: boolean;
  false_positive: boolean;
  false_reversal: boolean;
  abstained: boolean;
}

export interface AIOutcomeEvaluationResponse {
  symbol: string;
  generated_at: string;
  horizons: AIOutcomeHorizonSummary[];
  recent_samples: AIOutcomeSampleSummary[];
  data_state: WorkstationDataState;
  status_message: string | null;
}

export interface SignalSummary {
  side: 'BUY' | 'SELL' | 'HOLD';
  confidence: DecimalString;
  reason_codes: string[];
}

export interface PositionSummary {
  symbol: string;
  quantity: DecimalString;
  avg_entry_price: DecimalString;
  realized_pnl: DecimalString;
  quote_asset: string;
}

export interface LastActionSummary {
  signal_side: 'BUY' | 'SELL' | 'HOLD';
  signal_reasons: string[];
  execution_status: string | null;
  execution_reasons: string[];
  event_time: string;
}

export interface WorkstationResponse {
  symbol: string;
  data_state: WorkstationDataState;
  status_message: string | null;
  is_runtime_symbol: boolean;
  runtime_status: BotStatusResponse;
  persistence: PersistenceHealthSummary;
  last_price: DecimalString | null;
  current_candle: CandleSummary | null;
  top_of_book: TopOfBookSummary | null;
  feature: FeatureSummary | null;
  trade_readiness: TradeReadinessResponse;
  ai_signal: AISignalSummary | null;
  trend_bias: string | null;
  entry_signal: SignalSummary | null;
  exit_signal: SignalSummary | null;
  explanation: string | null;
  current_position: PositionSummary | null;
  last_action: LastActionSummary | null;
  last_market_event: string | null;
  total_pnl: DecimalString;
  realized_pnl: DecimalString;
}

export interface HealthResponse {
  name: string;
  status: string;
  mode: string;
  storage: string;
}

export interface MetricsResponse {
  total_trades: number;
  win_rate: DecimalString;
  realized_pnl: DecimalString;
  average_pnl_per_trade: DecimalString;
  current_equity: DecimalString;
  max_winning_streak: number;
  max_losing_streak: number;
}

export interface PerformanceAnalyticsResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  total_closed_trades: number;
  expectancy_per_closed_trade: DecimalString | null;
  profit_factor: DecimalString | null;
  average_hold_seconds: number | null;
  average_win: DecimalString | null;
  average_loss: DecimalString | null;
  session_realized_pnl: DecimalString;
  session_unrealized_pnl: DecimalString;
  symbol_realized_pnl: DecimalString;
  max_drawdown: DecimalString;
  current_drawdown: DecimalString;
}

export interface HoldTimeDistribution {
  average_seconds: number | null;
  median_seconds: number | null;
  p75_seconds: number | null;
  max_seconds: number | null;
}

export interface TradeQualitySummary {
  total_closed_trades: number;
  average_mfe_pct: DecimalString | null;
  average_mae_pct: DecimalString | null;
  average_captured_move_pct: DecimalString | null;
  average_giveback_pct: DecimalString | null;
  average_entry_quality_score: DecimalString | null;
  average_exit_quality_score: DecimalString | null;
  longest_no_trade_seconds: number | null;
  hold_time_distribution: HoldTimeDistribution;
}

export interface TradeQualityDetail {
  order_id: string;
  symbol: string;
  entry_time: string;
  exit_time: string;
  quantity: DecimalString;
  entry_price: DecimalString;
  exit_price: DecimalString;
  realized_pnl: DecimalString;
  hold_seconds: number;
  mfe_pct: DecimalString;
  mae_pct: DecimalString;
  captured_move_pct: DecimalString;
  giveback_pct: DecimalString;
  entry_quality_score: DecimalString;
  exit_quality_score: DecimalString;
}

export interface TradeQualityResponse {
  symbol: string;
  start_date: string | null;
  end_date: string | null;
  total_details: number;
  limit: number;
  offset: number;
  summary: TradeQualitySummary;
  details: TradeQualityDetail[];
}

export interface ReviewTradesPerSymbolItem {
  symbol: string;
  trade_count: number;
}

export interface PaperTradeReviewSession {
  trades_per_hour: DecimalString | null;
  trades_per_symbol: ReviewTradesPerSymbolItem[];
  win_rate: DecimalString | null;
  average_pnl: DecimalString | null;
  average_hold_seconds: number | null;
  fees_paid: DecimalString;
  idle_duration_seconds: number | null;
  total_closed_trades: number;
}

export interface BlockerFrequencyItem {
  blocker_key: string;
  label: string;
  count: number;
  frequency_pct: DecimalString;
}

export interface ProfileComparisonItem {
  profile: TradingProfile;
  trade_count: number;
  realized_pnl: DecimalString;
  win_rate: DecimalString | null;
  average_expectancy: DecimalString | null;
}

export interface ExecutionSourceComparisonItem {
  execution_source: 'auto' | 'manual';
  trade_count: number;
  realized_pnl: DecimalString;
  win_rate: DecimalString | null;
  average_expectancy: DecimalString | null;
}

export interface TuningSuggestionItem {
  summary: string;
}

export interface PaperTradeReviewResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  session: PaperTradeReviewSession;
  blockers: BlockerFrequencyItem[];
  profiles: ProfileComparisonItem[];
  execution_sources: ExecutionSourceComparisonItem[];
  suggestions: TuningSuggestionItem[];
}

export interface ThresholdChangeItem {
  threshold: string;
  current_value: DecimalString;
  suggested_value: DecimalString;
}

export interface ProfileCalibrationRecommendationItem {
  profile: TradingProfile;
  profile_health: string;
  recommendation: 'keep' | 'tighten' | 'loosen';
  reason: string;
  affected_thresholds: ThresholdChangeItem[];
  expected_impact: string;
  sample_size_warning: string | null;
  trade_count: number;
  win_rate: DecimalString | null;
  expectancy: DecimalString | null;
  fees_paid: DecimalString;
  blocker_share: Record<string, DecimalString>;
}

export interface ProfileCalibrationResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  recommendations: ProfileCalibrationRecommendationItem[];
  active_tuning: ProfileTuningPreviewItem | null;
  pending_tuning: ProfileTuningPreviewItem | null;
}

export interface ProfileTuningPreviewItem {
  version_id: string;
  profile: TradingProfile;
  status: string;
  created_at: string;
  applied_at: string | null;
  baseline_version_id: string | null;
  reason: string;
  affected_thresholds: ThresholdChangeItem[];
}

export interface ProfileCalibrationApplyResponse {
  symbol: string;
  profile: TradingProfile;
  applied_to_next_session: boolean;
  status_message: string;
  pending_tuning: ProfileTuningPreviewItem;
}

export interface ProfileCalibrationComparisonMetricsItem {
  session_count: number;
  trade_count: number;
  expectancy: DecimalString | null;
  profit_factor: DecimalString | null;
  win_rate: DecimalString | null;
  max_drawdown: DecimalString | null;
  fees_paid: DecimalString;
  blocker_distribution: Record<string, DecimalString>;
}

export interface ProfileCalibrationComparisonResponse {
  symbol: string;
  profile: TradingProfile;
  start_date: string | null;
  end_date: string | null;
  comparison_status: 'ready' | 'insufficient_data';
  status_message: string | null;
  active_tuning: ProfileTuningPreviewItem | null;
  baseline_tuning: ProfileTuningPreviewItem | null;
  before: ProfileCalibrationComparisonMetricsItem | null;
  after: ProfileCalibrationComparisonMetricsItem | null;
}

export interface TradeItem {
  order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  requested_quantity: DecimalString;
  approved_quantity: DecimalString;
  filled_quantity: DecimalString;
  status: string;
  risk_decision: string;
  reason_codes: string[];
  fill_price: DecimalString;
  realized_pnl: DecimalString;
  quote_balance: DecimalString;
  event_time: string;
}

export interface FillItem {
  order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  filled_quantity: DecimalString;
  fill_price: DecimalString;
  fee_paid: DecimalString;
  realized_pnl: DecimalString;
  quote_balance: DecimalString;
  event_time: string;
}

export interface EventItem {
  event_type: string;
  symbol: string;
  message: string;
  payload: Record<string, unknown>;
  event_time: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PositionItem {
  symbol: string;
  quantity: DecimalString;
  avg_entry_price: DecimalString;
  realized_pnl: DecimalString;
  quote_asset: string;
  snapshot_time: string;
}

export interface EquityResponse {
  snapshot_time: string | null;
  equity: DecimalString;
  total_pnl: DecimalString;
  realized_pnl: DecimalString;
  cash_balance: DecimalString;
}

export interface SymbolSummaryItem {
  symbol: string;
  total_trades: number;
  buy_trades: number;
  sell_trades: number;
  win_rate: DecimalString;
  realized_pnl: DecimalString;
  open_quantity: DecimalString;
  avg_entry_price: DecimalString;
  open_exposure: DecimalString;
  last_trade_time: string | null;
}

export interface HistoryFilters {
  symbol: string;
  startDate: string;
  endDate: string;
  limit: number;
  offset: number;
}

export interface RangeFilters {
  startDate?: string;
  endDate?: string;
}

export interface EquityHistoryPoint {
  snapshot_time: string;
  equity: DecimalString;
}

export interface PnlHistoryPoint {
  snapshot_time: string;
  total_pnl: DecimalString;
  realized_pnl: DecimalString;
}

export interface DailyPnlPoint {
  day: string;
  total_pnl: DecimalString;
  realized_pnl: DecimalString;
}

export interface PnlHistoryResponse {
  points: PnlHistoryPoint[];
  daily: DailyPnlPoint[];
}

export interface DrawdownPoint {
  snapshot_time: string;
  equity: DecimalString;
  peak_equity: DecimalString;
  drawdown: DecimalString;
  drawdown_pct: DecimalString;
}

export interface DrawdownResponse {
  current_drawdown: DecimalString;
  current_drawdown_pct: DecimalString;
  max_drawdown: DecimalString;
  max_drawdown_pct: DecimalString;
  points: DrawdownPoint[];
}
