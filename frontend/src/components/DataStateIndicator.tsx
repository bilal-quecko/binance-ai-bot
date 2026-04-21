import { classNames } from '../lib/format';
import type { WorkstationDataState } from '../lib/types';

interface DataStateIndicatorProps {
  dataState: WorkstationDataState;
  message: string | null;
  compact?: boolean;
}

function dataStateTone(dataState: WorkstationDataState): string {
  if (dataState === 'ready') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  }
  if (dataState === 'degraded_storage') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
  }
  return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
}

function dataStateLabel(dataState: WorkstationDataState): string {
  if (dataState === 'ready') {
    return 'Ready';
  }
  if (dataState === 'waiting_for_runtime') {
    return 'Waiting for Runtime';
  }
  if (dataState === 'waiting_for_history') {
    return 'Waiting for History';
  }
  return 'Degraded Storage';
}

export function DataStateIndicator({ dataState, message, compact = false }: DataStateIndicatorProps) {
  return (
    <div className={classNames('rounded-2xl border px-4 py-3', dataStateTone(dataState), compact && 'px-3 py-2')}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.16em]">Data State</span>
        <span className="rounded-full bg-slate-950/40 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-current">
          {dataStateLabel(dataState)}
        </span>
      </div>
      {message ? <p className="mt-2 text-sm leading-6">{message}</p> : null}
    </div>
  );
}
