export interface AIHistoryItemSummary {
  symbol: string;
  timestamp: string;
  bias: 'bullish' | 'bearish' | 'sideways';
  confidence: number;
  entry_signal: boolean;
  exit_signal: boolean;
  suggested_action: 'wait' | 'enter' | 'hold' | 'exit';
  explanation: string;
}

export interface AIHistoryViewModel {
  items: AIHistoryItemSummary[];
  recentItems: AIHistoryItemSummary[];
  recentActionChanges: AIHistoryItemSummary[];
  labels: string[];
  confidenceValues: number[];
  biasValues: number[];
}

export function biasToScore(bias: AIHistoryItemSummary['bias']): number;
export function buildAiHistoryViewModel(selectedSymbol: string, items: AIHistoryItemSummary[]): AIHistoryViewModel;
