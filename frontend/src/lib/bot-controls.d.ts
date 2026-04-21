export function canStartBot(
  selectedSymbol: string,
  state: 'stopped' | 'running' | 'paused' | 'error',
  actionLoading: boolean,
): boolean;
