import { classNames, formatDateTime } from '../lib/format';
import type { PersistenceHealthSummary } from '../lib/types';

interface PersistenceHealthCardProps {
  persistence: PersistenceHealthSummary;
  compact?: boolean;
}

function tone(state: PersistenceHealthSummary['persistence_state']): string {
  if (state === 'healthy') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  }
  if (state === 'recovered_from_persistence') {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-200';
  }
  if (state === 'degraded_in_memory_only') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
  }
  return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
}

function label(state: PersistenceHealthSummary['persistence_state']): string {
  if (state === 'healthy') {
    return 'Healthy Persistence';
  }
  if (state === 'recovered_from_persistence') {
    return 'Recovered Session';
  }
  if (state === 'degraded_in_memory_only') {
    return 'In-Memory Only';
  }
  return 'Persistence Unavailable';
}

function storageScope(state: PersistenceHealthSummary['persistence_state']): string {
  if (state === 'healthy') {
    return 'Current paper session is being persisted.';
  }
  if (state === 'recovered_from_persistence') {
    return 'Recovered paper session remains visible from persisted storage.';
  }
  if (state === 'degraded_in_memory_only') {
    return 'Current paper session is only protected in memory until persistence recovers.';
  }
  return 'No meaningful persisted session state is currently available.';
}

export function PersistenceHealthCard({
  persistence,
  compact = false,
}: PersistenceHealthCardProps) {
  return (
    <div className={classNames('rounded-2xl border px-4 py-3', tone(persistence.persistence_state), compact && 'px-3 py-2')}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.16em]">Persistence</span>
        <span className="rounded-full bg-slate-950/40 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-current">
          {label(persistence.persistence_state)}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6">{persistence.persistence_message}</p>
      <div className="mt-3 grid gap-2 text-xs text-current/80 sm:grid-cols-2">
        <p>{storageScope(persistence.persistence_state)}</p>
        <p>
          Last persisted OK: {formatDateTime(persistence.persistence_last_ok_at) || 'Not recorded yet'}
          {persistence.recovery_source ? ` | Source ${persistence.recovery_source}` : ''}
        </p>
      </div>
    </div>
  );
}
