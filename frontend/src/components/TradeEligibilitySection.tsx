import { StatePanel } from './StatePanel';
import type { TradeEligibilityResponse } from '../lib/types';

interface TradeEligibilitySectionProps {
  symbol: string;
  eligibility: TradeEligibilityResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

function statusLabel(status: TradeEligibilityResponse['status']): string {
  if (status === 'not_eligible') {
    return 'not eligible';
  }
  return status.replace('_', ' ');
}

function statusTone(status: TradeEligibilityResponse['status']): string {
  if (status === 'eligible') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100';
  }
  if (status === 'not_eligible') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
  }
  if (status === 'insufficient_data') {
    return 'border-slate-700 bg-slate-900/70 text-slate-200';
  }
  return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
}

function EvidenceList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <div className="mt-3 space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">{empty}</p>
        ) : (
          items.map((item) => (
            <div key={item} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-300">
              {item}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function TradeEligibilitySection({
  symbol,
  eligibility,
  loading,
  refreshing,
  error,
}: TradeEligibilitySectionProps) {
  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to check paper trade eligibility." tone="empty" />;
  }
  if (error) {
    return <StatePanel title="Trade eligibility unavailable" message={error} tone="error" />;
  }
  if (loading && !eligibility) {
    return <StatePanel title="Loading trade eligibility" message="Checking current signal evidence." tone="loading" />;
  }
  if (!eligibility) {
    return <StatePanel title="No eligibility data" message={`No trade eligibility result is available for ${symbol} yet.`} tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trade Eligibility</p>
          <p className="mt-2 text-sm text-slate-400">Advisory-only check for paper automation consideration.</p>
        </div>
        {refreshing ? <span className="text-xs text-slate-400">Refreshing...</span> : null}
      </div>

      <div className={`rounded-lg border p-4 ${statusTone(eligibility.status)}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-lg font-semibold uppercase">{statusLabel(eligibility.status)}</p>
          <p className="text-xs uppercase tracking-[0.16em]">Evidence {eligibility.evidence_strength}</p>
        </div>
        <p className="mt-2 text-sm leading-6">{eligibility.reason}</p>
        {eligibility.status === 'insufficient_data' ? (
          <p className="mt-2 text-xs opacity-80">More measured signal outcomes are needed before the bot can honestly judge this setup.</p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Current Evidence</p>
          <div className="mt-3 space-y-3 text-sm text-slate-300">
            <p>{eligibility.similar_setup_summary}</p>
            <p>{eligibility.regime_summary}</p>
            <p>{eligibility.fee_slippage_summary}</p>
            <p>Minimum confidence: {eligibility.minimum_confidence_threshold}%</p>
            <p>Preferred horizon: {eligibility.preferred_horizon ?? '-'}</p>
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Blockers</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">{eligibility.blocker_summary}</p>
          <p className="mt-3 text-xs text-slate-500">
            Paper only: {eligibility.paper_only ? 'yes' : 'no'} · Advisory only: {eligibility.advisory_only ? 'yes' : 'no'}
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <EvidenceList
          title="Required Confirmations"
          items={eligibility.required_confirmations}
          empty="No extra confirmation is required by the current evidence gate."
        />
        <EvidenceList
          title="Conditions To Avoid"
          items={eligibility.conditions_to_avoid}
          empty="No specific avoid condition is active."
        />
      </div>

      <EvidenceList title="Warnings" items={eligibility.warnings} empty="No active warnings." />
    </div>
  );
}
