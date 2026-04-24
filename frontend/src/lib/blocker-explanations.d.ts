export interface BlockerExplanation {
  title: string;
  happened: string;
  why: string;
  action: string;
  category: 'risk_protection' | 'system_state' | 'data_requirement' | 'setup_quality' | 'state_info';
}

export function explainPrimaryBlocker(readiness: unknown): BlockerExplanation | null;
