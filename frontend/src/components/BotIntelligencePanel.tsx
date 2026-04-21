import { SectionCard } from './SectionCard';

import type { BotIntelligence, DerivedNarrative } from '../lib/insights';

interface BotIntelligencePanelProps {
  intelligence: BotIntelligence;
  narrative: DerivedNarrative;
}

const ITEMS: Array<{ key: keyof BotIntelligence; label: string }> = [
  { key: 'currentState', label: 'Current state' },
  { key: 'lastAction', label: 'Last action' },
  { key: 'lastSymbol', label: 'Last symbol' },
  { key: 'reasonForLastAction', label: 'Reason for last action' },
  { key: 'currentTrendBias', label: 'Current trend bias' },
  { key: 'riskState', label: 'Risk state' },
];

export function BotIntelligencePanel({ intelligence, narrative }: BotIntelligencePanelProps) {
  return (
    <SectionCard
      title="Bot Intelligence"
      description="A quick read on what the paper bot is doing now, why it acted, and how risk is framing the next move."
    >
      <div className="mb-4 rounded-2xl border border-sky-500/20 bg-sky-500/8 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-200">{narrative.label}</p>
        <p className="mt-2 text-sm leading-6 text-slate-100">{narrative.text}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {ITEMS.map((item) => (
          <div key={item.key} className="rounded-2xl border border-slate-800 bg-slate-950/55 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
            <p className="mt-3 text-lg font-semibold text-white">{intelligence[item.key]}</p>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}
