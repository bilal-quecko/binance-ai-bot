import { DataStateIndicator } from './DataStateIndicator';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';
import { classNames, formatCurrency, formatDateTime, formatDecimal } from '../lib/format';
import { buildPatternCoverageSummary } from '../lib/workstation-ux.js';
import type { PatternAnalysisResponse, PatternHorizon } from '../lib/types';

const HORIZONS: PatternHorizon[] = ['1d', '3d', '7d', '14d', '30d'];

interface PatternAnalysisSectionProps {
  symbol: string;
  selectedHorizon: PatternHorizon;
  analysis: PatternAnalysisResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  onSelectHorizon: (horizon: PatternHorizon) => void;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return value.split('_').join(' ');
}

export function PatternAnalysisSection({
  symbol,
  selectedHorizon,
  analysis,
  loading,
  refreshing,
  error,
  onSelectHorizon,
}: PatternAnalysisSectionProps) {
  const coverage = analysis ? buildPatternCoverageSummary(analysis) : null;
  const isPreliminary = Boolean(analysis && (analysis.partial_coverage || analysis.data_state !== 'ready'));

  if (!symbol) {
    return (
      <StatePanel
        title="No symbol selected"
        message="Select one symbol to load symbol-scoped pattern analysis."
        tone="empty"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Pattern Analysis</p>
          <p className="mt-1 text-xs text-slate-400">Selected horizon {selectedHorizon.toUpperCase()}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {HORIZONS.map((horizon) => (
            <button
              key={horizon}
              type="button"
              onClick={() => onSelectHorizon(horizon)}
              className={classNames(
                'rounded-xl border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] transition',
                selectedHorizon === horizon
                  ? 'border-sky-400/60 bg-sky-400/10 text-sky-100'
                  : 'border-slate-700 bg-slate-950/40 text-slate-300 hover:border-slate-500 hover:text-white',
              )}
            >
              {horizon.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && analysis === null ? (
        <StatePanel
          title="Loading pattern analysis"
          message={`Reading ${selectedHorizon.toUpperCase()} close-price behavior for ${symbol}.`}
          tone="loading"
        />
      ) : error ? (
        <StatePanel title="Pattern analysis unavailable" message={error} tone="error" />
      ) : analysis === null ? (
        <StatePanel
          title="Pattern analysis unavailable"
          message={`No pattern view is available yet for ${symbol}.`}
          tone="empty"
        />
      ) : (
        <>
          <div className="flex items-center justify-between gap-3">
            <DataStateIndicator dataState={analysis.data_state} message={analysis.status_message} />
            {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
          </div>

          {analysis.data_state !== 'ready' && !analysis.partial_coverage ? (
            <StatePanel
              title="Pattern view incomplete"
              message={analysis.status_message ?? `More ${selectedHorizon.toUpperCase()} history is needed for ${symbol}.`}
              tone="empty"
            />
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Direction" value={analysis.overall_direction ?? '-'} helper={analysis.horizon.toUpperCase()} />
                <MetricCard
                  label="Net Return"
                  value={analysis.net_return_pct !== null ? `${formatDecimal(analysis.net_return_pct)}%` : '-'}
                  helper={`${analysis.up_moves} up / ${analysis.down_moves} down / ${analysis.flat_moves} flat${isPreliminary ? ' · preliminary' : ''}`}
                />
                <MetricCard
                  label="Volatility"
                  value={analysis.realized_volatility_pct !== null ? `${formatDecimal(analysis.realized_volatility_pct)}%` : '-'}
                  helper={isPreliminary ? 'Preliminary realized volatility from partial history' : 'Realized over selected horizon'}
                />
                <MetricCard
                  label="Max Drawdown"
                  value={analysis.max_drawdown_pct !== null ? `${formatDecimal(analysis.max_drawdown_pct)}%` : '-'}
                  helper={isPreliminary ? 'Preliminary peak-to-trough read from partial history' : 'Peak-to-trough over horizon'}
                />
                <MetricCard
                  label="Trend Character"
                  value={humanize(analysis.trend_character)}
                  helper="Persistence vs choppiness"
                />
                <MetricCard
                  label="Breakout Tendency"
                  value={humanize(analysis.breakout_tendency)}
                  helper="Breakout vs range behavior"
                />
                <MetricCard
                  label="Reversal Tendency"
                  value={humanize(analysis.reversal_tendency)}
                  helper="Observed reversal readiness"
                />
                <MetricCard
                  label="Coverage Window"
                  value={coverage?.value ?? 'Requested range'}
                  helper={coverage?.helper ?? 'No coverage yet'}
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Up vs Down Behavior</p>
                  <p className="mt-3 text-sm leading-6 text-slate-200">
                    Up moves {analysis.up_move_ratio_pct !== null ? `${formatDecimal(analysis.up_move_ratio_pct)}%` : '-'} | down moves {analysis.down_move_ratio_pct !== null ? `${formatDecimal(analysis.down_move_ratio_pct)}%` : '-'}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Coverage Status</p>
                  <p className="mt-3 text-sm leading-6 text-slate-200">
                    {analysis.partial_coverage
                      ? `This ${analysis.horizon.toUpperCase()} read is preliminary because only part of the requested history is available so far.`
                      : 'Coverage is sufficient for the selected horizon.'}
                  </p>
                  {analysis.coverage_start && analysis.coverage_end ? (
                    <p className="mt-2 text-xs text-slate-500">
                      Window {formatDateTime(analysis.coverage_start)} {'->'} {formatDateTime(analysis.coverage_end)}
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Pattern Summary</p>
                <p className="mt-3 text-sm leading-6 text-slate-300">{analysis.explanation ?? 'No pattern summary yet.'}</p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
