import { useEffect, useState } from 'react';
import { getBlockerAnalytics } from '../lib/api';
import type { BlockerAnalyticsResponse } from '../lib/types';
import { formatReasonCodes } from '../lib/format';
import { StatePanel } from './StatePanel';

interface WhyNoTradePanelProps {
  symbol: string;
}

function categoryLabel(category: string): string {
  return category.replace(/_/g, ' ');
}

export function WhyNoTradePanel({ symbol }: WhyNoTradePanelProps) {
  const [data, setData] = useState<BlockerAnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) {
      setData(null);
      return;
    }
    void getBlockerAnalytics(symbol, 75)
      .then((nextData) => {
        setData(nextData);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Unable to load blocker analytics.');
      });
  }, [symbol]);

  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to inspect no-trade blockers." tone="empty" />;
  }

  const topGroup = data?.groups[0] ?? null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Why No Trade?</p>
          <h3 className="mt-1 text-base font-semibold text-white">{topGroup ? categoryLabel(topGroup.category) : 'No recent blocker'}</h3>
          <p className="mt-2 text-sm text-slate-400">{data?.explanation ?? 'Recent blocker analytics appear after trade attempts are persisted.'}</p>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-right">
          <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Recent Events</p>
          <p className="text-lg font-semibold text-white">{data?.total_events ?? 0}</p>
        </div>
      </div>
      <p className="mt-3 rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-300">
        {data?.next_suggested_action ?? 'Run the paper bot to collect signal, risk, execution, and blocked events.'}
      </p>
      {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
      {data?.recent_blockers.length ? (
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {data.recent_blockers.slice(0, 3).map((blocker) => (
            <div key={`${blocker.event_time}-${blocker.event_type}`} className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{categoryLabel(blocker.category)}</p>
              <p className="mt-2 text-sm text-slate-300">{formatReasonCodes(blocker.reason_codes)}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
