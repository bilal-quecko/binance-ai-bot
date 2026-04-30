import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import type { RegimeAnalysisResponse } from '../lib/types';

interface RegimeAnalysisSectionProps {
  symbol: string;
  analysis: RegimeAnalysisResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.split('_').join(' ');
}

export function RegimeAnalysisSection({
  symbol,
  analysis,
  loading,
  refreshing,
  error,
}: RegimeAnalysisSectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select one symbol to classify the current market regime." tone="empty" />;
  }
  if (loading && analysis === null) {
    return <StatePanel title="Loading regime analysis" message={`Classifying current conditions for ${symbol}.`} tone="loading" />;
  }
  if (error) {
    return <StatePanel title="Regime analysis unavailable" message={error} tone="error" />;
  }
  if (analysis === null) {
    return <StatePanel title="Regime analysis unavailable" message={`No regime view is available yet for ${symbol}.`} tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Regime Analysis</p>
          <p className="mt-1 text-xs text-slate-400">Selected horizon {analysis.horizon.toUpperCase()}</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={analysis.data_state} message={analysis.status_message} />

      {analysis.data_state !== 'ready' ? (
        <StatePanel
          title="Regime view incomplete"
          message={analysis.status_message ?? `More stored or live history is needed to classify ${symbol}.`}
          tone="empty"
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Regime" value={humanize(analysis.regime_label)} helper="Primary current condition" />
            <MetricCard label="Confidence" value={`${analysis.confidence}/100`} helper="Evidence strength" />
            <MetricCard label="Behavior" value="Advisory" helper="See preferred behavior below" />
            <MetricCard label="Warnings" value={String(analysis.risk_warnings.length)} helper="Risk conditions detected" />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Preferred Trading Behavior</p>
            <p className="mt-3 text-sm leading-6 text-slate-300">{analysis.preferred_trading_behavior ?? 'No behavior guidance yet.'}</p>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Supporting Evidence</p>
              {analysis.supporting_evidence.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No strong regime evidence yet.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                  {analysis.supporting_evidence.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Avoid Conditions</p>
              {analysis.avoid_conditions.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No regime-specific avoid condition detected.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                  {analysis.avoid_conditions.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </div>
          </div>

          {analysis.risk_warnings.length > 0 ? (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-300">Risk Warnings</p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-amber-100/80">
                {analysis.risk_warnings.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
