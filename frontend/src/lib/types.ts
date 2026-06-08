export type DecimalString = string;
export type LiquidationSignal = 'none' | 'cascade_down' | 'cascade_up' | 'exhaustion' | 'sweep_confirmation' | 'noise';
export type DominantLiquidationSide = 'longs_liquidated' | 'shorts_liquidated' | 'balanced';
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

export interface BackfillStatusResponse {
  symbol: string;
  requested_interval: ChartTimeframe;
  requested_lookback_days: number;
  available_from: string | null;
  available_to: string | null;
  candle_count: number;
  coverage_pct: DecimalString;
  status: 'not_started' | 'loading' | 'ready' | 'partial' | 'failed';
  message: string;
  last_backfilled_at: string | null;
  effective_interval: ChartTimeframe | null;
}

export interface SimilarSetupHorizonMetric {
  horizon: string;
  sample_size: number;
  win_rate_pct: DecimalString | null;
  expectancy_pct: DecimalString | null;
  average_favorable_move_pct: DecimalString | null;
  average_adverse_move_pct: DecimalString | null;
}

export interface SimilarSetupResponse {
  status: 'ready' | 'insufficient_data';
  reliability_label: 'insufficient_data' | 'weak' | 'mixed' | 'promising' | 'strong';
  matching_sample_size: number;
  best_horizon: string | null;
  horizons: SimilarSetupHorizonMetric[];
  explanation: string;
  matched_attributes: string[];
}

export interface LiquidityZoneResponse {
  level: DecimalString | null;
  strength: 'low' | 'medium' | 'high';
  reason: string;
}

export interface NearestLiquidityTargetResponse {
  direction: 'up' | 'down' | 'none';
  level: DecimalString | null;
  distance_pct: DecimalString | null;
  strength: 'low' | 'medium' | 'high';
}

export interface TradingAssistantResponse {
  symbol: string;
  decision: 'buy' | 'sell_exit' | 'wait' | 'avoid';
  confidence_label: 'low' | 'medium' | 'high';
  confidence_score: number;
  risk_label: 'low' | 'medium' | 'high';
  best_timeframe: '5m' | '15m' | '1h' | 'unknown';
  simple_reason: string;
  why_not_trade: string | null;
  suggested_entry_zone: string | null;
  suggested_stop_loss: DecimalString | null;
  suggested_take_profit: DecimalString | null;
  data_state: WorkstationDataState;
  backfill_status: BackfillStatusResponse;
  similar_setup: SimilarSetupResponse | null;
  liquidity_bias: 'bullish' | 'bearish' | 'neutral';
  liquidity_pressure: 'low' | 'medium' | 'high';
  likely_liquidation_direction: 'up' | 'down' | 'none';
  trap_risk: 'long_trap' | 'short_trap' | 'low';
  liquidity_explanation: string;
  upside_liquidity_zone: LiquidityZoneResponse;
  downside_liquidity_zone: LiquidityZoneResponse;
  nearest_liquidity_target: NearestLiquidityTargetResponse;
  sweep_risk: 'none' | 'upside_sweep' | 'downside_sweep' | 'both_sides';
  trade_timing_adjustment: 'enter_now' | 'wait_for_sweep' | 'wait_for_confirmation' | 'avoid_chop';
  tp_sl_alignment: 'aligned' | 'stop_too_close_to_liquidity' | 'target_before_liquidity' | 'target_after_liquidity' | 'needs_review';
  liquidity_zone_explanation: string;
  crowd_side: 'long_crowded' | 'short_crowded' | 'balanced';
  crowd_strength: 'low' | 'medium' | 'high';
  squeeze_risk: 'long_squeeze' | 'short_squeeze' | 'low';
  positioning_explanation: string;
  funding_rate: DecimalString | null;
  open_interest: DecimalString | null;
  oi_trend: 'rising' | 'falling' | 'neutral';
  heatmap_liquidity_above: DecimalString | null;
  heatmap_liquidity_below: DecimalString | null;
  heatmap_intensity_score: number | null;
  heatmap_bias: 'upside_squeeze' | 'downside_sweep' | 'neutral';
  base_signal_type: string;
  heatmap_signal_type: string;
  base_confidence: number;
  heatmap_confidence: number;
  heatmap_alignment: 'confirmed' | 'conflict' | 'neutral';
  heatmap_explanation: string;
  heatmap_provider: string;
  heatmap_data_quality: string;
  heatmap_is_real_data: boolean;
  heatmap_provider_status: string;
  liquidation_pressure: 'low' | 'medium' | 'high';
  liquidation_imbalance: DecimalString | null;
  liquidation_signal: LiquidationSignal;
  liquidation_intensity: 'low' | 'medium' | 'high';
  dominant_side: DominantLiquidationSide;
  liquidation_explanation: string;
  liquidation_volume_long: DecimalString;
  liquidation_volume_short: DecimalString;
  liquidation_imbalance_ratio: DecimalString;
  liquidation_event_frequency: DecimalString;
}

export interface TradeEligibilityResponse {
  symbol: string;
  status: 'eligible' | 'not_eligible' | 'watch_only' | 'insufficient_data';
  evidence_strength: 'insufficient' | 'weak' | 'mixed' | 'promising' | 'strong';
  reason: string;
  required_confirmations: string[];
  minimum_confidence_threshold: number;
  preferred_horizon: string | null;
  conditions_to_avoid: string[];
  blocker_summary: string;
  similar_setup_summary: string;
  regime_summary: string;
  fee_slippage_summary: string;
  warnings: string[];
  liquidity_zone_summary: string;
  sweep_risk: 'none' | 'upside_sweep' | 'downside_sweep' | 'both_sides';
  trade_timing_adjustment: 'enter_now' | 'wait_for_sweep' | 'wait_for_confirmation' | 'avoid_chop';
  tp_sl_alignment: 'aligned' | 'stop_too_close_to_liquidity' | 'target_before_liquidity' | 'target_after_liquidity' | 'needs_review';
  crowd_side: 'long_crowded' | 'short_crowded' | 'balanced';
  crowd_strength: 'low' | 'medium' | 'high';
  squeeze_risk: 'long_squeeze' | 'short_squeeze' | 'low';
  liquidation_signal: LiquidationSignal;
  liquidation_intensity: 'low' | 'medium' | 'high';
  dominant_side: DominantLiquidationSide;
  paper_only: boolean;
  advisory_only: boolean;
  live_trading_enabled: boolean;
  futures_enabled: boolean;
}

export interface OpportunityResponse {
  symbol: string;
  score: number;
  suggested_action: 'watch' | 'possible_buy' | 'avoid';
  confidence: 'low' | 'medium' | 'high';
  volatility_label: string;
  momentum_label: string;
  liquidity_label: string;
  risk_label: 'low' | 'medium' | 'high';
  reason: string;
  data_state: WorkstationDataState;
}

export interface SpotOpportunitySignalResponse {
  symbol: string;
  action: 'buy_candidate' | 'watch' | 'avoid' | 'exit_watch';
  opportunity_score: number;
  confidence: number;
  trend_score: number;
  momentum_score: number;
  volatility_quality_score: number;
  liquidity_score: number;
  structure_score: number;
  regime_score: number;
  validation_score: number | null;
  eligibility_score: number;
  evidence_strength: 'insufficient' | 'weak' | 'mixed' | 'promising' | 'strong';
  trend: string;
  momentum: string;
  best_horizon: string;
  risk_grade: 'low' | 'medium' | 'high';
  current_price: string | null;
  suggested_entry_zone: string | null;
  suggested_stop_loss: string | null;
  suggested_take_profit: string | null;
  regime: string | null;
  data_source: 'binance_spot';
  price_type: 'spot_last_price';
  reason: string;
  warnings: string[];
  timestamp: string;
  paper_only: boolean;
  advisory_only: boolean;
  live_trading_enabled: boolean;
  futures_enabled: boolean;
}

export interface SpotOpportunityScanResponse {
  generated_at: string;
  scan_state: 'ready' | 'partial' | 'insufficient_data' | 'degraded';
  warnings: string[];
  scanned_count: number;
  failed_symbols: string[];
  buy_candidates: SpotOpportunitySignalResponse[];
  watch_candidates: SpotOpportunitySignalResponse[];
  avoid_candidates: SpotOpportunitySignalResponse[];
  exit_watch_candidates: SpotOpportunitySignalResponse[];
  data_source: 'binance_spot' | 'last_successful_cache' | 'empty_degraded';
  quote_asset: string;
  symbol_count: number;
  latest_successful_scanner_at: string | null;
  latest_error: string | null;
  persisted_candidate_count: number;
}

export interface SpotOpportunityScanJobResponse {
  scan_id: string;
  status: 'queued' | 'running' | 'partial' | 'completed' | 'failed' | 'cancelled';
  total_symbols: number;
  scanned_symbols: number;
  current_symbol: string | null;
  current_phase: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  scan: SpotOpportunityScanResponse | null;
  warnings: string[];
  failed_symbols: string[];
  latest_error: string | null;
}

export interface FuturesPaperSignalResponse {
  symbol: string;
  direction: 'long' | 'short' | 'wait' | 'avoid';
  opportunity_score: number;
  direction_score: number;
  momentum_score: number;
  trend_score: number;
  volatility_quality_score: number;
  liquidity_score: number;
  risk_score: number;
  validation_score: number | null;
  confidence: number;
  evidence_strength: 'insufficient' | 'unvalidated' | 'weak' | 'mixed' | 'promising' | 'strong';
  trend: string;
  momentum: string;
  best_horizon: string;
  risk_grade: 'low' | 'medium' | 'high';
  regime: string | null;
  current_price: DecimalString | null;
  market_sensitivity: TradingProfile;
  slow_market_setup: 'none' | 'range_breakout' | 'liquidity_sweep_reversal' | 'compression_breakout' | 'mean_reversion_range_edge' | 'low_volatility_continuation' | 'low_volatility_no_edge';
  slow_market_reason: string | null;
  data_source: 'binance_usdm_futures';
  price_type: 'mark_price' | 'futures_last_price';
  reason: string;
  invalidation_hint: string | null;
  suggested_entry_zone: string | null;
  suggested_stop_loss: DecimalString | null;
  suggested_take_profit: DecimalString | null;
  estimated_fee_impact: DecimalString | null;
  leverage_suggestion: string;
  liquidation_safety_note: string;
  similar_setup_summary: string;
  eligibility_status: string;
  warnings: string[];
  timestamp: string;
  liquidity_bias: 'bullish' | 'bearish' | 'neutral';
  liquidity_pressure: 'low' | 'medium' | 'high';
  likely_liquidation_direction: 'up' | 'down' | 'none';
  trap_risk: 'long_trap' | 'short_trap' | 'low';
  liquidity_explanation: string;
  upside_liquidity_zone: LiquidityZoneResponse;
  downside_liquidity_zone: LiquidityZoneResponse;
  nearest_liquidity_target: NearestLiquidityTargetResponse;
  sweep_risk: 'none' | 'upside_sweep' | 'downside_sweep' | 'both_sides';
  trade_timing_adjustment: 'enter_now' | 'wait_for_sweep' | 'wait_for_confirmation' | 'avoid_chop';
  tp_sl_alignment: 'aligned' | 'stop_too_close_to_liquidity' | 'target_before_liquidity' | 'target_after_liquidity' | 'needs_review';
  liquidity_zone_explanation: string;
  liquidity_adjusted_note: string | null;
  crowd_side: 'long_crowded' | 'short_crowded' | 'balanced';
  crowd_strength: 'low' | 'medium' | 'high';
  squeeze_risk: 'long_squeeze' | 'short_squeeze' | 'low';
  funding_rate: DecimalString | null;
  open_interest: DecimalString | null;
  oi_trend: 'rising' | 'falling' | 'neutral';
  heatmap_liquidity_above: DecimalString | null;
  heatmap_liquidity_below: DecimalString | null;
  heatmap_intensity_score: number | null;
  heatmap_bias: 'upside_squeeze' | 'downside_sweep' | 'neutral';
  base_signal_type: string;
  heatmap_signal_type: string;
  base_confidence: number;
  heatmap_confidence: number;
  heatmap_alignment: 'confirmed' | 'conflict' | 'neutral';
  heatmap_explanation: string;
  heatmap_provider: string;
  heatmap_data_quality: string;
  heatmap_is_real_data: boolean;
  heatmap_provider_status: string;
  liquidation_pressure: 'low' | 'medium' | 'high';
  liquidation_imbalance: DecimalString | null;
  liquidation_signal: LiquidationSignal;
  liquidation_intensity: 'low' | 'medium' | 'high';
  dominant_side: DominantLiquidationSide;
  liquidation_explanation: string;
  liquidation_volume_long: DecimalString;
  liquidation_volume_short: DecimalString;
  liquidation_imbalance_ratio: DecimalString;
  liquidation_event_frequency: DecimalString;
}

export interface FuturesOpportunityScanResponse {
  generated_at: string;
  scan_state: 'ready' | 'partial' | 'insufficient_data' | 'degraded';
  long_candidates: FuturesPaperSignalResponse[];
  short_candidates: FuturesPaperSignalResponse[];
  neutral_candidates: FuturesPaperSignalResponse[];
  warnings: string[];
  scanned_count: number;
  failed_symbols: string[];
  paper_only: boolean;
  advisory_only: boolean;
  live_futures_trading_enabled: boolean;
  real_orders_enabled: boolean;
  max_leverage_suggestion: string;
  futures_symbol_universe_source: 'live' | 'cache' | 'fallback' | 'unavailable';
  symbol_count: number;
  last_successful_fetch_at: string | null;
  latest_error: string | null;
  data_source: string;
  latest_successful_scanner_at: string | null;
  latest_scanner_error: string | null;
  persisted_candidate_count: number;
  fallback_symbol_count: number;
}

export interface FuturesOpportunityScanJobResponse {
  scan_id: string;
  status: 'queued' | 'running' | 'partial' | 'completed' | 'failed' | 'cancelled';
  total_symbols: number;
  scanned_symbols: number;
  current_symbol: string | null;
  current_phase: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  scan: FuturesOpportunityScanResponse | null;
  warnings: string[];
  failed_symbols: string[];
  latest_error: string | null;
}

export interface FuturesLivePriceItemResponse {
  symbol: string;
  live_price: DecimalString | null;
  updated_at: string;
  source: 'websocket' | 'rest' | 'cache' | 'unavailable';
  data_source: 'binance_usdm_futures';
  price_type: 'mark_price' | 'futures_last_price';
  stale: boolean;
  warning: string | null;
}

export interface FuturesLivePriceResponse {
  items: FuturesLivePriceItemResponse[];
  warnings: string[];
}

export interface FuturesLiveSubscriptionResponse {
  symbols: string[];
  count: number;
  websocket_enabled: boolean;
  warning: string | null;
}

export interface ScannerValidationGroupPerformance {
  name: string;
  sample_size: number;
  win_rate: DecimalString | null;
  average_net_return: DecimalString | null;
  expectancy: DecimalString | null;
}

export interface ScannerBaselineComparison {
  scanner_sample_size: number;
  random_baseline_sample_size: number;
  scanner_average_net_return: DecimalString | null;
  random_baseline_average_net_return: DecimalString | null;
  scanner_win_rate: DecimalString | null;
  random_baseline_win_rate: DecimalString | null;
  edge_vs_random: DecimalString | null;
}

export interface StopLossTakeProfitAnalysis {
  sample_size: number;
  take_profit_hit_rate: DecimalString | null;
  stop_loss_hit_rate: DecimalString | null;
  neither_hit_rate: DecimalString | null;
  take_profit_first: number;
  stop_loss_first: number;
}

export interface ScannerValidationReportResponse {
  generated_at: string;
  total_snapshots: number;
  evaluated_snapshots: number;
  pending_snapshots: number;
  win_rate: DecimalString | null;
  expectancy: DecimalString | null;
  average_win: DecimalString | null;
  average_loss: DecimalString | null;
  average_net_return: DecimalString | null;
  max_drawdown: DecimalString | null;
  scanner_vs_random_baseline: ScannerBaselineComparison;
  opportunity_score_bucket_performance: ScannerValidationGroupPerformance[];
  direction_performance: ScannerValidationGroupPerformance[];
  horizon_performance: ScannerValidationGroupPerformance[];
  stop_loss_take_profit_analysis: StopLossTakeProfitAnalysis;
  best_symbols: ScannerValidationGroupPerformance[];
  worst_symbols: ScannerValidationGroupPerformance[];
  best_regimes: ScannerValidationGroupPerformance[];
  weak_conditions: string[];
  conclusion: 'insufficient_data' | 'weak' | 'mixed' | 'promising' | 'strong';
  warnings: string[];
  paper_validation: boolean;
  advisory_only: boolean;
  live_trading_enabled: boolean;
  real_futures_execution_enabled: boolean;
}

export interface PostSignalOutcomeResponse {
  id: number | null;
  signal_id: string;
  horizon: string;
  future_price: DecimalString | null;
  price_change_percent: DecimalString | null;
  max_upside_percent: DecimalString | null;
  max_downside_percent: DecimalString | null;
  did_price_hit_tp: boolean;
  did_price_hit_sl: boolean;
  direction_correct: boolean | null;
  volatility_range: DecimalString | null;
  first_hit: string | null;
  time_to_hit_seconds: number | null;
  sweep_direction_actual: string;
  sweep_prediction_correct: boolean | null;
  outcome_state: string;
  evaluated_at: string;
  base_signal_correct: boolean | null;
  heatmap_signal_correct: boolean | null;
  did_heatmap_improve_result: boolean | null;
  did_heatmap_reduce_loss: boolean | null;
  predicted_sweep_direction: string;
  actual_sweep_direction: string;
}

export interface PostSignalSnapshotResponse {
  id: string;
  symbol: string;
  timestamp: string;
  source: 'scanner' | 'assistant' | 'eligibility' | string;
  signal_type: 'BUY' | 'SELL' | 'WAIT' | 'AVOID' | string;
  confidence: number;
  entry_price: DecimalString | null;
  liquidity_bias: string | null;
  sweep_risk: string | null;
  nearest_liquidity_above: DecimalString | null;
  nearest_liquidity_below: DecimalString | null;
  funding_rate: DecimalString | null;
  open_interest: DecimalString | null;
  notes: string;
  heatmap_liquidity_above: DecimalString | null;
  heatmap_liquidity_below: DecimalString | null;
  heatmap_intensity_score: number | null;
  heatmap_bias: string | null;
  base_signal_type: string | null;
  heatmap_signal_type: string | null;
  base_confidence: number | null;
  heatmap_confidence: number | null;
  heatmap_alignment: string | null;
  heatmap_explanation: string | null;
  heatmap_provider: string | null;
  heatmap_data_quality: string | null;
  heatmap_is_real_data: boolean | null;
  heatmap_provider_status: string | null;
  liquidation_pressure: string | null;
  liquidation_imbalance: DecimalString | null;
  outcomes: PostSignalOutcomeResponse[];
}

export interface PostSignalHistoryResponse {
  items: PostSignalSnapshotResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface PostSignalGroupSummaryResponse {
  name: string;
  total_signals: number;
  evaluated_signals: number;
  win_rate: DecimalString | null;
  avg_return: DecimalString | null;
  avg_max_upside: DecimalString | null;
  avg_max_drawdown: DecimalString | null;
  tp_hit_rate: DecimalString | null;
  sl_hit_rate: DecimalString | null;
}

export interface PostSignalPerformanceSummaryResponse {
  generated_at: string;
  total_signals: number;
  evaluated_signals: number;
  win_rate: DecimalString | null;
  avg_return: DecimalString | null;
  avg_max_upside: DecimalString | null;
  avg_max_drawdown: DecimalString | null;
  tp_hit_rate: DecimalString | null;
  sl_hit_rate: DecimalString | null;
  base_win_rate: DecimalString | null;
  heatmap_win_rate: DecimalString | null;
  delta_win_rate: DecimalString | null;
  base_avg_return: DecimalString | null;
  heatmap_avg_return: DecimalString | null;
  heatmap_accuracy_on_sweep_prediction: DecimalString | null;
  heatmap_false_signal_rate: DecimalString | null;
  heatmap_signal_count_by_data_quality: Record<string, number>;
  win_rate_by_heatmap_data_quality: Record<string, DecimalString | null>;
  sweep_accuracy_by_data_quality: Record<string, DecimalString | null>;
  avg_return_by_data_quality: Record<string, DecimalString | null>;
  by_signal_type: PostSignalGroupSummaryResponse[];
  by_confidence_bucket: PostSignalGroupSummaryResponse[];
  by_liquidity_bias: PostSignalGroupSummaryResponse[];
  by_source: PostSignalGroupSummaryResponse[];
  paper_validation: boolean;
  advisory_only: boolean;
  live_trading_enabled: boolean;
}

export interface ScannerValidationEvaluateResponse {
  evaluated_outcomes: number;
  idempotent: boolean;
  message: string;
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

export interface RegimeAnalysisResponse {
  symbol: string;
  horizon: PatternHorizon;
  generated_at: string | null;
  data_state: WorkstationDataState;
  status_message: string | null;
  regime_label:
    | 'trending_up'
    | 'trending_down'
    | 'sideways'
    | 'high_volatility'
    | 'low_liquidity'
    | 'choppy'
    | 'breakout_building'
    | 'reversal_risk'
    | null;
  confidence: number;
  supporting_evidence: string[];
  risk_warnings: string[];
  preferred_trading_behavior: string | null;
  avoid_conditions: string[];
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
  current_position_quantity: DecimalString;
  current_position_open: boolean;
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

export interface HorizonQualityMetric {
  horizon: string;
  sample_size: number;
  actionable_sample_size: number;
  win_rate_pct: DecimalString | null;
  expectancy_pct: DecimalString | null;
  average_favorable_move_pct: DecimalString | null;
  average_adverse_move_pct: DecimalString | null;
  false_positive_rate_pct: DecimalString | null;
  false_breakout_rate_pct: DecimalString | null;
  winner_average_confidence: DecimalString | null;
  loser_average_confidence: DecimalString | null;
}

export interface GroupPerformanceMetric {
  name: string;
  sample_size: number;
  win_rate_pct: DecimalString | null;
  expectancy_pct: DecimalString | null;
}

export interface ReasonPerformanceMetric {
  reason: string;
  sample_size: number;
  win_rate_pct: DecimalString | null;
  expectancy_pct: DecimalString | null;
}

export interface SignalValidationResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  status: 'ready' | 'insufficient_data';
  status_message: string | null;
  total_signals: number;
  actionable_signals: number;
  ignored_or_blocked_signals: number;
  horizons: HorizonQualityMetric[];
  performance_by_action: GroupPerformanceMetric[];
  performance_by_risk_grade: GroupPerformanceMetric[];
  performance_by_confidence_bucket: GroupPerformanceMetric[];
  performance_by_symbol: GroupPerformanceMetric[];
}

export interface EdgeReportResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  status: 'ready' | 'insufficient_data';
  status_message: string | null;
  useful_symbols: GroupPerformanceMetric[];
  weak_symbols: GroupPerformanceMetric[];
  best_horizons: HorizonQualityMetric[];
  reliable_confidence_ranges: GroupPerformanceMetric[];
  risk_grades_to_avoid: GroupPerformanceMetric[];
  useful_reasons: ReasonPerformanceMetric[];
  noisy_reasons: ReasonPerformanceMetric[];
  protective_blockers: ReasonPerformanceMetric[];
  noisy_modules: string[];
  suggestions: string[];
}

export interface ModuleAttributionResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  status: 'ready' | 'insufficient_data';
  status_message: string | null;
  modules: GroupPerformanceMetric[];
}

export interface AdaptiveRecommendationItem {
  recommendation_id: string;
  recommendation_type:
    | 'raise_min_confidence'
    | 'lower_min_confidence'
    | 'avoid_regime'
    | 'prefer_horizon'
    | 'avoid_horizon'
    | 'restrict_symbol'
    | 'watch_symbol'
    | 'restrict_action_type'
    | 'tighten_risk_grade'
    | 'loosen_risk_grade'
    | 'require_confirmation'
    | 'keep_current_settings'
    | 'insufficient_data';
  affected_scope:
    | 'global'
    | 'symbol'
    | 'regime'
    | 'horizon'
    | 'action_type'
    | 'risk_grade'
    | 'confidence_bucket';
  affected_value: string;
  current_observation: string;
  suggested_change: string;
  evidence_summary: string;
  expected_benefit: string;
  evidence_strength: 'insufficient' | 'weak' | 'mixed' | 'promising' | 'strong';
  sample_size: number;
  minimum_sample_required: number;
  warnings: string[];
  do_not_auto_apply: boolean;
}

export interface AdaptiveRecommendationResponse {
  symbol: string | null;
  start_date: string | null;
  end_date: string | null;
  status: 'ready' | 'insufficient_data';
  status_message: string | null;
  recommendations: AdaptiveRecommendationItem[];
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
