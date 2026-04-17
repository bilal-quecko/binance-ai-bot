export type DecimalString = string;

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

export interface DailyPnlPoint {
  day: string;
  value: number;
}

