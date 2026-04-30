import { formatDateTime } from '../lib/format';
import type {
  BackfillStatusResponse,
  BotStatusResponse,
  HealthResponse,
  PersistenceHealthSummary,
  WorkstationResponse,
} from '../lib/types';
import { MetricCard } from './MetricCard';

interface DiagnosticsPanelProps {
  selectedSymbol: string;
  health: HealthResponse | null;
  status: BotStatusResponse;
  workstation: WorkstationResponse | null;
  backfillStatus: BackfillStatusResponse | null;
  latestSignalTimestamp: string | null;
  persistence: PersistenceHealthSummary;
}

export function DiagnosticsPanel({
  selectedSymbol,
  health,
  status,
  workstation,
  backfillStatus,
  latestSignalTimestamp,
  persistence,
}: DiagnosticsPanelProps) {
  const positionState = workstation?.current_position
    ? `${workstation.current_position.quantity} ${workstation.current_position.symbol}`
    : 'No open paper position';

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Diagnostics</p>
        <p className="mt-2 text-sm text-slate-400">Compact release-readiness checks for the selected workstation.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard label="Runtime State" value={status.state} helper={`Mode ${status.mode}`} />
        <MetricCard label="Selected Symbol" value={selectedSymbol || '-'} helper={`Runtime ${status.symbol ?? '-'}`} />
        <MetricCard label="Storage Health" value={persistence.persistence_state.replace(/_/g, ' ')} helper={health?.storage ?? persistence.persistence_message} />
        <MetricCard
          label="Backfill State"
          value={backfillStatus?.status ?? 'not started'}
          helper={backfillStatus ? `${backfillStatus.coverage_pct}% coverage` : 'No backfill read yet'}
        />
        <MetricCard label="Latest Signal" value={formatDateTime(latestSignalTimestamp)} helper="Most recent advisory timestamp" />
        <MetricCard label="Position State" value={positionState} helper="Paper broker state only" />
      </div>
    </div>
  );
}
