interface StatePanelProps {
  title: string;
  message: string;
  tone?: 'loading' | 'error' | 'empty';
}

export function StatePanel({ title, message, tone = 'loading' }: StatePanelProps) {
  const friendlyMessage = tone === 'error' ? message : guideEmptyState(message);
  const toneClass = tone === 'error'
    ? 'border-rose-400/30 bg-rose-400/10 text-rose-100'
    : 'border-borderSoft bg-panelBgSoft/80 text-textSecondary';

  return (
    <div className={`rounded-lg border px-4 py-5 ${toneClass}`}>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-2 text-sm leading-6">{friendlyMessage}</p>
    </div>
  );
}

function guideEmptyState(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes('waiting for runtime') || normalized.includes('start the live runtime')) {
    return 'Start paper runtime to collect live market context.';
  }
  if (normalized.includes('not enough data') || normalized.includes('need more')) {
    return 'Validation appears after enough paper signals are evaluated.';
  }
  if (normalized.includes('no ai history') || normalized.includes('advisory history')) {
    return 'AI history will appear after the runtime generates advisory snapshots.';
  }
  if (normalized.includes('chart') && (normalized.includes('waiting') || normalized.includes('loading'))) {
    return 'Historical candles are still loading. Try refresh or start runtime.';
  }
  return message;
}

