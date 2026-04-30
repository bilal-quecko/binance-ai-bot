import { classNames, formatCurrency, formatDateTime, formatDecimal } from '../lib/format';
import type {
  BotStatusResponse,
  FusionSignalResponse,
  RegimeAnalysisResponse,
  SimilarSetupResponse,
  TradeEligibilityResponse,
  TradingAssistantResponse,
  WorkstationResponse,
} from '../lib/types';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';

interface V1SignalDashboardProps {
  selectedSymbol: string;
  workstation: WorkstationResponse | null;
  fusionSignal: FusionSignalResponse | null;
  tradingAssistant: TradingAssistantResponse | null;
  tradeEligibility: TradeEligibilityResponse | null;
  regimeAnalysis: RegimeAnalysisResponse | null;
  similarSetups: SimilarSetupResponse | null;
  botStatus: BotStatusResponse;
  loading: boolean;
  error: string | null;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.replace(/_/g, ' ');
}

function displaySignal(
  assistant: TradingAssistantResponse | null,
  fusion: FusionSignalResponse | null,
): 'BUY' | 'WAIT' | 'AVOID' | 'EXIT' {
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

function signalTone(signal: 'BUY' | 'WAIT' | 'AVOID' | 'EXIT'): string {
  if (signal === 'BUY') {
    return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100';
  }
  if (signal === 'EXIT' || signal === 'AVOID') {
    return 'border-rose-400/40 bg-rose-400/10 text-rose-100';
  }
  return 'border-amber-400/40 bg-amber-400/10 text-amber-100';
}

function confidenceValue(assistant: TradingAssistantResponse | null, fusion: FusionSignalResponse | null): string {
  if (assistant) {
    return `${assistant.confidence_score}%`;
  }
  if (fusion) {
    return `${fusion.confidence}%`;
  }
  return '-';
}

function riskValue(assistant: TradingAssistantResponse | null, fusion: FusionSignalResponse | null): string {
  return humanize(assistant?.risk_label ?? fusion?.risk_grade);
}

function bestHorizon(assistant: TradingAssistantResponse | null, fusion: FusionSignalResponse | null): string {
  return assistant?.best_timeframe ?? fusion?.preferred_horizon ?? '-';
}

function reliability(
  assistant: TradingAssistantResponse | null,
  similarSetups: SimilarSetupResponse | null,
): string {
  return humanize(assistant?.similar_setup?.reliability_label ?? similarSetups?.reliability_label ?? 'insufficient_data');
}

export function V1SignalDashboard({
  selectedSymbol,
  workstation,
  fusionSignal,
  tradingAssistant,
  tradeEligibility,
  regimeAnalysis,
  similarSetups,
  botStatus,
  loading,
  error,
}: V1SignalDashboardProps) {
  if (!selectedSymbol) {
    return <StatePanel title="Select a symbol" message="Choose a Binance Spot symbol to generate an AI-assisted signal view." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Signal view unavailable" message={error} tone="error" />;
  }
  if (loading && !workstation && !fusionSignal && !tradingAssistant) {
    return <StatePanel title="Loading signal view" message={`Preparing ${selectedSymbol} signal intelligence.`} tone="loading" />;
  }

  const finalSignal = displaySignal(tradingAssistant, fusionSignal);
  const whySignal = tradingAssistant?.simple_reason
    ?? fusionSignal?.top_reasons[0]
    ?? workstation?.explanation
    ?? 'No complete signal explanation is available yet.';
  const recommendedAction = tradingAssistant?.why_not_trade
    ?? tradeEligibility?.reason
    ?? (finalSignal === 'BUY' ? 'Paper automation may consider this only if the deterministic risk gate also agrees.' : 'Stay advisory-only until evidence improves.');
  const price = workstation?.last_price ?? workstation?.current_candle?.close ?? null;
  const paperStatus = botStatus.paper_only ? `Paper Mode - ${botStatus.state}` : botStatus.state;
  const reliabilityValue = reliability(tradingAssistant, similarSetups);
  const evidenceStrength = tradeEligibility?.evidence_strength ?? 'insufficient';
  const invalidationPoint = fusionSignal?.invalidation_hint
    ?? (tradingAssistant?.suggested_stop_loss ? formatDecimal(tradingAssistant.suggested_stop_loss) : null);

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">AI-Assisted Signal</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h2 className="text-3xl font-semibold text-white">{selectedSymbol}</h2>
              <span className={classNames('rounded-full border px-4 py-1.5 text-sm font-semibold uppercase tracking-[0.16em]', signalTone(finalSignal))}>
                {finalSignal}
              </span>
            </div>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">{whySignal}</p>
          </div>
          <div className="grid gap-2 text-xs text-slate-300 sm:min-w-64">
            {['Paper Mode', 'Advisory Only', 'No Guaranteed Profit', 'Data Driven Signals', 'Historical Validation Enabled'].map((item) => (
              <span key={item} className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-2 font-semibold uppercase tracking-[0.12em]">
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Current Price" value={price ? formatCurrency(price) : '-'} helper={formatDateTime(workstation?.last_market_event ?? null)} />
        <MetricCard label="Advisory Confidence" value={confidenceValue(tradingAssistant, fusionSignal)} helper={`Evidence ${evidenceStrength}`} />
        <MetricCard label="Best Time Horizon" value={bestHorizon(tradingAssistant, fusionSignal)} helper="Best opportunity window" />
        <MetricCard label="Smart Risk Filter" value={riskValue(tradingAssistant, fusionSignal)} helper={tradeEligibility?.status ? humanize(tradeEligibility.status) : 'Awaiting eligibility'} />
        <MetricCard label="Trade Eligibility" value={humanize(tradeEligibility?.status ?? 'insufficient_data')} helper={tradeEligibility?.reason ?? 'Need measured evidence'} />
        <MetricCard label="Market Condition" value={humanize(regimeAnalysis?.regime_label)} helper={regimeAnalysis ? `${regimeAnalysis.confidence}/100 confidence` : 'Regime pending'} />
        <MetricCard label="Similar Setup Reliability" value={reliabilityValue} helper={`${tradingAssistant?.similar_setup?.matching_sample_size ?? similarSetups?.matching_sample_size ?? 0} measured matches`} />
        <MetricCard label="Paper Mode Status" value={paperStatus} helper={botStatus.symbol ? `Runtime ${botStatus.symbol}` : 'No active runtime'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr,0.9fr]">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Recommended Action</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">{recommendedAction}</p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Invalidation Point</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            {invalidationPoint ?? 'No clear invalidation point is available yet.'}
          </p>
        </div>
      </div>

      {fusionSignal?.warnings?.length ? (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-200">Active Signal Warnings</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {fusionSignal.warnings.slice(0, 4).map((warning) => (
              <span key={warning} className="rounded-full border border-amber-400/30 px-3 py-1 text-xs text-amber-100">
                {warning}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
