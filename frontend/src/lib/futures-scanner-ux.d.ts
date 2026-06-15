import type { FuturesOpportunityScanResponse } from './types';

export function scannerCandidateCount(scan: FuturesOpportunityScanResponse | null): number;
export function hasScannerCandidates(scan: FuturesOpportunityScanResponse | null): boolean;
export function isLastSuccessfulScannerCache(scan: FuturesOpportunityScanResponse | null): boolean;
export function buildScannerUnavailableMessage(error: string | null, hasCachedResults: boolean): string;
