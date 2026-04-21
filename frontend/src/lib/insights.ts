import type { EventItem, PositionItem, TradeItem } from './types';

export interface BotIntelligence {
  currentState: string;
  lastAction: string;
  lastSymbol: string;
  reasonForLastAction: string;
  currentTrendBias: string;
  riskState: string;
}

export interface TrustMetricsSummary {
  winningTrades: number;
  losingTrades: number;
  avgGain: number;
  avgLoss: number;
  sampleSize: number;
  sampleSizeConfidence: string;
}

export interface ActivityFeedEntry {
  title: string;
  detail: string;
  symbol: string;
  eventTime: string;
  tone: 'default' | 'positive' | 'negative';
}

export interface DerivedNarrative {
  label: string;
  text: string;
}

function getReasonCodes(payload: Record<string, unknown>): string[] {
  const value = payload.reason_codes;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function humanizeReasonCode(reasonCode: string): string {
  return reasonCode
    .split('_')
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(' ');
}

function formatReasonCodes(payload: Record<string, unknown>): string {
  const reasonCodes = getReasonCodes(payload);
  if (reasonCodes.length === 0) {
    return 'No explicit reason recorded';
  }
  return reasonCodes.map(humanizeReasonCode).join(', ');
}

function getString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' ? value : null;
}

function getLastSignalEvent(events: EventItem[]): EventItem | undefined {
  return [...events].reverse().find((event) => event.event_type === 'signal_generated');
}

function getLastRiskEvent(events: EventItem[]): EventItem | undefined {
  return [...events].reverse().find((event) => event.event_type === 'risk_decision');
}

function getLastActionEvent(events: EventItem[]): EventItem | undefined {
  return [...events]
    .reverse()
    .find((event) => event.event_type === 'fill' || event.event_type === 'execution_result' || event.event_type === 'signal_generated');
}

function findLatestEventForSymbol(events: EventItem[], eventType: string, symbol: string): EventItem | undefined {
  return [...events].reverse().find((event) => event.event_type === eventType && event.symbol === symbol);
}

function inferNextWatchCondition(signalEvent: EventItem | undefined, riskEvent: EventItem | undefined): string {
  const signalReasons = getReasonCodes(signalEvent?.payload ?? {});
  const signalSide = getString(signalEvent?.payload ?? {}, 'side');
  const riskDecision = getString(riskEvent?.payload ?? {}, 'decision');

  if (signalSide === 'BUY') {
    return 'watch for an exit trigger, stop-loss, or take-profit condition';
  }
  if (signalSide === 'SELL') {
    return 'watch for a fresh bullish setup before considering a new entry';
  }
  if (signalReasons.includes('REGIME_NOT_TREND')) {
    return 'watch for trend confirmation before acting';
  }
  if (signalReasons.includes('VOL_TOO_LOW')) {
    return 'watch for volatility to expand before acting';
  }
  if (signalReasons.includes('MICROSTRUCTURE_UNHEALTHY')) {
    return 'watch for spread and order-book conditions to normalize';
  }
  if (riskDecision === 'reject') {
    return 'watch for risk limits to clear before acting';
  }
  if (riskDecision === 'resize') {
    return 'watch whether the resized position develops as expected';
  }
  return 'watch for the next validated signal';
}

export function deriveBotIntelligence(positions: PositionItem[], trades: TradeItem[], events: EventItem[]): BotIntelligence {
  const latestTrade = [...trades]
    .reverse()
    .find((trade) => trade.status === 'executed');
  const lastSignalEvent = getLastSignalEvent(events);
  const lastRiskEvent = getLastRiskEvent(events);
  const lastActionEvent = getLastActionEvent(events);
  const lastActionPayload = lastActionEvent?.payload ?? {};

  let currentState = 'Watching';
  if (positions.length > 0) {
    currentState = 'In Trade';
  } else if (latestTrade?.side === 'SELL') {
    currentState = 'Exited';
  }

  let lastAction = 'Waiting';
  if (lastActionEvent?.event_type === 'fill') {
    const fillSide = lastActionEvent.message.split('fill_side=').at(1) ?? 'FILL';
    lastAction = `${fillSide} filled`;
  } else if (lastActionEvent?.event_type === 'execution_result') {
    const side = getString(lastActionPayload, 'side') ?? 'Order';
    const status = getString(lastActionPayload, 'status') ?? 'processed';
    lastAction = `${side} ${status}`;
  } else if (lastActionEvent?.event_type === 'signal_generated') {
    const side = getString(lastActionPayload, 'side') ?? 'HOLD';
    lastAction = `${side} signal`;
  }

  const lastSymbol = lastActionEvent?.symbol || positions[0]?.symbol || latestTrade?.symbol || '-';

  let currentTrendBias = 'Neutral';
  const lastSignalSide = getString(lastSignalEvent?.payload ?? {}, 'side');
  if (lastSignalSide === 'BUY') {
    currentTrendBias = 'Bullish';
  } else if (lastSignalSide === 'SELL') {
    currentTrendBias = 'Bearish';
  } else if (lastSignalEvent) {
    const reasons = getReasonCodes(lastSignalEvent.payload);
    if (reasons.includes('REGIME_NOT_TREND')) {
      currentTrendBias = 'Sideways';
    } else if (reasons.includes('VOL_TOO_LOW') || reasons.includes('MICROSTRUCTURE_UNHEALTHY')) {
      currentTrendBias = 'Cautious';
    }
  }

  let riskState = 'Idle';
  if (lastRiskEvent) {
    const decision = getString(lastRiskEvent.payload, 'decision') ?? 'skipped';
    const reasons = formatReasonCodes(lastRiskEvent.payload);
    if (decision === 'approve') {
      riskState = `Approved - ${reasons}`;
    } else if (decision === 'resize') {
      riskState = `Resized - ${reasons}`;
    } else if (decision === 'reject') {
      riskState = `Blocked - ${reasons}`;
    } else {
      riskState = `Idle - ${reasons}`;
    }
  }

  const reasonForLastAction =
    lastActionEvent?.event_type === 'signal_generated' || lastActionEvent?.event_type === 'execution_result'
      ? formatReasonCodes(lastActionPayload)
      : latestTrade?.reason_codes.map(humanizeReasonCode).join(', ') || 'No explicit reason recorded';

  return {
    currentState,
    lastAction,
    lastSymbol,
    reasonForLastAction,
    currentTrendBias,
    riskState,
  };
}

export function deriveTrustMetrics(trades: TradeItem[]): TrustMetricsSummary {
  const closingTrades = trades.filter((trade) => trade.status === 'executed' && trade.side === 'SELL');
  const winningTrades = closingTrades.filter((trade) => Number(trade.realized_pnl) > 0);
  const losingTrades = closingTrades.filter((trade) => Number(trade.realized_pnl) < 0);

  const avgGain =
    winningTrades.length > 0
      ? winningTrades.reduce((sum, trade) => sum + Number(trade.realized_pnl), 0) / winningTrades.length
      : 0;
  const avgLoss =
    losingTrades.length > 0
      ? losingTrades.reduce((sum, trade) => sum + Number(trade.realized_pnl), 0) / losingTrades.length
      : 0;

  let sampleSizeConfidence = 'Low';
  if (closingTrades.length >= 30) {
    sampleSizeConfidence = 'Higher';
  } else if (closingTrades.length >= 10) {
    sampleSizeConfidence = 'Moderate';
  } else if (closingTrades.length >= 5) {
    sampleSizeConfidence = 'Building';
  }

  return {
    winningTrades: winningTrades.length,
    losingTrades: losingTrades.length,
    avgGain,
    avgLoss,
    sampleSize: closingTrades.length,
    sampleSizeConfidence,
  };
}

export function deriveActivityFeed(events: EventItem[]): ActivityFeedEntry[] {
  return [...events]
    .reverse()
    .map((event) => {
      const reasonSummary = formatReasonCodes(event.payload);
      let title = event.event_type;
      let detail = event.message;
      let tone: ActivityFeedEntry['tone'] = 'default';

      if (event.event_type === 'signal_generated') {
        const side = getString(event.payload, 'side') ?? 'HOLD';
        title = `${side} signal`;
        detail = reasonSummary;
        tone = side === 'BUY' ? 'positive' : side === 'SELL' ? 'negative' : 'default';
      } else if (event.event_type === 'risk_decision') {
        const decision = getString(event.payload, 'decision') ?? 'skipped';
        title = `Risk ${decision}`;
        detail = reasonSummary;
        tone = decision === 'approve' ? 'positive' : decision === 'reject' ? 'negative' : 'default';
      } else if (event.event_type === 'execution_result') {
        const status = getString(event.payload, 'status') ?? 'skipped';
        const side = getString(event.payload, 'side') ?? 'order';
        title = `${side} ${status}`;
        detail = reasonSummary;
        tone = status === 'executed' ? 'positive' : status === 'rejected' ? 'negative' : 'default';
      } else if (event.event_type === 'fill') {
        title = 'Order fill';
        const realizedPnl = getString(event.payload, 'realized_pnl');
        detail = realizedPnl ? `Realized PnL ${realizedPnl}` : 'Execution filled';
        tone = realizedPnl && Number(realizedPnl) < 0 ? 'negative' : 'positive';
      } else if (event.event_type === 'pnl_snapshot') {
        title = 'Portfolio snapshot';
        const equity = getString(event.payload, 'equity');
        detail = equity ? `Equity ${equity}` : event.message;
      }

      return {
        title,
        detail,
        symbol: event.symbol,
        eventTime: event.event_time,
        tone,
      };
    });
}

export function deriveNarrative(events: EventItem[]): DerivedNarrative {
  const latestSignal = getLastSignalEvent(events);
  const symbol = latestSignal?.symbol || getLastActionEvent(events)?.symbol || '-';
  const signalForSymbol = symbol !== '-' ? findLatestEventForSymbol(events, 'signal_generated', symbol) : latestSignal;
  const riskForSymbol = symbol !== '-' ? findLatestEventForSymbol(events, 'risk_decision', symbol) : getLastRiskEvent(events);
  const executionForSymbol = symbol !== '-' ? findLatestEventForSymbol(events, 'execution_result', symbol) : undefined;
  const fillForSymbol = symbol !== '-' ? findLatestEventForSymbol(events, 'fill', symbol) : undefined;

  const signalSide = getString(signalForSymbol?.payload ?? {}, 'side') ?? 'HOLD';
  const signalReasons = formatReasonCodes(signalForSymbol?.payload ?? {});
  const riskDecision = getString(riskForSymbol?.payload ?? {}, 'decision') ?? 'skipped';
  const executionStatus = getString(executionForSymbol?.payload ?? {}, 'status') ?? 'skipped';
  const nextWatchCondition = inferNextWatchCondition(signalForSymbol, riskForSymbol);

  let actionPhrase = `${signalSide} signal`;
  if (fillForSymbol) {
    const fillSide = fillForSymbol.message.split('fill_side=').at(1) ?? signalSide;
    actionPhrase = `${fillSide} fill`;
  } else if (executionForSymbol) {
    const executionSide = getString(executionForSymbol.payload, 'side') ?? signalSide;
    actionPhrase = `${executionSide} execution`;
  }

  const riskPhrase =
    riskDecision === 'approve'
      ? 'Risk approved it'
      : riskDecision === 'resize'
        ? 'Risk resized it'
        : riskDecision === 'reject'
          ? 'Risk rejected it'
          : 'Risk skipped action';

  const executionPhrase =
    executionStatus === 'executed'
      ? 'and execution completed'
      : executionStatus === 'rejected'
        ? 'but execution was rejected'
        : executionStatus === 'skipped'
          ? 'and no execution was sent'
          : `and execution status was ${executionStatus}`;

  return {
    label: 'Derived summary',
    text:
      symbol === '-'
        ? 'Derived summary: no recent persisted decision is available yet, so the bot is still waiting for a validated setup.'
        : `Derived summary: the bot most recently produced a ${actionPhrase} on ${symbol} because ${signalReasons.toLowerCase()}; ${riskPhrase.toLowerCase()} ${executionPhrase}, and the next watch condition is to ${nextWatchCondition}.`,
  };
}
