import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { formatCurrency } from '../lib/format';
import type { TechnicalAnalysisResponse } from '../lib/types';

interface TechnicalAnalysisSectionProps {
  symbol: string;
  analysis: TechnicalAnalysisResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function formatLevelList(levels: string[]): string {
  if (levels.length === 0) {
    return 'Not enough structure yet';
  }
  return levels.map((level) => formatCurrency(level)).join(', ');
}

function humanizeAgreement(value: TechnicalAnalysisResponse['multi_timeframe_agreement']): string {
  if (!value) {
    return '-';
  }
  return value.split('_').join(' ');
}

export function TechnicalAnalysisSection({
  symbol,
  analysis,
  loading,
  refreshing,
  error,
}: TechnicalAnalysisSectionProps) {
  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load symbol-scoped technical analysis."
        tone="empty"
      />
    );
  }

  if (loading && analysis === null) {
    return (
      <StatePanel
        title="Loading technical analysis"
        message={`Reading recent candles and structure for ${symbol}.`}
        tone="loading"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        title="Technical analysis unavailable"
        message={error}
        tone="error"
      />
    );
  }

  if (analysis === null) {
    return (
      <StatePanel
        title="Technical analysis unavailable"
        message={`No technical view is available yet for ${symbol}.`}
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Technical Analysis</p>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <DataStateIndicator dataState={analysis.data_state} message={analysis.status_message} />

      {analysis.data_state !== 'ready' ? (
        <StatePanel
          title="Technical view incomplete"
          message={analysis.status_message ?? `Technical analysis still needs more live structure for ${symbol}.`}
          tone="empty"
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Trend" value={analysis.trend_direction ?? '-'} helper="Current direction" />
            <MetricCard
              label="Trend Strength"
              value={analysis.trend_strength ?? '-'}
              helper={analysis.trend_strength_score !== null ? `${analysis.trend_strength_score}/100` : 'No score'}
            />
            <MetricCard label="Momentum" value={analysis.momentum_state ?? '-'} helper="Recent impulse state" />
            <MetricCard label="Volatility" value={analysis.volatility_regime ?? '-'} helper="ATR-based regime" />
            <MetricCard
              label="Breakout View"
              value={analysis.breakout_readiness ?? '-'}
              helper={analysis.breakout_bias && analysis.breakout_bias !== 'none' ? `${analysis.breakout_bias} bias` : 'No directional bias'}
            />
            <MetricCard label="Reversal Risk" value={analysis.reversal_risk ?? '-'} helper="Exhaustion readiness" />
            <MetricCard
              label="MTF Agreement"
              value={humanizeAgreement(analysis.multi_timeframe_agreement)}
              helper="1m / 5m / 15m summary"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Support</p>
              <p className="mt-3 text-sm leading-6 text-slate-200">{formatLevelList(analysis.support_levels)}</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Resistance</p>
              <p className="mt-3 text-sm leading-6 text-slate-200">{formatLevelList(analysis.resistance_levels)}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Multi-Timeframe Summary</p>
            {analysis.timeframe_summaries.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">Not enough history yet for 5m / 15m aggregation.</p>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                {analysis.timeframe_summaries.map((summary) => (
                  <div key={summary.timeframe} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{summary.timeframe}</p>
                    <p className="mt-2 text-sm font-medium text-white">{summary.trend_direction}</p>
                    <p className="mt-1 text-xs text-slate-400">{summary.trend_strength}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Technical Explanation</p>
            <p className="mt-3 text-sm leading-6 text-slate-300">{analysis.explanation ?? 'No explanation yet.'}</p>
          </div>
        </div>
      )}
    </div>
  );
}
