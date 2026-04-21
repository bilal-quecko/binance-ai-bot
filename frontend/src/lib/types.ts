export type DecimalString = string;
export type RangePreset = '1D' | '7D' | '30D' | 'ALL';
export type AutoRefreshIntervalSeconds = 0 | 5 | 10 | 30;

export interface SpotSymbolItem {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  status: string;
}

export interface BotStatusResponse {
  state: 'stopped' | 'running' | 'paused' | 'error';
  symbol: string | null;
  timeframe: string;
  paper_only: boolean;
  started_at: string | null;
  last_event_time: string | null;
  last_error: string | null;
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
}

export interface AISignalSummary {
  symbol: string;
  timestamp: string;
  bias: 'bullish' | 'bearish' | 'sideways';
  confidence: number;
  entry_signal: boolean;
  exit_signal: boolean;
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit';
  explanation: string;
  features: AISignalFeatureSummary;
}

export interface AISignalHistoryResponse {
  items: AISignalSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AIOutcomeHorizonSummary {
  horizon: '5m' | '15m' | '1h';
  sample_size: number;
  directional_accuracy_pct: DecimalString;
  confidence_calibration_pct: DecimalString;
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
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit';
  baseline_close: DecimalString;
  future_close: DecimalString;
  return_pct: DecimalString;
  observed_direction: 'bullish' | 'bearish' | 'sideways' | 'unknown';
  directional_correct: boolean;
  false_positive: boolean;
  false_reversal: boolean;
}

export interface AIOutcomeEvaluationResponse {
  symbol: string;
  generated_at: string;
  horizons: AIOutcomeHorizonSummary[];
  recent_samples: AIOutcomeSampleSummary[];
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
  is_runtime_symbol: boolean;
  runtime_status: BotStatusResponse;
  last_price: DecimalString | null;
  current_candle: CandleSummary | null;
  top_of_book: TopOfBookSummary | null;
  feature: FeatureSummary | null;
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
