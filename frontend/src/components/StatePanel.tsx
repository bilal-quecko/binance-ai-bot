interface StatePanelProps {
  title: string;
  message: string;
  tone?: 'loading' | 'error' | 'empty';
}

export function StatePanel({ title, message, tone = 'loading' }: StatePanelProps) {
  const toneClass = tone === 'error' ? 'border-rose-500/30 bg-rose-500/10 text-rose-200' : 'border-slate-700 bg-slate-900/70 text-slate-300';

  return (
    <div className={`rounded-xl border px-4 py-5 ${toneClass}`}>
      <p className="text-sm font-semibold uppercase tracking-[0.16em]">{title}</p>
      <p className="mt-2 text-sm">{message}</p>
    </div>
  );
}

