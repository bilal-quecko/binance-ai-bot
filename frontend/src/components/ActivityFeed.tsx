import { classNames, formatDateTime } from '../lib/format';
import type { ActivityFeedEntry } from '../lib/insights';

interface ActivityFeedProps {
  items: ActivityFeedEntry[];
}

export function ActivityFeed({ items }: ActivityFeedProps) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">No recent bot activity has been persisted yet.</p>;
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={`${item.eventTime}-${item.symbol}-${item.title}`} className="rounded-2xl border border-slate-800 bg-slate-950/55 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p
                className={classNames(
                  'text-sm font-semibold',
                  item.tone === 'positive' && 'text-emerald-300',
                  item.tone === 'negative' && 'text-rose-300',
                  item.tone === 'default' && 'text-white',
                )}
              >
                {item.title}
              </p>
              <p className="mt-1 text-sm text-slate-300">{item.detail}</p>
            </div>
            <div className="text-right text-xs text-slate-500">
              <p>{item.symbol || '-'}</p>
              <p className="mt-1">{formatDateTime(item.eventTime)}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
