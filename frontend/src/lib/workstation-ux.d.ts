import type { PatternAnalysisResponse, TradeReadinessResponse } from './types';

export interface PatternCoverageSummary {
  value: string;
  helper: string;
  isPreliminary: boolean;
}

export function formatDurationLabel(start: string | null, end: string | null): string;
export function buildPatternCoverageSummary(analysis: PatternAnalysisResponse | null): PatternCoverageSummary;
export function humanizeReadinessAction(nextAction: string | null | undefined): string;
export function humanizeMode(mode: string | null | undefined): string;
export function describeReadiness(readiness: TradeReadinessResponse | null): string;
export function shouldShowCostMetrics(readiness: TradeReadinessResponse | null): boolean;
