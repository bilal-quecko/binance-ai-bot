import type { PropsWithChildren, ReactNode } from 'react';

interface AdvancedDetailsProProps extends PropsWithChildren {
  action?: ReactNode;
  defaultOpen?: boolean;
}

export function AdvancedDetailsPro({ action, children, defaultOpen = false }: AdvancedDetailsProProps) {
  const defaultOpenProps = defaultOpen ? { open: true } : {};

  return (
    <details className="rounded-lg border border-slate-800 bg-slate-950/55 p-4 shadow-glow" {...defaultOpenProps}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">Advanced Details - Pro</p>
          <p className="mt-1 text-xs text-slate-400">
            Full technical, validation, performance, and diagnostic detail for deeper review.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {action}
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
            Expand
          </span>
        </div>
      </summary>
      <div className="mt-5 space-y-4">{children}</div>
    </details>
  );
}
