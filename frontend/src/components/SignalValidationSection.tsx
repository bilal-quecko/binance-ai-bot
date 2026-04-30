import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { formatDecimal, pnlTone } from '../lib/format';
import type {
  EdgeReportResponse,
  GroupPerformanceMetric,
  HorizonQualityMetric,
  ModuleAttributionResponse,
  ReasonPerformanceMetric,
  SignalValidationResponse,
  SimilarSetupResponse,
} from '../lib/types';

interface SignalValidationSectionProps {
  symbol: string;
  validation: SignalValidationResponse | null;
  edgeReport: EdgeReportResponse | null;
  moduleAttribution: ModuleAttributionResponse | null;
  similarSetups: SimilarSetupResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function pct(value: string | null): string {
  return value === null ? '-' : `${formatDecimal(value, { maximumFractionDigits: 2 })}%`;
}

function expectancyTone(value: string | null): string {
  return value === null ? 'text-slate-200' : pnlTone(value);
}

function bestMetric(items: GroupPerformanceMetric[]): GroupPerformanceMetric | null {
  return [...items]
    .filter((item) => item.expectancy_pct !== null)
    .sort((a, b) => Number(b.expectancy_pct ?? 0) - Number(a.expectancy_pct ?? 0))[0] ?? null;
}

function worstMetric(items: GroupPerformanceMetric[]): GroupPerformanceMetric | null {
  return [...items]
    .filter((item) => item.expectancy_pct !== null)
    .sort((a, b) => Number(a.expectancy_pct ?? 0) - Number(b.expectancy_pct ?? 0))[0] ?? null;
}

function MetricList({ title, items }: { title: string; items: GroupPerformanceMetric[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">No measured pattern yet.</p>
        ) : (
          items.slice(0, 4).map((item) => (
            <div key={item.name} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
              <span className="text-slate-300">{item.name}</span>
              <span className={expectancyTone(item.expectancy_pct)}>{pct(item.expectancy_pct)} exp</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ReasonList({ title, items }: { title: string; items: ReasonPerformanceMetric[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Not enough evidence yet.</p>
        ) : (
          items.slice(0, 4).map((item) => (
            <div key={item.reason} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-slate-300">{item.reason}</span>
                <span className={expectancyTone(item.expectancy_pct)}>{pct(item.expectancy_pct)}</span>
              </div>
              <p className="mt-1 text-xs text-slate-500">{item.sample_size} evaluated samples</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function HorizonRows({ horizons }: { horizons: HorizonQualityMetric[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Win Rate And Expectancy By Horizon</p>
      <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
        {horizons.map((item) => (
          <div key={item.horizon} className="grid grid-cols-4 gap-3 border-b border-slate-800 px-3 py-2 text-sm last:border-b-0">
            <span className="font-medium text-slate-200">{item.horizon}</span>
            <span className="text-slate-400">{item.actionable_sample_size} samples</span>
            <span className="text-slate-300">{pct(item.win_rate_pct)} wins</span>
            <span className={expectancyTone(item.expectancy_pct)}>{pct(item.expectancy_pct)} exp</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SignalValidationSection({
  symbol,
  validation,
  edgeReport,
  moduleAttribution,
  similarSetups,
  loading,
  refreshing,
  error,
}: SignalValidationSectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to validate signal profitability." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Signal validation unavailable" message={error} tone="error" />;
  }
  if (loading && validation === null) {
    return <StatePanel title="Loading signal validation" message="Evaluating stored signals against forward price outcomes." tone="loading" />;
  }
  if (!validation || validation.total_signals === 0) {
    return <StatePanel title="No signal samples yet" message="Open the Signal tab or run paper mode so final signals can be stored for validation." tone="empty" />;
  }

  const bestSymbol = bestMetric(validation.performance_by_symbol);
  const worstSymbol = worstMetric(validation.performance_by_symbol);
  const bestConfidence = bestMetric(validation.performance_by_confidence_bucket);
  const worstRisk = worstMetric(validation.performance_by_risk_grade);
  const insufficient = validation.status === 'insufficient_data' || edgeReport?.status === 'insufficient_data';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Signal Validation & Edge Report</p>
          <p className="mt-1 text-sm text-slate-400">Checks whether stored signals for {symbol} worked after forward price movement, fees, and slippage.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      {insufficient ? (
        <StatePanel
          title="Insufficient evidence"
          message={edgeReport?.status_message ?? validation.status_message ?? 'More evaluated signal outcomes are needed before claiming an edge.'}
          tone="empty"
        />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Signal Samples" value={String(validation.total_signals)} helper={`${validation.actionable_signals} actionable`} />
        <MetricCard label="Ignored / Blocked" value={String(validation.ignored_or_blocked_signals)} helper="Signals not converted into entries" />
        <MetricCard label="Best Symbol" value={bestSymbol?.name ?? '-'} helper={bestSymbol ? `${pct(bestSymbol.expectancy_pct)} expectancy` : 'Waiting for data'} />
        <MetricCard label="Worst Symbol" value={worstSymbol?.name ?? '-'} helper={worstSymbol ? `${pct(worstSymbol.expectancy_pct)} expectancy` : 'Waiting for data'} />
      </div>

      <HorizonRows horizons={validation.horizons} />

      {similarSetups ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Similar Setup Outcome</p>
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">
                  {similarSetups.reliability_label.replace('_', ' ')}
                </p>
                <p className="mt-2 text-sm text-slate-400">{similarSetups.explanation}</p>
              </div>
              <div className="text-right text-xs text-slate-400">
                <p>{similarSetups.matching_sample_size} matching outcomes</p>
                <p className="mt-1">Best horizon {similarSetups.best_horizon ?? '-'}</p>
              </div>
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-3">
              {similarSetups.horizons.slice(0, 3).map((item) => (
                <div key={item.horizon} className="rounded-lg border border-slate-800 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-200">{item.horizon}</span>
                    <span className={expectancyTone(item.expectancy_pct)}>{pct(item.expectancy_pct)} exp</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.sample_size} samples, {pct(item.win_rate_pct)} wins
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <MetricList title="Confidence Bucket Performance" items={validation.performance_by_confidence_bucket} />
        <MetricList title="Risk Grade Performance" items={validation.performance_by_risk_grade} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ReasonList title="Top Useful Reasons" items={edgeReport?.useful_reasons ?? []} />
        <ReasonList title="Noisy Reasons" items={edgeReport?.noisy_reasons ?? []} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ReasonList title="Blocker Effectiveness" items={edgeReport?.protective_blockers ?? []} />
        <MetricList title="Module Attribution" items={moduleAttribution?.modules ?? []} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MetricCard label="Most Reliable Confidence" value={bestConfidence?.name ?? '-'} helper={bestConfidence ? `${pct(bestConfidence.expectancy_pct)} expectancy` : 'No reliable bucket yet'} />
        <MetricCard label="Weakest Risk Grade" value={worstRisk?.name ?? '-'} helper={worstRisk ? `${pct(worstRisk.expectancy_pct)} expectancy` : 'No weak grade measured yet'} />
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Deterministic Improvement Suggestions</p>
        <div className="mt-3 space-y-2">
          {(edgeReport?.suggestions ?? []).length === 0 ? (
            <p className="text-sm text-slate-500">No evidence-backed tuning suggestion yet.</p>
          ) : (
            edgeReport?.suggestions.map((suggestion) => (
              <div key={suggestion} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-300">
                {suggestion}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
