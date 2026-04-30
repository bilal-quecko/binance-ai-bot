import type { OpportunityResponse } from '../lib/types';
import { StatePanel } from './StatePanel';

interface OpportunityScannerSectionProps {
  opportunities: OpportunityResponse[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

export function OpportunityScannerSection({
  opportunities,
  loading,
  refreshing,
  error,
  selectedSymbol,
  onSelectSymbol,
}: OpportunityScannerSectionProps) {
  if (loading && opportunities.length === 0) {
    return <StatePanel title="Loading opportunities" message="Ranking the best USDT Spot symbols from available history." tone="loading" />;
  }
  if (error) {
    return <StatePanel title="Opportunity scanner unavailable" message={error} tone="error" />;
  }
  if (opportunities.length === 0) {
    return <StatePanel title="No opportunities yet" message="No ranked symbols are available from stored history yet." tone="empty" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Best Opportunities Right Now</p>
          <p className="mt-2 text-sm text-slate-300">Click a symbol to load it into the workstation. This scanner is advisory only.</p>
        </div>
        <p className="text-xs text-slate-400">{refreshing ? 'Refreshing...' : `${opportunities.length} ranked`}</p>
      </div>

      <div className="space-y-3">
        {opportunities.map((item) => (
          <button
            key={item.symbol}
            type="button"
            onClick={() => onSelectSymbol(item.symbol)}
            className={`w-full rounded-2xl border px-4 py-3 text-left transition ${selectedSymbol === item.symbol ? 'border-sky-500 bg-sky-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-white">{item.symbol}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">{item.suggested_action.replace('_', ' ')} · {item.confidence} confidence</p>
                <p className="mt-2 text-sm text-slate-300">{item.reason}</p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold text-white">{item.score}</p>
                <p className="text-xs text-slate-400">{item.data_state}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
