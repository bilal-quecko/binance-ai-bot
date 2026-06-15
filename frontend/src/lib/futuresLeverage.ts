import type { FuturesPaperSignalResponse } from './types';

export type LeverageOption = 1 | 2 | 3 | 5 | 10 | 25 | 50 | 100;
export type LeverageRiskLabel = 'low' | 'medium' | 'high' | 'extreme';

export interface FuturesLeverageSimulation {
  selected_leverage: LeverageOption;
  estimated_tp_return_percent: number | null;
  estimated_sl_return_percent: number | null;
  estimated_current_unrealized_return_percent: number | null;
  fee_adjusted_tp_return_percent: number | null;
  fee_adjusted_sl_return_percent: number | null;
  liquidation_risk_label: LeverageRiskLabel;
  leverage_warning: string | null;
  fee_slippage_estimated: boolean;
}

const DEFAULT_FEE_SLIPPAGE_PCT = 0.12;
export const LEVERAGE_OPTIONS: LeverageOption[] = [1, 2, 3, 5, 10, 25, 50, 100];

function parseNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function pct(value: number | null): number | null {
  return value === null ? null : Number(value.toFixed(4));
}

function leveragedReturn(
  direction: 'long' | 'short',
  entryPrice: number | null,
  targetPrice: number | null,
  leverage: LeverageOption,
): number | null {
  if (entryPrice === null || targetPrice === null || entryPrice <= 0) {
    return null;
  }
  const raw = direction === 'long'
    ? ((targetPrice - entryPrice) / entryPrice) * 100 * leverage
    : ((entryPrice - targetPrice) / entryPrice) * 100 * leverage;
  return pct(raw);
}

function feeAdjusted(value: number | null, feeDrag: number): number | null {
  return value === null ? null : pct(value - feeDrag);
}

function riskLabel(stopLossReturn: number | null): LeverageRiskLabel {
  if (stopLossReturn === null) {
    return 'high';
  }
  const impact = Math.abs(stopLossReturn);
  if (impact < 5) {
    return 'low';
  }
  if (impact < 15) {
    return 'medium';
  }
  if (impact < 50) {
    return 'high';
  }
  return 'extreme';
}

function leverageWarning(leverage: LeverageOption): string | null {
  if (leverage >= 50) {
    return 'Extreme paper leverage. Small adverse moves can wipe out simulated margin.';
  }
  if (leverage >= 25) {
    return 'High paper leverage. Adverse moves and fee drag can dominate the simulated setup.';
  }
  return null;
}

export function simulateFuturesLeverageFromPrices({
  direction,
  entryPrice,
  takeProfit,
  stopLoss,
  livePrice,
  leverage,
  estimatedFeeSlippagePct,
}: {
  direction: 'long' | 'short';
  entryPrice: string | number | null | undefined;
  takeProfit: string | number | null | undefined;
  stopLoss: string | number | null | undefined;
  livePrice: string | number | null | undefined;
  leverage: LeverageOption;
  estimatedFeeSlippagePct?: string | number | null;
}): FuturesLeverageSimulation {
  const parsedEntry = parseNumber(entryPrice);
  const parsedTakeProfit = parseNumber(takeProfit);
  const parsedStopLoss = parseNumber(stopLoss);
  const parsedLivePrice = parseNumber(livePrice);
  const feeSlippagePct = parseNumber(estimatedFeeSlippagePct);
  const feePct = feeSlippagePct ?? DEFAULT_FEE_SLIPPAGE_PCT;
  const feeDrag = feePct * leverage;
  const tpReturn = leveragedReturn(direction, parsedEntry, parsedTakeProfit, leverage);
  const slReturn = leveragedReturn(direction, parsedEntry, parsedStopLoss, leverage);
  const currentReturn = leveragedReturn(direction, parsedEntry, parsedLivePrice, leverage);

  return {
    selected_leverage: leverage,
    estimated_tp_return_percent: tpReturn,
    estimated_sl_return_percent: slReturn,
    estimated_current_unrealized_return_percent: currentReturn,
    fee_adjusted_tp_return_percent: feeAdjusted(tpReturn, feeDrag),
    fee_adjusted_sl_return_percent: feeAdjusted(slReturn, feeDrag),
    liquidation_risk_label: riskLabel(slReturn),
    leverage_warning: leverageWarning(leverage),
    fee_slippage_estimated: feeSlippagePct === null,
  };
}

export function simulateFuturesLeverage(
  signal: FuturesPaperSignalResponse,
  livePrice: number | null,
  leverage: LeverageOption,
): FuturesLeverageSimulation | null {
  if (signal.direction !== 'long' && signal.direction !== 'short') {
    return null;
  }
  return simulateFuturesLeverageFromPrices({
    direction: signal.direction,
    entryPrice: signal.current_price,
    takeProfit: signal.suggested_take_profit,
    stopLoss: signal.suggested_stop_loss,
    livePrice,
    leverage,
    estimatedFeeSlippagePct: signal.estimated_fee_impact,
  });
}
