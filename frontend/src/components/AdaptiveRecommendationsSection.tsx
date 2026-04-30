import { StatePanel } from './StatePanel';
import type { AdaptiveRecommendationResponse } from '../lib/types';

interface AdaptiveRecommendationsSectionProps {
  symbol: string;
  recommendations: AdaptiveRecommendationResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function label(value: string): string {
  return value.split('_').join(' ');
}

function strengthTone(strength: string): string {
  if (strength === 'strong' || strength === 'promising') {
    return 'text-emerald-300';
  }
  if (strength === 'weak' || strength === 'insufficient') {
    return 'text-amber-300';
  }
  return 'text-slate-300';
}

export function AdaptiveRecommendationsSection({
  symbol,
  recommendations,
  loading,
  refreshing,
  error,
}: AdaptiveRecommendationsSectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to review adaptive recommendations." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Adaptive recommendations unavailable" message={error} tone="error" />;
  }
  if (loading && !recommendations) {
    return <StatePanel title="Loading adaptive recommendations" message="Checking measured signal outcomes for threshold suggestions." tone="loading" />;
  }
  if (!recommendations) {
    return <StatePanel title="No adaptive recommendation data" message={`No adaptive recommendation data is available for ${symbol} yet.`} tone="empty" />;
  }
  if (recommendations.status === 'insufficient_data') {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Adaptive Recommendations</p>
            <p className="mt-1 text-sm text-slate-400">Evidence-based threshold suggestions for paper mode.</p>
          </div>
          {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
        </div>
        <StatePanel
          title="Insufficient evidence"
          message={recommendations.status_message ?? 'More measured signal outcomes are needed before recommending settings changes.'}
          tone="empty"
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Adaptive Recommendations</p>
          <p className="mt-1 text-sm text-slate-400">Evidence-based threshold and rule suggestions for paper mode.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className="space-y-3">
        {recommendations.recommendations.map((item) => (
          <div key={item.recommendation_id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold uppercase text-white">{label(item.recommendation_type)}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                  {label(item.affected_scope)} · {item.affected_value}
                </p>
              </div>
              <div className="text-right text-xs">
                <p className={strengthTone(item.evidence_strength)}>Evidence {item.evidence_strength}</p>
                <p className="mt-1 text-slate-500">
                  {item.sample_size}/{item.minimum_sample_required} samples
                </p>
              </div>
            </div>
            <p className="mt-3 text-sm text-slate-300">{item.suggested_change}</p>
            <p className="mt-2 text-sm text-slate-400">{item.expected_benefit}</p>
            <p className="mt-2 text-xs text-slate-500">{item.evidence_summary}</p>
            {item.warnings.length > 0 ? (
              <div className="mt-3 space-y-1">
                {item.warnings.map((warning) => (
                  <p key={warning} className="text-xs text-amber-300">{warning}</p>
                ))}
              </div>
            ) : null}
            <p className="mt-3 text-xs text-slate-500">
              Manual review required: {item.do_not_auto_apply ? 'yes' : 'no'}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
